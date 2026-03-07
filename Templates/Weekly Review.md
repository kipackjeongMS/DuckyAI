---
created: {{date:YYYY-MM-DD}}
type: weekly
week: {{date:YYYY-[W]ww}}
start: {{date:YYYY-MM-DD|monday}}
end: {{date:YYYY-MM-DD|friday}}
tags:
  - weekly
---

# Week {{date:ww, YYYY}}

## Goals This Week
- [ ] 

## Key Accomplishments
- 

## Tasks Completed
```dataview
TASK
FROM "01-Work/Tasks"
WHERE completed >= this.start AND completed <= this.end
```

## Meetings & 1:1s
```dataview
LIST
FROM "02-People"
WHERE date >= this.start AND date <= this.end
SORT date ASC
```

## Blockers / Challenges
- 

## Learnings
- 

## Next Week
- [ ] 

## Notes

