---
name: prioritize-work
description: 'Prioritize current work items. Use when asked to prioritize, show my tasks, what should I work on, list active work, show priorities, or review workload.'
---

# Prioritize Work

Generate a prioritized view of all active work items.

## Instructions

1. Scan these locations for active items:
   - `01-Work/Tasks/` — status != done AND status != cancelled
   - `01-Work/Projects/` — status = active
   - `01-Work/Investigations/` — status = active

2. For each item extract: title, priority (P0–P3), status, due date, project

3. Present sorted and grouped:

```markdown
## 🔴 P0 — Critical (Drop Everything)
- [ ] {Task} — Due: {date} — {status}

## 🟠 P1 — High Priority (This Week)
- [ ] {Task} — Due: {date} — {status}

## 🟡 P2 — Medium Priority (This Sprint)
- [ ] {Task} — Due: {date} — {status}

## 🟢 P3 — Backlog
- [ ] {Task} — {status}

## 📋 Active Projects
- {Project} — {status} — Target: {date}

## 🔍 Active Investigations
- {Investigation} — {priority}
```

4. Highlight:
   - Overdue items (due date < today)
   - Blocked items
   - Items missing priority

5. Check today's daily note for committed items

6. Offer to:
   - Update priorities
   - Mark items done
   - Create new tasks
   - Add items to today's daily note
