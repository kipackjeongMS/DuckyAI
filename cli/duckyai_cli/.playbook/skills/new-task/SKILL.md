---
name: new-task
description: 'Create a new task. Use when asked to create a task, add a todo, make a work item, track an action item, or add something to the task list.'
---

# New Task

Create a prioritized task in the vault.

## Instructions

1. Gather from the user:
   - Task title/description
   - Priority: P0 (critical), P1 (this week), P2 (this sprint), P3 (backlog)
   - Due date (optional)
   - Related project (optional)

2. Create file at `01-Work/Tasks/{Task Title}.md`

3. Use frontmatter:

```yaml
---
created: YYYY-MM-DD
modified: YYYY-MM-DD
type: task
status: todo
priority: P2  # P0 | P1 | P2 | P3
due: YYYY-MM-DD  # omit if none
project: "[[Project Name]]"  # omit if none
tags:
  - task
---
```

4. Add a brief description section and any initial notes

5. If P0 or P1, offer to add it to today's daily note under `## Focus Today`

6. Suggest relevant links to projects, people, and related tasks

## Priority Reference

| Priority | Meaning | Timeline |
|----------|---------|----------|
| P0 | Critical — drop everything | Immediate |
| P1 | High — complete this week | This week |
| P2 | Medium — complete this sprint | This sprint |
| P3 | Low — backlog | When possible |
