# Contributing to DuckyAI

Thank you for helping improve DuckyAI! This guide explains how to submit changes to the template.

## How It Works

DuckyAI is an Obsidian vault **template**. Users clone it and personalize it. Updates are pulled via the `vault-update` Copilot skill, which only touches infrastructure files — never personal content.

This means changes to the template must be:
- **General** — no user-specific content, paths, or references
- **Non-breaking** — existing vaults should still work after updating
- **Backward-compatible** — new features are additive, not destructive

## File Classification

### Infrastructure (shared via updates)

These files are synced to users when they run `vault-update`:

| Path | What it is |
|------|-----------|
| `cli/duckyai/api/vault_service.py` | Native Python vault tool implementations |
| `cli/duckyai/api/routes_vault.py` | Native vault API routing |
| `Templates/*.md` | Obsidian note templates |
| `.github/prompts/*.prompt.md` | Copilot prompts |
| `.github/skills/*/SKILL.md` | Copilot skill definitions |
| `.github/copilot-instructions.md` | AI context (structural sections only) |
| `.vscode/mcp.json` | MCP server config |
| `scripts/sync-repos.ps1` | Repo sync script |
| `DuckyAI.code-workspace` | VS Code workspace |

### Personal (never synced)

These are user-specific and never touched by updates:

- `00-Inbox/`, `01-Work/`, `02-People/`, `04-Periodic/`, `05-Archive/` — all user content
- `Home.md` — personalized after setup
- `scripts/repos.json` — user's repo list
- `.env` — user's config
- `.repos/` — user's synced repos
- `.obsidian/` — user's Obsidian settings

### Documentation (synced selectively)

- `03-Knowledge/Documentation/DuckyAI MCP Server.md` — synced
- `03-Knowledge/Documentation/Obsidian Plugin Setup.md` — synced
- All other docs in `03-Knowledge/` — user-created, not synced

## Submitting Changes

### 1. Clone the repo

```powershell
git clone https://dev.azure.com/msazure/Azure%20AppConfig/_git/DuckyAI
cd DuckyAI
```

### 2. Create a feature branch

```powershell
git checkout -b users/yourname/description
```

### 3. Make your changes

- **New skill:** Create `.github/skills/your-skill/SKILL.md`
- **New prompt:** Create `.github/prompts/your-prompt.prompt.md`
- **Vault tool change:** Edit `cli/duckyai/api/vault_service.py` and add or update tests under `cli/duckyai/tests/unit/`
- **Template change:** Edit files in `Templates/`
- **Instructions change:** Edit structural sections in `.github/copilot-instructions.md` (don't touch placeholder sections)

> **Tip:** You can also use the `vault-publish` skill to prototype changes in your own vault first, then extract and submit them:
> ```
> @workspace publish vault updates
> ```
> The skill diffs your vault against the template, strips personal content, and stages a PR-ready branch.

### 4. Test your changes

- Verify the vault tool tests pass: `cd cli && python -m pytest duckyai/tests/unit/test_vault_service.py duckyai/tests/unit/test_routes_vault.py -q`
- Check for accidental personal content: no hardcoded usernames, paths, or team-specific references
- If you added a skill, test it in your own vault first

### 5. Bump the version

Edit `version.json`:
- **Patch** (`1.0.0` → `1.0.1`): Bug fix, typo fix
- **Minor** (`1.0.0` → `1.1.0`): New feature, skill, prompt, or template
- **Major** (`1.0.0` → `2.0.0`): Breaking change (folder restructure, schema change)

Update `CHANGELOG.md` with your changes under the new version.

### 6. Submit a PR

```powershell
git add -A
git commit -m "v1.1.0: Description of changes

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push origin users/yourname/description
```

Create a PR targeting `main` in Azure DevOps.

## Guidelines

### Do
- ✅ Keep changes general and reusable
- ✅ Use placeholders (`[USER_NAME]`, `[USER_ROLE]`) in user-facing config
- ✅ Test the native vault API and service coverage before submitting
- ✅ Update CHANGELOG.md and version.json
- ✅ Add `.gitkeep` files in new empty directories

### Don't
- ❌ Hardcode paths, usernames, or organization names
- ❌ Add personal content (tasks, notes, people)
- ❌ Change the folder structure without a major version bump
- ❌ Modify placeholder sections in `copilot-instructions.md` (About the User, Person Aliases, Domain Knowledge)
- ❌ Remove existing templates or prompts without deprecation notice

## Questions?

Open an issue in the repo or reach out to the maintainers.
