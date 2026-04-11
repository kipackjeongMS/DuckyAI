#!/usr/bin/env bash
# sync-services.sh — Sync all ADO service repos based on duckyai.yml config
#
# Reads services.entries from duckyai.yml, filters entries with metadata.type=ado,
# and invokes clone-ado-repos.sh for each service.
#
# Usage:
#   sync-services.sh --config <path/to/duckyai.yml> --services-path <path> [--dry-run] [--depth <n>]
#   sync-services.sh --vault <vault-root>   # auto-discovers config + services path
#
# Examples:
#   sync-services.sh --vault ~/Main
#   sync-services.sh --vault ~/Main --dry-run
#   sync-services.sh --config ~/Main/.duckyai/duckyai.yml --services-path ~/Main-Services

set -uo pipefail

# ─── Defaults ────────────────────────────────────────────────────────
CONFIG_FILE=""
SERVICES_PATH=""
VAULT_PATH=""
DRY_RUN=false
DEPTH=""
CLONE_SCRIPT=""

# ─── Parse args ──────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)         CONFIG_FILE="$2"; shift 2 ;;
        --services-path)  SERVICES_PATH="$2"; shift 2 ;;
        --vault)          VAULT_PATH="$2"; shift 2 ;;
        --dry-run)        DRY_RUN=true; shift ;;
        --depth)          DEPTH="$2"; shift 2 ;;
        --clone-script)   CLONE_SCRIPT="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# ─── Resolve vault → config + services path ──────────────────────────
if [[ -n "$VAULT_PATH" ]]; then
    # Auto-discover from vault root
    if [[ -z "$CONFIG_FILE" ]]; then
        if [[ -f "$VAULT_PATH/.duckyai/duckyai.yml" ]]; then
            CONFIG_FILE="$VAULT_PATH/.duckyai/duckyai.yml"
        elif [[ -f "$VAULT_PATH/duckyai.yml" ]]; then
            CONFIG_FILE="$VAULT_PATH/duckyai.yml"
        fi
    fi
fi

if [[ -z "$CONFIG_FILE" || ! -f "$CONFIG_FILE" ]]; then
    echo "Error: duckyai.yml not found. Use --config or --vault" >&2
    exit 1
fi

CONFIG_DIR=$(cd "$(dirname "$CONFIG_FILE")" && pwd)

# ─── Resolve az CLI ──────────────────────────────────────────────────
AZ_BIN=$(command -v az 2>/dev/null || echo "")
if [[ -z "$AZ_BIN" ]]; then
    AZ_BIN=$(command -v az.cmd 2>/dev/null || echo "")
fi
if [[ -z "$AZ_BIN" ]]; then
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

# ─── Find clone-ado-repos.sh ─────────────────────────────────────────
if [[ -z "$CLONE_SCRIPT" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    # Check same directory, parent scripts/, skill scripts/
    for candidate in \
        "$SCRIPT_DIR/clone-ado-repos.sh" \
        "$SCRIPT_DIR/../scripts/clone-ado-repos.sh" \
        "$SCRIPT_DIR/scripts/clone-ado-repos.sh"; do
        if [[ -f "$candidate" ]]; then
            CLONE_SCRIPT="$candidate"
            break
        fi
    done
fi
if [[ -z "$CLONE_SCRIPT" || ! -f "$CLONE_SCRIPT" ]]; then
    echo "Error: clone-ado-repos.sh not found. Use --clone-script or place it alongside this script." >&2
    exit 1
fi

# ─── Parse duckyai.yml (pure bash — extract service entries) ──────────
# We parse the YAML line by line to extract services.entries with metadata.
# This avoids Python/yq dependency.

parse_services() {
    local config="$1"
    local in_entries=false
    local in_entry=false
    local in_metadata=false
    local in_repos=false
    local current_name=""
    local current_type=""
    local current_org=""
    local current_project=""
    local current_repos=()
    local services_path_from_config=""

    while IFS= read -r line; do
        # Strip carriage return (Windows line endings)
        line="${line%$'\r'}"

        # Detect services.path
        if [[ "$line" =~ ^[[:space:]]+path:[[:space:]]*\"?([^\"]+)\"? ]]; then
            if [[ "$in_entries" == false && -z "$services_path_from_config" ]]; then
                services_path_from_config="${BASH_REMATCH[1]}"
            fi
        fi

        # Detect entries list start
        if [[ "$line" =~ ^[[:space:]]+entries: ]]; then
            in_entries=true
            continue
        fi

        if [[ "$in_entries" == false ]]; then
            continue
        fi

        # Detect new entry (- name: ...)
        if [[ "$line" =~ ^[[:space:]]*-[[:space:]]+name:[[:space:]]*\"?([^\"]+)\"? ]]; then
            # Emit previous entry if complete
            if [[ -n "$current_name" && "$current_type" == "ado" && -n "$current_org" && -n "$current_project" ]]; then
                echo "ENTRY|${current_name}|${current_org}|${current_project}|${current_repos[*]}"
            fi
            current_name="${BASH_REMATCH[1]}"
            current_type=""
            current_org=""
            current_project=""
            current_repos=()
            in_entry=true
            in_metadata=false
            in_repos=false
            continue
        fi

        # Detect metadata block
        if [[ "$in_entry" == true && "$line" =~ ^[[:space:]]+metadata: ]]; then
            in_metadata=true
            continue
        fi

        if [[ "$in_metadata" == true ]]; then
            if [[ "$line" =~ ^[[:space:]]+type:[[:space:]]*\"?([^\"]+)\"? ]]; then
                current_type="${BASH_REMATCH[1]}"
            elif [[ "$line" =~ ^[[:space:]]+organization:[[:space:]]*\"?([^\"]+)\"? ]]; then
                current_org="${BASH_REMATCH[1]}"
            elif [[ "$line" =~ ^[[:space:]]+project:[[:space:]]*\"?([^\"]+)\"? ]]; then
                current_project="${BASH_REMATCH[1]}"
            elif [[ "$line" =~ ^[[:space:]]+repositories:[[:space:]]*\[(.+)\] ]]; then
                # Inline array: repositories: [ "item1", "item2" ]
                local inline="${BASH_REMATCH[1]}"
                # Strip quotes and split by comma
                inline="${inline//\"/}"
                inline="${inline//\'/}"
                IFS=',' read -ra items <<< "$inline"
                for item in "${items[@]}"; do
                    item=$(echo "$item" | xargs)  # trim whitespace
                    [[ -n "$item" ]] && current_repos+=("$item")
                done
            elif [[ "$line" =~ ^[[:space:]]+repositories: ]]; then
                # Multi-line list follows
                in_repos=true
                continue
            fi
        fi

        # Parse repository list items
        if [[ "$in_repos" == true ]]; then
            if [[ "$line" =~ ^[[:space:]]+-[[:space:]]*\"?([^\"]+)\"? ]]; then
                current_repos+=("${BASH_REMATCH[1]}")
            else
                in_repos=false
            fi
        fi

        # Detect end of entries (next top-level key)
        if [[ "$in_entries" == true && "$line" =~ ^[a-z] && ! "$line" =~ ^[[:space:]] ]]; then
            break
        fi
    done < "$config"

    # Emit last entry
    if [[ -n "$current_name" && "$current_type" == "ado" && -n "$current_org" && -n "$current_project" ]]; then
        echo "ENTRY|${current_name}|${current_org}|${current_project}|${current_repos[*]}"
    fi

    # Emit services path
    if [[ -n "$services_path_from_config" ]]; then
        echo "SERVICES_PATH|${services_path_from_config}"
    fi
}

# ─── Read config ──────────────────────────────────────────────────────
echo "📋 Reading config: ${CONFIG_FILE}"

PARSED_SERVICES_PATH=""
ENTRIES=()

while IFS='|' read -r tag name org project repos; do
    if [[ "$tag" == "SERVICES_PATH" ]]; then
        PARSED_SERVICES_PATH="$name"
    elif [[ "$tag" == "ENTRY" ]]; then
        ENTRIES+=("${name}|${org}|${project}|${repos}")
    fi
done < <(parse_services "$CONFIG_FILE")

# Resolve services path
if [[ -z "$SERVICES_PATH" ]]; then
    if [[ -n "$PARSED_SERVICES_PATH" ]]; then
        # Resolve relative to vault root (config parent's parent for .duckyai/duckyai.yml)
        if [[ -n "$VAULT_PATH" ]]; then
            SERVICES_PATH=$(cd "$VAULT_PATH" && cd "$PARSED_SERVICES_PATH" 2>/dev/null && pwd || echo "$VAULT_PATH/$PARSED_SERVICES_PATH")
        else
            SERVICES_PATH=$(cd "$CONFIG_DIR/.." && cd "$PARSED_SERVICES_PATH" 2>/dev/null && pwd || echo "$CONFIG_DIR/../$PARSED_SERVICES_PATH")
        fi
    else
        echo "Error: Cannot determine services path. Use --services-path" >&2
        exit 1
    fi
fi

echo "   Services path: ${SERVICES_PATH}"
echo "   Found ${#ENTRIES[@]} ADO service(s)"
echo ""

if [[ ${#ENTRIES[@]} -eq 0 ]]; then
    echo "⚠️  No services with ADO metadata found in config."
    exit 0
fi

# ─── Sync each service ───────────────────────────────────────────────
TOTAL_CLONED=0
TOTAL_FETCHED=0
TOTAL_FAILED=0
SERVICES_SYNCED=0

for entry in "${ENTRIES[@]}"; do
    IFS='|' read -r name org project repos <<< "$entry"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔄 Syncing: ${name} (${org}/${project})"

    TARGET="${SERVICES_PATH}/${name}"
    mkdir -p "$TARGET"

    # Build --repos args (repos are space-separated in the entry string)
    REPO_ARGS=()
    # Use set -f to prevent glob expansion of * patterns
    set -f
    for repo in $repos; do
        REPO_ARGS+=(--repos "$repo")
    done
    set +f

    # Build optional args
    EXTRA_ARGS=()
    if $DRY_RUN; then
        EXTRA_ARGS+=(--dry-run)
    fi
    if [[ -n "$DEPTH" ]]; then
        EXTRA_ARGS+=(--depth "$DEPTH")
    fi

    # Invoke clone script
    bash "$CLONE_SCRIPT" \
        --org "$org" \
        --project "$project" \
        "${REPO_ARGS[@]}" \
        --target "$TARGET" \
        "${EXTRA_ARGS[@]}" 2>&1

    EXIT_CODE=$?
    if [[ $EXIT_CODE -eq 0 ]]; then
        SERVICES_SYNCED=$((SERVICES_SYNCED + 1))
    else
        echo "   ⚠️  Service ${name} had errors (exit code ${EXIT_CODE})"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    fi
    echo ""
done

# ─── Summary ─────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Service Sync Summary"
echo "   Services synced: ${SERVICES_SYNCED} / ${#ENTRIES[@]}"
echo "   Failed: ${TOTAL_FAILED}"
echo "   Target: ${SERVICES_PATH}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
