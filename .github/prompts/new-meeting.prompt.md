---
mode: agent
description: Create a new meeting or 1:1 note
---

Create a meeting note or 1:1 record.

## Instructions

1. Ask the user:
   - Is this a **1:1** or a **general meeting**?
   - Date and time
   - Attendees (for meetings) or person (for 1:1)
   - Topic/agenda (optional)
   - Related project (optional)

2. **For 1:1s**, create at `02-People/1-on-1s/{YYYY-MM-DD} {Person Name}.md`:

```yaml
---
created: {today's date}
type: 1-on-1
person: "[[{Person Name}]]"
date: {YYYY-MM-DD}
tags:
  - 1-on-1
---
```

Content structure:
```markdown
# 1:1 with [[{Person Name}]] - {Date}

## Their Updates
- 

## My Updates
- 

## Discussion Topics
- 

## Action Items
- [ ] {owner}: {action}

## Notes
```

3. **For meetings**, create at `02-People/Meetings/{YYYY-MM-DD} {Topic}.md`:

```yaml
---
created: {today's date}
type: meeting
date: {YYYY-MM-DD}
time: {HH:MM}
attendees:
  - "[[{Person 1}]]"
  - "[[{Person 2}]]"
project: "[[{Project}]]"
tags:
  - meeting
---
```

Content structure:
```markdown
# {Meeting Topic} - {Date}

## Attendees
- [[{Person 1}]]
- [[{Person 2}]]

## Agenda
1. 
2. 

## Discussion
- 

## Decisions
- 

## Action Items
- [ ] [[{Person}]]: {action}

## Next Meeting
```

4. Check if person profiles exist in `02-People/Contacts/`
   - If not, offer to create them

5. Link to relevant projects, tasks, or previous meetings

6. Add meeting reference to today's daily note if it's today
