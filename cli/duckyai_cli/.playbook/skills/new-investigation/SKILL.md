---
name: new-investigation
description: 'Create a technical investigation. Use when asked to investigate, research a bug, deep-dive into an issue, create an investigation, or start a technical analysis.'
---

# New Investigation

Create a structured investigation for deep technical research.

## Instructions

1. Gather from the user:
   - Investigation topic/title
   - Initial hypothesis or question
   - Priority (P0–P3)
   - Related tasks or incidents (optional)

2. Create file at `01-Work/Investigations/{Topic}.md`

3. Use frontmatter:

```yaml
---
created: YYYY-MM-DD
modified: YYYY-MM-DD
type: investigation
status: active
priority: P0  # P0 | P1 | P2 | P3
related-tasks:
  - "[[Task Name]]"
tags:
  - investigation
---
```

4. Structure content:

```markdown
# {Investigation Title}

## Hypothesis
{What we think is happening}

## Background
{Context, why this matters}

## Findings
{Document discoveries as investigation progresses}

## Conclusions
{Final determination — fill when concluded}

## Action Items
- [ ] {Tasks spawned from this investigation}

## References
- {Links to docs, logs, incidents}
```

5. Link to related tasks, incidents, and documentation
6. If the investigation spawns tasks, offer to create them with the `new-task` skill
