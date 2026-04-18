# Getting Started with DuckyAI

This guide walks you through setting up your DuckyAI vault step by step.

> **Prefer the quick path?** Open the workspace in VS Code and run `@workspace set up my vault` — the setup skill handles most of this for you.

## Prerequisites

| Tool | Required | Why |
|------|----------|-----|
| [Obsidian](https://obsidian.md/) | ✅ | The vault viewer/editor |
| [VS Code](https://code.visualstudio.com/) | ✅ | Copilot host + vault automation |
| [GitHub Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) | ✅ | AI assistant with skills/prompts |
| Git | ✅ | Repo sync, version control |

## Step 1: Clone the Template

```powershell
# Clone to your Obsidian vault location
git clone https://dev.azure.com/msazure/Azure%20AppConfig/_git/DuckyAI "$HOME\Documents\Obsidian\DuckyAI"
cd "$HOME\Documents\Obsidian\DuckyAI"
```

## Step 2: Open in VS Code

Open `DuckyAI.code-workspace` in VS Code. This sets up the workspace with the vault and any synced doc repos.

## Step 3: Use the Native Vault Tooling

The vault automation surface now runs natively in Python through the CLI daemon and HTTP API. There is no separate Node.js build step for the vault tools.

## Step 4: Personalize Your Vault

### Option A: Use the Setup Skill (Recommended)

In VS Code Copilot Chat:
```
@workspace set up my vault
```

The skill will ask for your name, role, technologies, and configure everything.

### Option B: Manual Configuration

1. **Edit `.github/copilot-instructions.md`:**
   - Replace `[USER_NAME]` with your full name
   - Replace `[USER_ROLE]` with your role
   - Replace `[USER_SPECIALIZATION]` with your focus areas
   - Replace `[USER_TECHNOLOGIES]` with your tech stack
   - Fill in the "Domain Knowledge" section with context about your team's tools and services

2. **Edit `Home.md`:**
   - Replace `[USER_NAME]` in the header and System Info section
   - Replace `[USER_ROLE]` and `[USER_TECHNOLOGIES]` in System Info

3. **Configure code review skill** (if you use Azure DevOps):
   - Edit `.github/skills/code-review/SKILL.md`
   - Update the default org and project values

## Step 5: Install Obsidian Plugins

Open the vault folder in Obsidian, then install these community plugins:

1. **Periodic Notes** — enables daily/weekly note templates
   - Settings: set Daily Note template to `Templates/Daily Note` and folder to `04-Periodic/Daily`
   
2. **Templater** — advanced template variable expansion
   - Settings: set template folder to `Templates`

3. **Dataview** — powers the dynamic queries on the Home page
   - No special settings needed

See [[Obsidian Plugin Setup]] for detailed configuration.

## Step 6: Configure Documentation Repos (Optional)

If you want Copilot to have access to your team's documentation repos:

1. Copy `scripts/repos.json.example` to `scripts/repos.json`
2. Edit `scripts/repos.json` — add your repo URLs, branches, and optional sparse checkout paths
3. Run the sync:
   ```powershell
   .\scripts\sync-repos.ps1
   ```

Repos are cloned to `.repos/` (git-ignored). Copilot can then reference them for context.

## Step 7: Create Your First Daily Note

In VS Code Copilot Chat:
```
@workspace prepare today's daily note
```

Or manually create `04-Periodic/Daily/{YYYY-MM-DD}.md` using the Daily Note template.

## What's Next?

- **Create a task:** `@workspace /new-task`
- **Log a meeting:** `@workspace /new-meeting`
- **Start an investigation:** `@workspace /new-investigation`
- **Review a PR:** `@workspace review PR https://dev.azure.com/...`
- **Build a custom skill:** `@workspace create a skill for [your use case]`

## Updating Your Vault

When new template versions are released:

```
@workspace update my vault
```

The update skill pulls template changes (Python vault tools, templates, prompts, skills) without touching your personal content (tasks, notes, people, etc.).

## Troubleshooting

### Vault automation not detected
- Ensure you opened `DuckyAI.code-workspace` (not just the folder)
- Ensure the CLI environment is installed and the daemon can start
- Restart VS Code or restart the DuckyAI daemon if discovery looks stale

### Daily note template not working
- Ensure Periodic Notes plugin is installed and configured
- Template folder should be `Templates`, daily note folder `04-Periodic/Daily`

### Dataview queries show nothing
- Install the Dataview plugin
- Ensure notes have proper frontmatter (the templates handle this)

### Repo sync fails
- Ensure Git credential manager is configured for your ADO org
- Try `git clone` manually to test authentication
