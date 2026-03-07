---
created: 2026-02-06
modified: 2026-02-06
type: documentation
category: reference
related:
  - "[[Obsidian Plugin Setup]]"
tags:
  - documentation
  - mcp
  - automation
---

# DuckyAI MCP Server

A Model Context Protocol (MCP) server that provides automated vault management tools for GitHub Copilot.

## Location

```
DuckyAI/mcp-server/
├── src/index.ts    # Main server code
├── dist/           # Compiled JavaScript
├── package.json    # Dependencies
└── tsconfig.json   # TypeScript config
```

## Available Tools

### Daily & Logging Tools

#### prepareDailyNote

Creates today's daily note with carry-forward items from the previous day.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | No | Date in YYYY-MM-DD format (defaults to today) |

**Behavior:**
- Creates `04-Periodic/Daily/YYYY-MM-DD.md`
- Finds the most recent previous daily note
- Extracts uncompleted carry-forward items (`- [ ]` lines)
- Populates "Carried from yesterday" section
- Skips if file already exists

---

#### logPRReview

Logs a PR review or comment to today's daily note.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `person` | string | Yes | PR author's name (e.g., "Shi Chen") |
| `prNumber` | string | Yes | PR number (e.g., "14653251") |
| `prUrl` | string | Yes | Full PR URL |
| `description` | string | Yes | Brief description of the PR |
| `action` | enum | Yes | `"reviewed"` or `"commented"` |

**Behavior:**
- Adds entry to "Tasks Completed" section
- Format: `- [x] Reviewed [[Person]]'s PR - [PR XXXXXX](url) - description`
- Creates contact file if person doesn't exist
- Requires daily note to exist first

---

#### logAction

Logs a completed action to today's daily note.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | Description of what was completed |
| `addToCarryForward` | string | No | Optional follow-up item to add |

**Behavior:**
- Adds entry to "Tasks Completed" section
- Optionally adds follow-up to "Carry forward to tomorrow"
- Requires daily note to exist first

---

### Task Management Tools

#### createTask

Creates a new task in `01-Work/Tasks/`.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | string | Yes | Task title (used as filename) |
| `description` | string | No | Task description |
| `priority` | enum | No | `P0`, `P1`, `P2` (default), `P3` |
| `project` | string | No | Related project name |
| `due` | string | No | Due date in YYYY-MM-DD format |

**Behavior:**
- Reads `Templates/Task.md` for structure
- Sets frontmatter values from parameters
- Creates file with proper naming

---

#### updateTaskStatus

Updates the status of an existing task.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | string | Yes | Task filename (without .md) |
| `status` | enum | Yes | `todo`, `in-progress`, `blocked`, `done`, `cancelled` |

**Behavior:**
- Updates `status` in frontmatter
- Updates `modified` date automatically

---

#### archiveTask

Moves a completed/cancelled task to `05-Archive/`.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | string | Yes | Task filename (without .md) |
| `status` | enum | No | Final status: `done` (default) or `cancelled` |

**Behavior:**
- Updates `status` and `modified` in frontmatter
- Moves file from `01-Work/Tasks/` to `05-Archive/`
- Deletes original file

---

### Meeting Tools

#### createMeeting

Creates a new meeting note in `02-People/Meetings/`.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | string | Yes | Meeting topic/title |
| `date` | string | No | Meeting date (defaults to today) |
| `time` | string | No | Meeting time in HH:MM format |
| `attendees` | string[] | No | List of attendee names |
| `project` | string | No | Related project name |

**Behavior:**
- Reads `Templates/Meeting.md` for structure
- Filename: `YYYY-MM-DD Title.md`
- Creates contact files for new attendees
- Links attendees in frontmatter and body

---

#### create1on1

Creates a new 1:1 meeting note in `02-People/1-on-1s/`.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `person` | string | Yes | Person's name |
| `date` | string | No | Meeting date (defaults to today) |

**Behavior:**
- Reads `Templates/1-on-1.md` for structure
- Filename: `YYYY-MM-DD Person Name.md`
- Creates contact file if person doesn't exist
- Links person in frontmatter

---

### Review Tools

#### prepareWeeklyReview

Creates a weekly review note with aggregated data from daily notes.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `week` | string | No | Week in YYYY-Www format (defaults to current week) |

**Behavior:**
- Reads `Templates/Weekly Review.md` for structure
- Calculates Monday-Friday of the specified week
- Aggregates completed tasks from daily notes in that range
- Populates "Key Accomplishments" section automatically

## Template Consistency

The MCP server reads templates directly from the `Templates/` folder, ensuring consistency between:
- Manual note creation in Obsidian
- MCP-generated notes
- Copilot instructions

**Single source of truth:** Edit `Templates/*.md` to change note structure everywhere.

Supported template variables:
| Variable | Description | Example Output |
|----------|-------------|----------------|
| `{{date:YYYY-MM-DD}}` | Formatted date | 2026-02-06 |
| `{{date:dddd, MMMM D, YYYY}}` | Long date | Friday, February 6, 2026 |
| `{{date:YYYY-[W]ww}}` | ISO week | 2026-W06 |
| `{{title}}` | Note title | My Task Name |
| `{{date:YYYY-MM-DD\|monday}}` | Week's Monday | 2026-02-03 |
| `{{date:YYYY-MM-DD\|friday}}` | Week's Friday | 2026-02-07 |

---

## Development

### Building

```powershell
cd DuckyAI/mcp-server
npm install
npm run build
```

### Rebuilding after changes

```powershell
npm run build
```

Then restart VS Code or run **MCP: Restart Server** → **duckyai-vault**

### Watch mode

```powershell
npm run dev
```

## VS Code Configuration

The MCP server is configured in VS Code settings. Configuration lives in:
- User settings: `%APPDATA%\Code - Insiders\User\settings.json`
- Or workspace: `.vscode/settings.json`

Example configuration:
```json
{
  "mcp": {
    "servers": {
      "duckyai-vault": {
        "command": "node",
        "args": ["C:/Users/.../DuckyAI/mcp-server/dist/index.js"]
      }
    }
  }
}
```

## Troubleshooting

### Tools not appearing
1. Check VS Code Output panel → MCP
2. Restart MCP server: `Ctrl+Shift+P` → **MCP: Restart Server**
3. Rebuild: `npm run build`

### Line ending issues (Windows)
The server normalizes `\r\n` to `\n` before regex matching. If edits fail silently, check that the normalization is working.

### Daily note not found
Run `prepareDailyNote` first, or manually create `04-Periodic/Daily/YYYY-MM-DD.md`

## Future Enhancements

- [ ] `createInvestigation` - Create investigation files
- [ ] `createProject` - Create project files with timeline
- [ ] `logICM` - Log incident references with consistent formatting
- [ ] `linkBlocker` - Mark task blocked and reference blocker
- [ ] `searchTasks` - Search tasks by status, priority, or project
