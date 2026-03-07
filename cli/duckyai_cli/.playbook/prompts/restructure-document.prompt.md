---
mode: agent
description: Restructure a user-written document with proper frontmatter and links
---

Take user-provided content and restructure it into proper vault format.

## Instructions

1. Ask the user to:
   - Paste their content, OR
   - Specify a file in `00-Inbox/` to restructure

2. Analyze the content to determine:
   - **Type:** task, investigation, documentation, meeting, person, or topic
   - **Appropriate location** in the vault structure
   - **Entities mentioned:** people, projects, tasks, concepts

3. Add appropriate frontmatter based on detected type (see schemas in copilot-instructions.md)

4. Restructure the content:
   - Add clear headers/sections
   - Convert mentioned names to `[[Person Name]]` links
   - Convert mentioned projects to `[[Project Name]]` links
   - Convert mentioned tasks to `[[Task Name]]` links
   - Add relevant tags

5. Present the restructured document to the user:
```markdown
## Restructured Document

**Detected type:** {type}
**Suggested location:** {path}
**New links created:** {list}

---
{Full restructured content with frontmatter}
---
```

6. Ask for confirmation before:
   - Creating the file at the suggested location
   - Creating any new linked notes (people, projects, etc.)
   - Adding backlinks to existing notes

7. After confirmation:
   - Create the main file
   - Offer to create stub files for new links
   - Suggest backlinks to add in related notes

## Link Detection Patterns

- Names (capitalized words): potential `[[Person]]` links
- "Project X", "the X project": potential `[[Project]]` links  
- "task", "TODO", "need to": potential task extraction
- Dates mentioned: potential meeting/event context
- Technical terms: potential `[[Topic]]` links in Knowledge
