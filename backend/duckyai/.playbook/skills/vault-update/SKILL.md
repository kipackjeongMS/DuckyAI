---
name: vault-update
description: 'Safely update your DuckyAI vault with the latest template changes. Use when the user says "update vault", "pull template updates", "check for DuckyAI updates", or "upgrade vault". Updates infrastructure files (MCP server, templates, prompts, skills) without touching personal content.'
---

# Vault Update Skill

Safely pull updates from the DuckyAI template repository and apply them to the user's vault without overwriting personal content.

## When to Use

- User asks to update their vault
- User wants to check for new features or fixes
- New version of DuckyAI template is released

## Instructions

### Step 0: Read Current Version

Check if `version.json` exists in the vault root:

```powershell
Get-Content version.json | ConvertFrom-Json
```

If it doesn't exist, this is a pre-versioning vault — treat as version `0.0.0`.

### Step 1: Clone or Pull the Template Repo

Check if the template repo is already cloned:

```powershell
$templateDir = Join-Path $env:TEMP "duckyai-template-update"
if (Test-Path $templateDir) {
    git -C $templateDir pull origin main
} else {
    git clone --depth 1 https://dev.azure.com/msazure/Azure%20AppConfig/_git/DuckyAI $templateDir
}
```

> **Note:** Update the URL above if the template repo moves. The user may need to authenticate via Git credential manager.

### Step 2: Compare Versions

Read the template's `version.json` and compare with the local version:

```powershell
$templateVersion = Get-Content "$templateDir/version.json" | ConvertFrom-Json
$localVersion = if (Test-Path "version.json") { Get-Content "version.json" | ConvertFrom-Json } else { @{version="0.0.0"} }
```

If versions match, tell the user they're up to date and stop.

### Step 3: Identify Changed Files

Compare template infrastructure files against local copies. **ONLY** these paths are eligible for update:

#### Always update (infrastructure)
```
mcp-server/src/index.ts
mcp-server/package.json
mcp-server/tsconfig.json
scripts/sync-repos.ps1
.github/prompts/*.prompt.md
.github/skills/code-review/SKILL.md
.github/skills/make-skill-template/SKILL.md
.github/skills/vault-update/SKILL.md
Templates/*.md
.vscode/mcp.json
DuckyAI.code-workspace
```

#### Merge carefully (preserve user sections)
```
.github/copilot-instructions.md
```

For `copilot-instructions.md`:
1. Read the user's current file
2. Extract their personal sections (About the User, Person Aliases, Domain Knowledge)
3. Take the structural sections from the template (Core Principles, MCP Tools, Schemas, Operations, etc.)
4. Reassemble: template structural sections + user personal sections

#### NEVER touch (blocklist)
```
00-Inbox/
01-Work/
02-People/
03-Knowledge/ (except template docs)
04-Periodic/
05-Archive/
Home.md
.env
scripts/repos.json
version.json (updated separately at the end)
```

### Step 4: Show Diff Summary

Before applying any changes, show the user what will be updated:

```
📦 DuckyAI Update: v{local} → v{template}

Files to update:
  📝 mcp-server/src/index.ts (modified)
  📝 Templates/Daily Note.md (modified)
  🆕 .github/prompts/new-prompt.prompt.md (new)
  🔀 .github/copilot-instructions.md (merge — your personal sections preserved)

Files NOT touched:
  🔒 All personal content (01-Work, 02-People, 04-Periodic, etc.)
  🔒 Home.md, .env, repos.json
```

Ask the user to confirm: "Apply these updates?" (Yes / No)

### Step 5: Backup and Apply

1. **Create backup** of files being updated:
   ```powershell
   $backupDir = "05-Archive/.vault-backup-{timestamp}"
   ```
   Copy each file being modified to the backup directory.

2. **Copy updated files** from the template to the vault.

3. **Merge copilot-instructions.md** if it changed (using the strategy in Step 3).

4. **Rebuild MCP server** if `mcp-server/` files changed:
   ```powershell
   Push-Location mcp-server
   npm install
   npm run build
   Pop-Location
   ```

### Step 5.5: Patch `duckyai.yml` Agent Nodes (Config Migration)

Some infrastructure features are wired via the user's `duckyai.yml` agent node config (not copied files). Patch these in-place, preserving the user's other edits.

#### PR Review (PR) — `/repo-cache` mount

Ensures the PR Review agent reuses cloned repos across runs (avoids 30-120s re-clones).

1. Load `duckyai.yml` as YAML (use `Get-Content duckyai.yml | ConvertFrom-Yaml` via the `powershell-yaml` module, or `python -c "import yaml; ..."`).
2. Find the `nodes[]` entry where `name == "PR Review (PR)"`.
   - If missing → append the full node from `duckyai.yml.template` (the `PR Review (PR)` block).
   - If present → ensure `extra_mounts` contains both of:
     - `{ source: "${repo_cache}", target: "/repo-cache" }`
     - `{ source: "${services_path}", target: "/services", readonly: true }`
3. Write back, preserving YAML comments and ordering where possible (prefer `ruamel.yaml` round-trip mode over `PyYAML` dump).

Report each change in the Step 4 diff summary as:

```
🔧 duckyai.yml: PR Review (PR) node — added /repo-cache mount
```

Skip silently if the node already has both mounts.

### Step 6: Update Version

Write the new version to `version.json`:

```json
{
  "version": "1.1.0",
  "updatedAt": "2026-03-07T00:00:00Z",
  "templateRepo": "https://dev.azure.com/msazure/Azure%20AppConfig/_git/DuckyAI"
}
```

### Step 7: Summary

```
✅ DuckyAI vault updated to v{version}

Updated files:
  - {list of files}

Backup saved to: 05-Archive/.vault-backup-{timestamp}/

⚠️  If anything looks wrong, restore from the backup directory.
```

### Step 8: Cleanup

Remove the temp clone:
```powershell
Remove-Item $templateDir -Recurse -Force
```
