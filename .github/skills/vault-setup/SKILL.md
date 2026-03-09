---
name: vault-setup
description: 'Set up your DuckyAI vault for the first time. Use when the user says "set up my vault", "configure DuckyAI", "get started", "initialize vault", or "OOBE". Walks through personalization, MCP server setup, and creates the first daily note.'
---

# Vault Setup Skill (OOBE)

Set up a fresh DuckyAI vault by walking the user through personalization and configuration.

## When to Use

- User just cloned the DuckyAI template
- User says "set up my vault", "get started", "configure DuckyAI", "initialize"
- Placeholders like `[USER_NAME]` still exist in vault files

## Instructions

### Step 1: Gather User Information

Ask the user for the following (one question at a time, use `ask_user` with choices where possible):

1. **Full name** (freeform)
2. **Role / title** (freeform, e.g., "Senior Engineer - Platform Engineering")
3. **Specialization** (freeform, e.g., "Cloud infrastructure, CI/CD, Kubernetes")
4. **Key technologies** (freeform, e.g., "TypeScript, Python, Bicep, Azure, Terraform")
5. **Do you use Azure DevOps for code reviews?** (Yes / No)
   - If yes: **ADO organization** (e.g., `msazure`) and **default project** (e.g., `MyProject`)
6. **Do you have documentation repos to sync?** (Yes, I'll configure later / No)
7. **Who is your manager?** (name + optional role, or skip)

### Step 2: Update Copilot Instructions

Edit `.github/copilot-instructions.md`:

1. Replace `[USER_NAME]` with the user's full name (line 3 and line 1 heading)
2. Replace `[USER_ROLE]` with their role (line 7)
3. Replace `[USER_SPECIALIZATION]` with their specialization (line 8)
4. Replace `[USER_TECHNOLOGIES]` with their technologies (line 9)
5. Leave Person Aliases table empty (user will populate over time)
6. If they provided domain knowledge, fill in the "Domain Knowledge" section

### Step 3: Update Home.md

Edit `Home.md`:

1. Replace `[USER_NAME]` with the user's full name (line 11)
2. Replace `[USER_NAME]`, `[USER_ROLE]`, `[USER_TECHNOLOGIES]` in the System Info section

### Step 4: Configure Code Review Skill (if ADO)

If the user uses Azure DevOps:

1. Edit `.github/skills/code-review/SKILL.md`
2. Replace `org=your-org` with their organization
3. Replace `project=your-project` with their default project

### Step 5: Configure Repos (if applicable)

If the user wants to sync repos:

1. Copy `scripts/repos.json.example` to `scripts/repos.json`
2. Tell the user to edit `scripts/repos.json` with their repo URLs
3. Remind them to run `.\scripts\sync-repos.ps1` after configuring

### Step 6: Build MCP Server

Run:
```powershell
Push-Location mcp-server
npm install
npm run build
Pop-Location
```

Verify the build succeeds. If it fails, troubleshoot (usually Node.js version issue — needs Node 18+).

### Step 7: Create Manager Contact (if provided)

If the user provided their manager's name:

1. Create `02-People/Contacts/{Manager Name}.md` with the Person frontmatter schema
2. Set role and team fields based on what the user provided

### Step 8: Create First Daily Note

Use the MCP `prepareDailyNote` tool if available, or manually create today's daily note:

1. Create `04-Periodic/Daily/{YYYY-MM-DD}.md` using the Daily Note template
2. Add a welcome item to Focus Today: `- [ ] Finish setting up DuckyAI vault`

### Step 9: Obsidian Plugin Reminder

Tell the user to install these Obsidian community plugins (requires manual install):

1. **Periodic Notes** — for daily/weekly note automation
2. **Templater** — for template variable expansion
3. **Dataview** — for the dynamic queries on the Home page (Active Work section)

Provide the link: [[03-Knowledge/Documentation/Obsidian Plugin Setup]]

### Step 10: Summary

Print a summary of what was configured:
```
✅ DuckyAI vault configured for {name}
   - Copilot instructions personalized
   - Home page updated
   - MCP server built
   - {Optional: Code review skill configured for {org}/{project}}
   - {Optional: Manager contact created}
   - First daily note created
   
📋 Next steps:
   1. Install Obsidian plugins (Periodic Notes, Templater, Dataview)
   2. Configure repos in scripts/repos.json (optional)
   3. Start using the vault! Try: @workspace /new-task
```
