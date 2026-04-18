---
name: add-documentation
description: 'Add documentation to the knowledge base. Use when asked to create docs, add a runbook, write a how-to, document architecture, add reference docs, or create knowledge articles.'
---

# Add Documentation

Create structured documentation in the vault knowledge base.

## Instructions

1. Gather from the user:
   - Document title
   - Category: `runbook`, `how-to`, `reference`, or `architecture`
   - Content (or have them paste it)
   - Related documents (optional)

2. Determine location:
   - General docs → `03-Knowledge/Documentation/`
   - Domain-specific → `03-Knowledge/Topics/`

3. Create the file with frontmatter:

```yaml
---
created: YYYY-MM-DD
modified: YYYY-MM-DD
type: documentation
category: runbook  # runbook | how-to | reference | architecture
related:
  - "[[Related Doc]]"
tags:
  - documentation
---
```

4. Use the correct section template per category:

**Runbook:** Overview → Prerequisites → Steps → Troubleshooting → Rollback

**How-To:** Goal → Steps → Verification → See Also

**Reference:** Summary → Details → Examples → Related

**Architecture:** Overview → Components → Data Flow → Decisions → Diagrams

5. Add `[[wiki links]]` to related concepts, people, and tasks
6. Suggest backlinks to add in related notes
