# 🦆 DuckyAI

**AI-powered personal knowledge and task management for engineers.**

DuckyAI is an Obsidian vault template with built-in GitHub Copilot integration, Python-native vault automation, Copilot skills, prompts, and structured workflows that give your AI assistant persistent context about your work.

## Why DuckyAI?

AI assistants forget everything between conversations. DuckyAI gives Copilot a **persistent brain** — your tasks, projects, people, decisions, and domain knowledge — so it can actually help you work instead of starting from scratch every time.

- 📝 **Structured workflows** — tasks, investigations, meetings, daily notes with consistent frontmatter
- 🤖 **Native vault tools** — 23 Python automation tools (daily notes, PR reviews, tasks, meetings, sync state, roundup, and more)
- 💬 **Copilot prompts** — 7 ready-to-use prompts for common operations
- 🧠 **Copilot skills** — code review, vault setup, vault updates, and a skill builder
- 📂 **Repo syncing** — clone documentation repos for Copilot to reference
- 🔄 **Safe updates** — pull template improvements without losing your content

## Quick Start

### Prerequisites

- [Obsidian](https://obsidian.md/) (free)
- [VS Code](https://code.visualstudio.com/) with [GitHub Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot)
- Git

### Setup

1. **Clone this repo:**
   ```powershell
   git clone https://dev.azure.com/msazure/Azure%20AppConfig/_git/DuckyAI C:\Users\$env:USERNAME\Documents\Obsidian\DuckyAI
   ```

2. **Open in VS Code** — open `DuckyAI.code-workspace`

3. **Run the setup skill:**
   ```
   @workspace set up my vault
   ```
   The OOBE skill will walk you through personalization, configure the Python tooling, and create your first daily note.

4. **Open in Obsidian** — open the vault folder as an Obsidian vault

5. **Install plugins** — Periodic Notes, Templater, Dataview (see [Plugin Setup](03-Knowledge/Documentation/Obsidian%20Plugin%20Setup.md))

For detailed manual setup, see [GETTING_STARTED.md](GETTING_STARTED.md).

## Vault Structure

```
DuckyAI/
├── 00-Inbox/          # Quick capture, unsorted items
├── 01-Work/
│   ├── Tasks/         # Active work items (P0-P3)
│   ├── Projects/      # Multi-task initiatives
│   ├── Investigations/# Technical deep-dives
│   └── Plans/         # Implementation plans
├── 02-People/
│   ├── 1-on-1s/       # Recurring 1:1 notes
│   ├── Meetings/      # General meeting notes
│   └── Contacts/      # People profiles
├── 03-Knowledge/
│   ├── Documentation/ # Runbooks, how-tos, reference
│   └── Topics/        # General knowledge
├── 04-Periodic/
│   ├── Daily/         # Daily notes
│   └── Weekly/        # Weekly reviews
├── 05-Archive/        # Completed items
├── Templates/         # 9 Obsidian note templates
├── cli/               # Python CLI, daemon, API, and auxiliary services
├── scripts/           # Repo sync and utilities
└── .github/
    ├── copilot-instructions.md  # Your AI's context
    ├── prompts/                  # 7 Copilot prompts
    └── skills/                   # 4 Copilot skills
```

## Copilot Prompts

| Prompt | What it does |
|--------|-------------|
| `@workspace /new-task` | Create a task with priority and deadline |
| `@workspace /new-investigation` | Start a technical investigation |
| `@workspace /new-meeting` | Create meeting or 1:1 note |
| `@workspace /add-documentation` | Add to knowledge base |
| `@workspace /prioritize-work` | Get prioritized work list |
| `@workspace /archive-task` | Archive completed task |
| `@workspace /restructure-document` | Format and link a document |

## Copilot Skills

| Skill | What it does |
|-------|-------------|
| `vault-setup` | Interactive first-time setup |
| `vault-update` | Pull template updates safely |
| `code-review` | Review ADO pull requests |
| `vault-publish` | Contribute changes back to template |
| `make-skill-template` | Create new custom skills |

## Updating

When new template versions are released, update your vault safely:

```
@workspace update my vault
```

The update skill pulls infrastructure changes (Python vault tools, templates, prompts, skills) without touching your personal content.

## License

Internal use. See your organization's policies.
