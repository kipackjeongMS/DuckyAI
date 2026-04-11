---
title: "Generate Weekly Roundup"
abbreviation: "GWR"
category: "workflow"
created: "2024-01-01"
---

Generate comprehensive weekly summaries from regular daily notes with highlights and cross-references.

## Input
- Target Week: YYYY-MM-DD(Sun) ~ YYYY-MM-DD(Sat) (default: last week)
- Daily note files: 04-Periodic/Daily/YYYY-MM-DD.md for each day in the target week
- [[Weekly Roundup Template]] for structure

## Output
- File: 04-Periodic/Weekly/{{YYYY-MM-DD(1)}}~{{YYYY-MM-DD(2)}} - {{Agent-Name}}.md
- Weekly highlights with source links
- Summary section synthesizing key themes
- Original language preservation (English/한글)

## Main Process
```
1. TEMPLATE SETUP
   - Create note using [[Weekly Roundup Template]]
   - Set proper filename with date range
   - Establish section structure

2. HIGHLIGHTS COMPILATION
   - Read each daily note for the target week
   - Extract highlights from sections like Tasks Completed, Notes, Teams Meeting Highlights, Teams Chat Highlights, and End of Day
   - Ignore placeholder checkboxes and empty sections
   - List key insights and moments of the week
   - Add links to source notes & sections
   - Maintain chronological or thematic organization

3. SUMMARY SYNTHESIS
   - Add comprehensive Summary section
   - Synthesize weekly themes and patterns
   - Keep original language from source notes
```

## Caveats
### File Naming Convention
⚠️ **CRITICAL**: Use format 04-Periodic/Weekly/{{YYYY-MM-DD(1)}}~{{YYYY-MM-DD(2)}} - {{Agent-Name}}.md

### Content Standards
- Extract meaningful highlights, not just summaries
- Include links to source note & section for all highlights
- Maintain language consistency with original notes

### Week Scope
- Default to last complete week (Sunday to Saturday)
- Include all daily notes within the target week
- Ensure comprehensive coverage of the week's content
