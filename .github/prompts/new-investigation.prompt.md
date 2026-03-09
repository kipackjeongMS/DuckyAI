---
mode: agent
description: Create a new technical investigation
---

Create a new investigation for deep technical research.

## Instructions

1. Ask the user for:
   - Investigation topic/title
   - Initial hypothesis or question
   - Priority (P0-P3)
   - Related tasks or incidents (optional)

2. Create the file at `01-Work/Investigations/{Topic}.md`

3. Use this frontmatter:
```yaml
---
created: {today's date YYYY-MM-DD}
modified: {today's date YYYY-MM-DD}
type: investigation
status: active
priority: {P0|P1|P2|P3}
related-tasks:
  - "[[{Task Name}]]"
tags:
  - investigation
---
```

4. Structure the content with these sections:
```markdown
# {Investigation Title}

## Hypothesis
{What we think is happening / what we're trying to understand}

## Background
{Context, why this matters}

## Findings
{Document discoveries here as investigation progresses}

## Conclusions
{Final determination - fill in when concluded}

## Action Items
- [ ] {Tasks spawned from this investigation}

## References
- {Links to relevant docs, logs, etc.}
```

5. Link to any related tasks, incidents, or documentation

6. If the investigation spawns tasks, offer to create them
