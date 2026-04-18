---
mode: agent
description: Create a new task with priority and optional deadline
---

Create a new task in the DuckyAI vault.

## Instructions

1. Ask the user for:
   - Task title/description
   - Priority (P0, P1, P2, P3) - explain if needed
   - Due date (optional)
   - Related project (optional)

2. Create the task file at `01-Work/Tasks/{Task Title}.md`

3. Use this frontmatter:
```yaml
---
created: {today's date YYYY-MM-DD}
modified: {today's date YYYY-MM-DD}
type: task
status: todo
priority: {P0|P1|P2|P3}
due: {YYYY-MM-DD or omit if none}
scheduled: 
project: "[[{Project Name}]]" or omit
tags:
  - task
---
```

4. Add a brief description section and any initial notes

5. If this is P0 or P1, offer to add it to today's daily note

6. Suggest relevant links (projects, people, related tasks)

## Priority Reference
- **P0:** Critical, drop everything. Production impact or blocking others.
- **P1:** High priority, complete this week.
- **P2:** Medium priority, complete this sprint/cycle.
- **P3:** Low priority, backlog.
