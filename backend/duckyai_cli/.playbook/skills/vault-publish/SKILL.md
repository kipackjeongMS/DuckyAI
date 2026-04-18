---
name: vault-publish
description: 'Publish vault infrastructure changes to the DuckyAI template repo. Use when the user says "publish vault updates", "sync to template", "push to template", or "publish changes". Diffs personal vault against the template repo, strips personal content, stages changes for review.'
---

# Vault Publish Skill

Sync infrastructure changes from your personal DuckyAI vault to the DuckyAI-Template repo, stripping personal content and staging for review before commit.

> **This skill is included in the template.** Any DuckyAI user can contribute improvements back to the shared template by running this skill.

## When to Use

- You've made changes to the MCP server, templates, prompts, or skills in your personal vault
- You want to publish those improvements to the shared template
- User says "publish vault updates", "sync to template", "push changes to template"

## Configuration

- **Personal vault root:** The current workspace root
- **Template repo location:** Auto-detected from `version.json` → `templateRepo` field, cloned to a temp directory. Falls back to `C:\repos\DuckyAI-Template` if a local clone exists.
- **Template remote:** Read from `version.json` (default: `https://dev.azure.com/msazure/Azure%20AppConfig/_git/DuckyAI`)

## Instructions

### Step 0: Verify Template Repo Exists

```powershell
# Read template repo URL from version.json
$versionFile = "version.json"
if (Test-Path $versionFile) {
    $versionInfo = Get-Content $versionFile | ConvertFrom-Json
    $templateUrl = $versionInfo.templateRepo
} else {
    $templateUrl = "https://dev.azure.com/msazure/Azure%20AppConfig/_git/DuckyAI"
}

# Use local clone if available, otherwise clone to temp
$templateDir = "C:\repos\DuckyAI-Template"
if (-not (Test-Path $templateDir)) {
    $templateDir = Join-Path $env:TEMP "duckyai-template-publish"
    if (-not (Test-Path $templateDir)) {
        git clone --depth 1 $templateUrl $templateDir
    }
}
```

Ensure the template repo is on `main` and up to date:
```powershell
git -C $templateDir checkout main
git -C $templateDir pull origin main
```

### Step 1: Define File Maps

Infrastructure files that get synced from personal vault → template:

**Direct copy (no transformation needed):**
```
.github/prompts/*.prompt.md
.github/skills/code-review/SKILL.md
.github/skills/make-skill-template/SKILL.md
.github/skills/vault-setup/SKILL.md
.github/skills/vault-update/SKILL.md
.vscode/mcp.json
mcp-server/src/index.ts
mcp-server/package.json
mcp-server/tsconfig.json
scripts/sync-repos.ps1
Templates/*.md
DuckyAI.code-workspace
03-Knowledge/Documentation/DuckyAI MCP Server.md
03-Knowledge/Documentation/Obsidian Plugin Setup.md
```

**Special merge (strip personal content):**
```
.github/copilot-instructions.md
```

**Never sync (blocklist):**
```
00-Inbox/
01-Work/
02-People/
03-Knowledge/ (except the two docs above)
04-Periodic/
05-Archive/
Home.md
.env
scripts/repos.json
.repos/
.obsidian/
.github/skills/vault-publish/  (this skill itself — personal only)
```

### Step 2: Diff Infrastructure Files

For each file in the direct-copy list, compare the personal vault version against the template version:

```powershell
$vaultRoot = Get-Location
$templateDir = "C:\repos\DuckyAI-Template"

# Compare each infrastructure file
$files = @(
    ".github/prompts/new-task.prompt.md",
    ".github/prompts/new-investigation.prompt.md",
    ".github/prompts/new-meeting.prompt.md",
    ".github/prompts/add-documentation.prompt.md",
    ".github/prompts/archive-task.prompt.md",
    ".github/prompts/prioritize-work.prompt.md",
    ".github/prompts/restructure-document.prompt.md",
    ".github/skills/code-review/SKILL.md",
    ".github/skills/make-skill-template/SKILL.md",
    ".github/skills/vault-setup/SKILL.md",
    ".github/skills/vault-update/SKILL.md",
    ".vscode/mcp.json",
    "mcp-server/src/index.ts",
    "mcp-server/package.json",
    "mcp-server/tsconfig.json",
    "scripts/sync-repos.ps1",
    "DuckyAI.code-workspace",
    "03-Knowledge/Documentation/DuckyAI MCP Server.md",
    "03-Knowledge/Documentation/Obsidian Plugin Setup.md"
)

# Also glob Templates/*.md
$templateFiles = Get-ChildItem "Templates/*.md" -Name
foreach ($t in $templateFiles) { $files += "Templates/$t" }
```

For each file:
1. If file exists in vault but not in template → **NEW** file
2. If file exists in both and content differs → **MODIFIED**
3. If file exists in both and content matches → **UNCHANGED**

Report to the user:
```
Changed files:
  📝 mcp-server/src/index.ts (modified)
  🆕 .github/skills/new-skill/SKILL.md (new)

Unchanged:
  ✓ 15 files unchanged
```

### Step 3: Handle New Skills

Check for any **new** skill directories in `.github/skills/` that exist in the personal vault but not in the template. Exclude `vault-publish` (personal only).

For each new skill found, add it to the copy list.

### Step 4: Merge copilot-instructions.md

This file needs special handling because it has personal sections that must be replaced with placeholders.

**Personal sections (replace with template placeholders):**
- **Line 1-3:** Title and user intro → replace with `[USER_NAME]`, `[USER_ROLE]` version
- **"About the User" section** → replace with placeholder version
- **"Person Aliases" section** → replace with empty template table
- **"Synced Documentation Repos" section** → replace with empty template table
- **"Domain Knowledge" section** (was "Express V2 Context") → replace with placeholder comment

**Structural sections (take from personal vault — these are the updates):**
- Core Principles
- MCP Server Tools
- Vault Structure
- Frontmatter Schemas
- Linking Conventions
- File Naming Conventions
- Common Operations
- Quick Context Recovery
- Credential Handling
- Response Style
- Planning & Session Artifacts

**Algorithm:**
1. Read the personal vault's `copilot-instructions.md`
2. Read the template's `copilot-instructions.md`
3. Split both by `## ` headers into sections
4. For each section:
   - If it's a "personal" section → use the template's version (has placeholders)
   - If it's a "structural" section → use the personal vault's version (has updates)
5. Write the merged result to the template

### Step 5: Copy Files to Template

For each changed/new file, copy from personal vault to template:

```powershell
foreach ($file in $changedFiles) {
    $src = Join-Path $vaultRoot $file
    $dst = Join-Path $templateDir $file
    $dstDir = Split-Path $dst -Parent
    if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Force -Path $dstDir | Out-Null }
    Copy-Item $src $dst -Force
}
```

For `copilot-instructions.md`, write the merged version (from Step 4) instead of copying.

### Step 6: Verify No Personal Content Leaked

Run a check for personal references in the staged files:

```powershell
$personalPatterns = @()  # Add patterns like usernames, team names, etc.
# Read patterns from a config if available, otherwise use common ones
$hits = Get-ChildItem $templateDir -Recurse -File -Exclude *.js,*.map |
    Where-Object { $_.FullName -notlike "*node_modules*" -and $_.FullName -notlike "*.git\*" } |
    Select-String -Pattern ($personalPatterns -join "|") -SimpleMatch
```

If any hits found, warn the user and list them. Do NOT proceed until the user confirms.

### Step 7: Stage in Git

```powershell
git -C $templateDir add -A
git -C $templateDir diff --staged --stat
```

Show the staged diff summary to the user.

### Step 8: Prompt for Next Action

Ask the user what to do next:

1. **"Commit and push"** → proceed to version bump (see below)
2. **"Let me review first"** → stop here, user reviews manually
3. **"Abort"** → `git -C $templateDir checkout .` to revert

### Step 9: Version Bump (if committing)

Ask: **"What kind of change is this?"**
- **Patch** (bug fix, typo) → bump `x.x.X`
- **Minor** (new feature, new skill) → bump `x.X.0`
- **Major** (breaking change) → bump `X.0.0`

Then:
1. Read current `version.json`
2. Bump the version number
3. Ask for a one-line change summary
4. Update `CHANGELOG.md` with new section (use Keep a Changelog format)
5. Update `version.json` with new version + timestamp + changes array
6. Commit:
   ```powershell
   git -C $templateDir add -A
   git -C $templateDir commit -m "v{version}: {summary}

   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
   ```
7. Push to a feature branch:
   ```powershell
   $username = $env:USERNAME
   $branch = "users/$username/v{version}"
   git -C $templateDir checkout -b $branch
   git -C $templateDir push origin $branch
   ```
8. Output the PR creation URL:
   ```
   Create PR: https://dev.azure.com/msazure/Azure%20AppConfig/_git/DuckyAI/pullrequestcreate?sourceRef={branch}&targetRef=main
   ```

### Step 10: Summary

```
✅ Published vault updates to DuckyAI-Template

  Version: {old} → {new}
  Changed: {N} files
  Branch: users/{username}/v{version}
  PR: {url}

  Don't forget to merge the PR!
```
