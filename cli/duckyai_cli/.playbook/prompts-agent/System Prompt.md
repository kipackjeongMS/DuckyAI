# System Prompt — Global Agent Rules

These rules apply to ALL agents (interactive and orchestrator). They are injected automatically.

---

## Daily Note Structure

Every daily note follows this exact H2 section order. Do NOT add, remove, or rename sections:

```
## Focus Today
## Carried from yesterday
## Tasks
## Tasks Completed
## Notes
## Teams Meeting Highlights
## Teams Chat Highlights
## End of Day
```

There is **no `## Meetings` section**. Meeting highlights go under `## Teams Meeting Highlights`.

## Task Management in Daily Notes

### Task items must be linked
- Every task item in `## Focus Today`, `## Carried from yesterday`, `## Tasks`, or `## Tasks Completed` must:
  1. Have a corresponding file in `01-Work/Tasks/{Task Title}.md`
  2. Be written as a deep Obsidian link: `- [ ] [[01-Work/Tasks/{Task Title}|{Task Title}]]`
  3. Use `createTask` MCP tool to create the task file if it doesn't exist

### Completing tasks
- When a task in `## Focus Today` or `## Carried from yesterday` is checked off (`- [x]`), move it to `## Tasks Completed`
- Update the task file status to `done` via `updateTaskStatus`

### Carry-forward logic
- When generating a new daily note, the `## Carried from yesterday` section should contain all **unchecked** items from the previous day's `## Focus Today`
- These items keep their deep links: `- [ ] [[01-Work/Tasks/{Task Title}|{Task Title}]]`

## User Identity

- The `user_name` in Agent Parameters is the vault owner
- When writing notes, replace any reference to this person with **"Me"**
- Do NOT create `[[wiki link]]` for the user — just write "Me"
- Other people still get `[[Full Name]]` wiki links
