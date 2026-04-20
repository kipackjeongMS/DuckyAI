---
name: archive-task
description: 'Archive a completed or cancelled task. Use when asked to archive a task, mark task done, close a task, cancel a task, or move task to archive.'
---

# Archive Task

Move a completed or cancelled task to the archive.

## Instructions

1. Gather from the user:
   - Which task to archive (name or let them specify)
   - Final status: `done` or `cancelled`
   - Completion/cancellation notes (optional)

2. Locate the task in `01-Work/Tasks/`

3. Update frontmatter:
   - Set `modified: {today}`
   - Set `status: done` or `status: cancelled`

4. Add completion/cancellation section:
   - Done: `## Completion\nCompleted on YYYY-MM-DD. {notes}`
   - Cancelled: `## Cancelled\nCancelled on YYYY-MM-DD. Reason: {reason}`

5. Move file from `01-Work/Tasks/` to `05-Archive/`

6. Update references:
   - Check linked projects → update their task lists
   - Check recent daily notes → note the completion
   - Check investigations that referenced this task

7. Confirm with the user:
   - Status (done/cancelled)
   - New location in `05-Archive/`
   - List of updated references

8. If task was part of a project, offer to:
   - View remaining project tasks
   - Create follow-up tasks
