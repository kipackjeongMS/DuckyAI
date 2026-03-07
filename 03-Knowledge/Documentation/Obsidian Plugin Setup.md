---
created: 2026-02-02
modified: 2026-02-02
type: documentation
category: how-to
related:
  - "[[Templates/Daily Note]]"
  - "[[Templates/Weekly Review]]"
tags:
  - documentation
  - setup
  - obsidian
---

# Obsidian Plugin Setup Guide

This guide walks you through setting up recommended Obsidian plugins for the DuckyAI vault.

## Required Plugins

### 1. Dataview (Community Plugin)

Enables the dashboard queries in README files.

**Install:**
1. Settings → Community plugins → Browse
2. Search "Dataview"
3. Install and Enable

**Settings:**
- Enable JavaScript Queries: ON (for advanced queries)
- Enable Inline Queries: ON

---

### 2. Templater (Community Plugin)

Enables advanced templates with date variables and automation.

**Install:**
1. Settings → Community plugins → Browse
2. Search "Templater"
3. Install and Enable

**Settings:**
- Template folder location: `Templates`
- Trigger Templater on new file creation: ON
- Enable Folder Templates (see below)

**Folder Templates Configuration:**
| Folder | Template |
|--------|----------|
| `01-Work/Tasks` | `Templates/Task.md` |
| `01-Work/Investigations` | `Templates/Investigation.md` |
| `01-Work/Projects` | `Templates/Project.md` |
| `02-People/Meetings` | `Templates/Meeting.md` |
| `02-People/1-on-1s` | `Templates/1-on-1.md` |
| `02-People/Contacts` | `Templates/Person.md` |
| `04-Periodic/Daily` | `Templates/Daily Note.md` |
| `04-Periodic/Weekly` | `Templates/Weekly Review.md` |

---

### 3. Periodic Notes (Community Plugin)

Automates daily and weekly note creation.

**Install:**
1. Settings → Community plugins → Browse
2. Search "Periodic Notes"
3. Install and Enable

**Daily Notes Settings:**
- Daily Note Template: `Templates/Daily Note.md`
- New File Location: `04-Periodic/Daily`
- Date Format: `YYYY-MM-DD`

**Weekly Notes Settings:**
- Enable Weekly Notes: ON
- Weekly Note Template: `Templates/Weekly Review.md`
- New File Location: `04-Periodic/Weekly`
- Date Format: `YYYY-[W]ww`

---

### 4. Calendar (Community Plugin)

Visual calendar for navigating daily/weekly notes.

**Install:**
1. Settings → Community plugins → Browse
2. Search "Calendar"
3. Install and Enable

**Settings:**
- Show week numbers: ON
- Start week on: Monday (adjust to preference)

**Usage:**
- Click a date to open/create that day's note
- Dots indicate days with notes
- Week numbers link to weekly reviews

---

## Optional Plugins

### Tasks (Community Plugin)

Enhanced task tracking with due dates, priorities, and queries.

**Install:** Search "Tasks" in Community plugins

**Usage:**
```markdown
- [ ] Task description 📅 2026-02-15 🔼
```

**Emoji meanings:**
- 📅 Due date
- 🔼 High priority
- 🔽 Low priority
- ✅ Completed date (auto-added)

---

### Quick Add (Community Plugin)

Create notes quickly with keyboard shortcuts.

**Suggested Macros:**
| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+T` | New Task |
| `Ctrl+Shift+M` | New Meeting |
| `Ctrl+Shift+D` | Open Today's Daily Note |

---

### Obsidian Git (Community Plugin)

Auto-backup vault to Git repository.

**Settings:**
- Auto backup interval: 10 minutes
- Auto pull on open: ON
- Commit message: `vault backup: {{date}}`

---

## Core Plugin Settings

These are built-in Obsidian features:

### Templates (Core Plugin)
- Enable: ON
- Template folder location: `Templates`

### Daily Notes (Core Plugin)
- Disable this if using Periodic Notes plugin (avoid conflicts)

### Backlinks (Core Plugin)
- Enable: ON
- Show backlinks in document: ON (optional)

### Outgoing Links (Core Plugin)
- Enable: ON

### Tags (Core Plugin)
- Enable: ON

---

## Recommended Hotkeys

| Action | Suggested Hotkey |
|--------|------------------|
| Open daily note | `Ctrl+D` |
| Insert template | `Ctrl+T` |
| Open quick switcher | `Ctrl+O` |
| Search | `Ctrl+Shift+F` |
| Toggle left sidebar | `Ctrl+\` |
| Open command palette | `Ctrl+P` |

---

## Appearance Settings

### Suggested Theme
- Default or "Minimal" theme for clean look

### Editor Settings
- Readable line length: ON
- Show frontmatter: ON
- Show line numbers: OFF (cleaner)

---

## First-Time Setup Checklist

- [ ] Install Dataview
- [ ] Install Templater and configure folder templates
- [ ] Install Periodic Notes and configure paths
- [ ] Install Calendar
- [ ] Configure hotkeys
- [ ] Create first daily note to test
- [ ] (Optional) Set up Obsidian Git for backups

---

## Troubleshooting

### Templates not auto-applying
- Check Templater folder template settings
- Ensure template file exists in `Templates/`

### Dataview queries showing errors
- Ensure Dataview is enabled
- Check frontmatter syntax (YAML must be valid)

### Daily notes going to wrong folder
- Disable core Daily Notes plugin
- Use only Periodic Notes plugin
