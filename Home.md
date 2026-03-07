---
created: 2026-02-02
type: home
tags:
  - home
  - index
---

# 🦆 DuckyAI

Personal knowledge and task management system for **[USER_NAME]**.

---

## Quick Navigation

| Area | Description |
|------|-------------|
| [[00-Inbox/README\|📥 Inbox]] | Quick capture, triage items |
| [[01-Work/README\|💼 Work]] | Tasks, Projects, Investigations |
| [[02-People/README\|👥 People]] | Meetings, 1:1s, Contacts |
| [[03-Knowledge/README\|📚 Knowledge]] | Documentation, Topics |
| [[04-Periodic/README\|📅 Periodic]] | Daily & Weekly notes |
| [[05-Archive/README\|🗄️ Archive]] | Completed items |

---

## Today

![[04-Periodic/Daily/{{date:YYYY-MM-DD}}]]

---

## Active Work

### 🔴 P0 - Critical
```dataview
LIST
FROM "01-Work/Tasks"
WHERE priority = "P0" AND status != "done" AND status != "cancelled"
```

### 🟠 P1 - This Week
```dataview
LIST
FROM "01-Work/Tasks"
WHERE priority = "P1" AND status != "done" AND status != "cancelled"
LIMIT 5
```

### 📋 Active Projects
```dataview
LIST
FROM "01-Work/Projects"
WHERE status = "active"
```

---

## Copilot Prompts

Use these prompts with GitHub Copilot (Ctrl+I or Chat):

| Prompt | What it does |
|--------|--------------|
| `@workspace /new-task` | Create a new task with priority/deadline |
| `@workspace /new-investigation` | Start a technical investigation |
| `@workspace /add-documentation` | Add docs to knowledge base |
| `@workspace /prioritize-work` | Get prioritized work list |
| `@workspace /new-meeting` | Create meeting or 1:1 note |
| `@workspace /archive-task` | Archive completed task |
| `@workspace /restructure-document` | Format and link a document |

---

## Getting Started

1. **First time?** Read [[03-Knowledge/Documentation/Obsidian Plugin Setup|Obsidian Plugin Setup]]
2. **Create today's note:** Click the calendar or use `Ctrl+D`
3. **Add a task:** Use the new-task prompt or create in `01-Work/Tasks/`
4. **Quick capture:** Drop anything in `00-Inbox/` for later triage

---

## System Info

- **Owner:** [USER_NAME]
- **Role:** [USER_ROLE]
- **Stack:** [USER_TECHNOLOGIES]
- **Agent:** GitHub Copilot (see `.github/copilot-instructions.md`)
