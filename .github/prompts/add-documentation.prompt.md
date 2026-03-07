---
mode: agent
description: Add a document to the knowledge base
---

Add documentation to the DuckyAI knowledge base.

## Instructions

1. Ask the user for:
   - Document title
   - Category: `runbook`, `how-to`, `reference`, or `architecture`
   - Content (or ask them to paste it)
   - Related documents (optional)

2. Determine the appropriate location:
   - General docs: `03-Knowledge/Documentation/`
   - Domain-specific: `03-Knowledge/Topics/`

3. Create the file with this frontmatter:
```yaml
---
created: YYYY-MM-DD  # Replace with today's date
modified: YYYY-MM-DD  # Replace with today's date
type: documentation
category: runbook  # Choose: runbook, how-to, reference, or architecture
related:
  - "[[Related Doc]]"
tags:
  - documentation
---
```

4. Structure the content appropriately:

**For Runbooks:**
```markdown
## Overview
## Prerequisites  
## Steps
## Troubleshooting
## Rollback
```

**For How-Tos:**
```markdown
## Goal
## Steps
## Verification
## See Also
```

**For Reference:**
```markdown
## Summary
## Details
## Examples
## Related
```

**For Architecture:**
```markdown
## Overview
## Components
## Data Flow
## Decisions
## Diagrams
```

5. Add forward links to related concepts, people, or tasks
6. Suggest backlinks to add in related notes
