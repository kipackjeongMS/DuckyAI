---
mode: agent
description: Archive a completed or cancelled task
---

Archive a task that is done or no longer needed.

## Instructions

1. Ask the user:
   - Which task to archive (or let them specify)
   - Final status: `done` or `cancelled`
   - Any completion notes (optional)

2. Locate the task in `01-Work/Tasks/`

3. Update the task's frontmatter:
```yaml
---
modified: YYYY-MM-DD  # Replace with today's date
status: done  # or cancelled
---
```

5. If status is `done`, add a completion note:
```markdown
## Completion
Completed on YYYY-MM-DD. Notes about resolution here.
```

5. If status is `cancelled`, add cancellation reason:
```markdown
## Cancelled
Cancelled on YYYY-MM-DD. Reason: why it was cancelled.
```

6. Move the file from `01-Work/Tasks/` to `05-Archive/`

7. Update related items:
   - Check if task was linked from a project → update project's task list
   - Check if task was in today's/recent daily notes → note completion there
   - Check for any investigations that referenced this task

8. Confirm the archive with the user:
```markdown
✅ Archived: Task Name
- Status: done/cancelled
- Moved to: 05-Archive/Task Name.md
- Updated references in: (list of updated files)
```

9. If task was part of a project, offer to:
   - View remaining tasks in the project
   - Create follow-up tasks if needed
