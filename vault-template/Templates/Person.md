---
created: {{date:YYYY-MM-DD}}
type: person
role: 
team: 
email: 
tags:
  - person
---

# {{title}}

## Role
- **Title:** 
- **Team:** 
- **Reports to:** 

## Contact
- **Email:** 
- **Teams:** 

## Working Style
- 

## Topics / Expertise
- 

## 1:1 History
```dataview
LIST
FROM "02-People/1-on-1s"
WHERE contains(person, this.file.name)
SORT date DESC
LIMIT 5
```

## Meeting History
```dataview
LIST
FROM "02-People/Meetings"
WHERE contains(attendees, this.file.name)
SORT date DESC
LIMIT 5
```

## Notes
- 
