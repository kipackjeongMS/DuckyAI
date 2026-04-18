---
name: restructure-document
description: 'Restructure a document into proper vault format. Use when asked to restructure content, format a note, convert inbox items, organize a document, or add frontmatter to a file.'
---

# Restructure Document

Take user-provided or inbox content and restructure it into proper vault format with frontmatter and links.

## Instructions

1. Get the content:
   - User pastes it, OR
   - User specifies a file in `00-Inbox/` to restructure

2. Analyze content to determine:
   - **Type:** task, investigation, documentation, meeting, person, or topic
   - **Location:** appropriate vault folder
   - **Entities:** people, projects, tasks, concepts mentioned

3. Add appropriate frontmatter based on detected type (task, investigation, documentation, meeting, person schemas from copilot-instructions.md)

4. Restructure the content:
   - Add clear headers/sections matching the type template
   - Convert mentioned names to `[[Person Name]]` wiki links
   - Convert mentioned projects to `[[Project Name]]` wiki links
   - Extract action items as `- [ ]` checkboxes
   - Add relevant tags

5. Present the restructured document:

```markdown
**Detected type:** {type}
**Suggested location:** {path}
**New links created:** {list}
---
{Full restructured content with frontmatter}
```

6. Ask for confirmation before:
   - Creating the file at the suggested location
   - Removing the original from `00-Inbox/` (if applicable)
   - Adding backlinks to existing notes

## Link Detection Patterns

- Capitalized names → potential `[[Person]]` links
- "Project X", "the X project" → potential `[[Project]]` links
- "task", "TODO", "need to" → potential task extraction
- Dates → potential meeting/event context
- Technical terms → potential `[[Topic]]` links
