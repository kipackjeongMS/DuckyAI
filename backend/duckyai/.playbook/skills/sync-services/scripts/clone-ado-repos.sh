#!/usr/bin/env bash
# clone-ado-repos.sh — Clone Azure DevOps repos by org/project/pattern
#
# Usage:
#   clone-ado-repos.sh --org <organization> --project <project> --repos <pattern> [--target <dir>] [--depth <n>] [--dry-run]
#
# Repository patterns:
#   "*"              — all repos in the project
#   "ServiceLinker*" — glob prefix match (fnmatch-style)
#   "MyRepo"         — exact repo name
#   Multiple patterns: --repos "RepoA" --repos "Prefix*"
#
# Examples:
#   clone-ado-repos.sh --org msazure --project "Azure AppConfig" --repos "*" --target ./services/AppConfig
#   clone-ado-repos.sh --org msazuredev --project AzureDevSvcAI --repos "DevOpsDeploymentAgents" --target ./services/DEPA
#   clone-ado-repos.sh --org msazure --project One --repos "ServiceLinker*" --target ./services/ServiceConnector --depth 1
#
# Auth:
#   Uses AZURE_DEVOPS_EXT_PAT env var if set (recommended).
#   Otherwise falls back to az CLI's cached credentials.

set -uo pipefail

# ─── Defaults ────────────────────────────────────────────────────────
ORG=""
PROJECT=""
REPO_PATTERNS=()
TARGET_DIR="."
DEPTH=""
DRY_RUN=false
FETCH_ONLY=false

# ─── Parse args ──────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --org)          ORG="$2"; shift 2 ;;
        --project)      PROJECT="$2"; shift 2 ;;
        --repos|--repo) REPO_PATTERNS+=("$2"); shift 2 ;;
        --target)       TARGET_DIR="$2"; shift 2 ;;
        --depth)        DEPTH="$2"; shift 2 ;;
        --dry-run)      DRY_RUN=true; shift ;;
        --fetch-only)   FETCH_ONLY=true; shift ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# ─── Validate ────────────────────────────────────────────────────────
if [[ -z "$ORG" || -z "$PROJECT" ]]; then
    echo "Error: --org and --project are required" >&2
    exit 1
fi
if [[ ${#REPO_PATTERNS[@]} -eq 0 ]]; then
    echo "Error: at least one --repos pattern is required" >&2
    exit 1
fi

ORG_URL="https://dev.azure.com/${ORG}"

# ─── Resolve az CLI ──────────────────────────────────────────────────
AZ_BIN=$(command -v az 2>/dev/null || echo "")
if [[ -z "$AZ_BIN" ]]; then
    AZ_BIN=$(command -v az.cmd 2>/dev/null || echo "")
fi
if [[ -z "$AZ_BIN" ]]; then
    # Windows: add Azure CLI to PATH for Git Bash / MSYS2
    for az_dir in \
        "/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin" \
        "/mnt/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin"; do
        if [[ -f "${az_dir}/az.cmd" ]]; then
            export PATH="${PATH}:${az_dir}"
            AZ_BIN="az.cmd"
            break
        fi
    done
fi
if [[ -z "$AZ_BIN" ]]; then
    echo "Error: az CLI not found. Install Azure CLI or add to PATH." >&2
    exit 1
fi

# ─── Pattern matching (fnmatch-style) ────────────────────────────────
matches_pattern() {
    local name="$1"
    local pattern="$2"
    if [[ "$pattern" == "*" ]]; then
        return 0
    fi
    # Use bash built-in glob matching
    # shellcheck disable=SC2254
    case "$name" in
        $pattern) return 0 ;;
        *) return 1 ;;
    esac
}

# ─── Step 1: List all repos in the project ───────────────────────────
echo "📡 Querying repos: ${ORG_URL} / ${PROJECT}"

# Use temp file for az output (Windows Git Bash .cmd wrappers need cmd //c for stdout)
_AZ_TMPFILE=$(mktemp)
trap 'rm -f "$_AZ_TMPFILE"' EXIT

if [[ "$AZ_BIN" == *.cmd ]]; then
    cmd //c "$AZ_BIN" repos list \
        --org "$ORG_URL" \
        --project "$PROJECT" \
        --output tsv \
        --query "[][name,remoteUrl]" \
        > "$_AZ_TMPFILE" 2>/dev/null || true
else
    "$AZ_BIN" repos list \
        --org "$ORG_URL" \
        --project "$PROJECT" \
        --output tsv \
        --query "[][name,remoteUrl]" \
        > "$_AZ_TMPFILE" 2>/dev/null || true
fi

if [[ ! -s "$_AZ_TMPFILE" ]]; then
    echo "Error: az repos list returned no data. Check auth and org/project names." >&2
    exit 1
fi

# Parse TSV into arrays (pure bash — no Python/jq needed)
REPO_NAMES=()
REPO_URLS=()
while IFS=$'\t' read -r name url; do
    [[ -z "$name" ]] && continue
    # Strip org@ prefix from URL: https://org@dev.azure.com/... → https://dev.azure.com/...
    url="${url/https:\/\/*@dev.azure.com/https:\/\/dev.azure.com}"
    REPO_NAMES+=("$name")
    REPO_URLS+=("$url")
done < "$_AZ_TMPFILE"

TOTAL_REPOS=${#REPO_NAMES[@]}
echo "   Found ${TOTAL_REPOS} repos in ${PROJECT}"

# ─── Step 2: Filter by patterns ──────────────────────────────────────
MATCHED_INDICES=()
for i in "${!REPO_NAMES[@]}"; do
    for pattern in "${REPO_PATTERNS[@]}"; do
        if matches_pattern "${REPO_NAMES[$i]}" "$pattern"; then
            MATCHED_INDICES+=("$i")
            break
        fi
    done
done

MATCH_COUNT=${#MATCHED_INDICES[@]}
if [[ $MATCH_COUNT -eq 0 ]]; then
    echo "⚠️  No repos matched patterns: ${REPO_PATTERNS[*]}"
    echo "   Available repos (first 20):"
    for i in "${!REPO_NAMES[@]}"; do
        [[ $i -ge 20 ]] && break
        echo "     - ${REPO_NAMES[$i]}"
    done
    exit 0
fi

echo "   Matched ${MATCH_COUNT} repos:"
for i in "${MATCHED_INDICES[@]}"; do
    echo "     ✓ ${REPO_NAMES[$i]}"
done

# ─── Step 3: Clone or fetch each matched repo ────────────────────────
if $DRY_RUN; then
    echo ""
    echo "🔍 Dry run — no changes made."
    exit 0
fi

mkdir -p "$TARGET_DIR"

CLONED=0
FETCHED=0
SKIPPED=0
FAILED=0

# Build git clone depth flag
DEPTH_FLAG=""
if [[ -n "$DEPTH" ]]; then
    DEPTH_FLAG="--depth $DEPTH"
fi

# Configure git auth if PAT is available
GIT_AUTH_HEADER=""
if [[ -n "${AZURE_DEVOPS_EXT_PAT:-}" ]]; then
    # Use PAT for authentication via extraheader
    ENCODED=$(echo -n ":${AZURE_DEVOPS_EXT_PAT}" | base64 -w0 2>/dev/null || echo -n ":${AZURE_DEVOPS_EXT_PAT}" | base64)
    GIT_AUTH_HEADER="Authorization: Basic ${ENCODED}"
fi

for i in "${MATCHED_INDICES[@]}"; do
    REPO_NAME="${REPO_NAMES[$i]}"
    REPO_URL="${REPO_URLS[$i]}"
    REPO_DIR="${TARGET_DIR}/${REPO_NAME}"

    if [[ -d "${REPO_DIR}/.git" ]]; then
        if $FETCH_ONLY || true; then
            echo "🔄 Fetching: ${REPO_NAME}"
            GIT_CMD=(git -C "$REPO_DIR")
            if [[ -n "$GIT_AUTH_HEADER" ]]; then
                GIT_CMD+=(-c "http.extraheader=${GIT_AUTH_HEADER}")
            fi
            # Remove stale lock files
            rm -f "${REPO_DIR}/.git/index.lock" "${REPO_DIR}/.git/shallow.lock" 2>/dev/null || true

            if "${GIT_CMD[@]}" fetch origin --prune 2>&1; then
                FETCHED=$((FETCHED + 1))
            else
                echo "   ⚠️  Fetch failed for ${REPO_NAME}"
                FAILED=$((FAILED + 1))
            fi
        else
            echo "⏭️  Skipping (exists): ${REPO_NAME}"
            SKIPPED=$((SKIPPED + 1))
        fi
    else
        echo "📦 Cloning: ${REPO_NAME}"
        # Remove partial dir if it exists without .git
        if [[ -d "$REPO_DIR" ]]; then
            rm -rf "$REPO_DIR"
        fi

        GIT_CMD=(git)
        if [[ -n "$GIT_AUTH_HEADER" ]]; then
            GIT_CMD+=(-c "http.extraheader=${GIT_AUTH_HEADER}")
        fi
        # shellcheck disable=SC2086
        if "${GIT_CMD[@]}" clone $DEPTH_FLAG "$REPO_URL" "$REPO_DIR" 2>&1; then
            CLONED=$((CLONED + 1))
        else
            echo "   ❌ Clone failed for ${REPO_NAME}"
            FAILED=$((FAILED + 1))
        fi
    fi
done

# ─── Summary ─────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Summary: ${ORG}/${PROJECT}"
echo "   Patterns: ${REPO_PATTERNS[*]}"
echo "   Target:   ${TARGET_DIR}"
echo "   Cloned:   ${CLONED}"
echo "   Fetched:  ${FETCHED}"
echo "   Skipped:  ${SKIPPED}"
echo "   Failed:   ${FAILED}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
