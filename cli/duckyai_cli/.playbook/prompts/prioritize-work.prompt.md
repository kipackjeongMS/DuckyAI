---
mode: agent
description: Get a prioritized list of current work items
---

Generate a prioritized view of all active work.

## Instructions

1. Scan these locations for active items:
   - `01-Work/Tasks/` - all files where status != done and status != cancelled
   - `01-Work/Projects/` - all files where status = active
   - `01-Work/Investigations/` - all files where status = active

2. For each item, extract:
   - Title (filename)
   - Priority (P0, P1, P2, P3)
   - Status
   - Due date (if set)
   - Project association (if any)

3. Sort and group the results:

```markdown
## 🔴 P0 - Critical (Drop Everything)
- [ ] {Task} - Due: {date} - {status}

## 🟠 P1 - High Priority (This Week)
- [ ] {Task} - Due: {date} - {status}

## 🟡 P2 - Medium Priority (This Sprint)
- [ ] {Task} - Due: {date} - {status}

## 🟢 P3 - Backlog
- [ ] {Task} - {status}

## 📋 Active Projects
- {Project} - {status} - Target: {date}

## 🔍 Active Investigations
- {Investigation} - {priority}
```

4. Highlight any:
   - Overdue items (due date < today)
   - Blocked items
   - Items without priority set

5. Check today's daily note for any committed items

6. Offer to:
   - Update priorities
   - Mark items as done
   - Create new tasks
   - Add items to today's daily note
