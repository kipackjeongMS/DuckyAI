---
name: new-meeting
description: 'Create a meeting or 1:1 note. Use when asked to create meeting notes, log a 1:1, record a meeting, create 1-on-1 notes, or document a discussion.'
---

# New Meeting

Create a meeting note or 1:1 record in the vault.

## Instructions

1. Determine type:
   - **1:1** → `02-People/1-on-1s/{YYYY-MM-DD} {Person Name}.md`
   - **Meeting** → `02-People/Meetings/{YYYY-MM-DD} {Topic}.md`

2. Gather from the user:
   - Date and time
   - Attendees (meeting) or person (1:1)
   - Topic/agenda (optional)
   - Related project (optional)

3. **For 1:1s**, use frontmatter:

```yaml
---
created: YYYY-MM-DD
type: 1-on-1
person: "[[Person Name]]"
date: YYYY-MM-DD
tags:
  - 1-on-1
---
```

Sections: Their Updates → My Updates → Discussion Topics → Action Items → Notes

4. **For meetings**, use frontmatter:

```yaml
---
created: YYYY-MM-DD
type: meeting
date: YYYY-MM-DD
time: HH:MM
attendees:
  - "[[Person 1]]"
  - "[[Person 2]]"
project: "[[Project]]"
tags:
  - meeting
---
```

Sections: Attendees → Agenda → Discussion → Decisions → Action Items → Next Meeting

5. Check if person profiles exist in `02-People/Contacts/` — offer to create if missing
6. Link to relevant projects, tasks, or previous meetings
7. Add meeting reference to today's daily note if meeting is today
