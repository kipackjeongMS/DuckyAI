---
title: "Topic Index Update"
abbreviation: "TIU"
category: "workflow"
created: "2025-12-06"
updated: "2026-01-04"
---
Perform Topic index updates, new Topic creation, and quality validation for any given documents.

## Input
- Input documents: Any markdown files
	- Single file or multiple files
	- Date range: `start_date` ~ `end_date` (for batch processing)
- Existing Topics: `03-Knowledge/Topics/` directory

## Output
- Updated Topic files
- New Topic files
- Processing log:

| Item | Details |
|------|---------|
| Topics Updated | count (list) |
| Topics Created | count (list) |
| Topics Skipped | count (reason) |
| Topics Verified | count (matched/total) |
| Frontmatter Fixed | count |

## Process
```
1. SOURCE ANALYSIS
   - Extract [[03-Knowledge/Topics/...]] links from input documents
   - Identify subjects not mapped to existing Topics
   - Batch-read input files first (in parallel)

2. TOPIC UPDATES
   A. Update existing Topics:
      - Dedup check: Skip if identical source entry already exists
      - Add new entries (one-line-per-source)
      - Experiences: Personal experiences (Journal, Lifelog)
      - Learnings: External learning (Articles, Clippings)
      - Validate and fix frontmatter format

   B. Create new Topics:
      - Wikipedia standard: Is it a universal concept?
      - Potential to accumulate 3+ entries
      - No overlap with existing Topics
      - Create with Topic Template + initial entries

3. QUALITY VALIDATION
   - Validate wiki link integrity
   - Remove duplicate entries
   - Validate frontmatter of all modified Topic files (auto-standardize on edit)
   - **Tip**: `obsidian unresolved` (broken links), `obsidian deadends` (no outgoing links), `obsidian orphans` (unreferenced files) — see `obsidian-cli` skill

4. VERIFICATION
   - Cross-verify Topic mentions in input documents against actual Topic file entries
   - Warn and add if any Topics are missing
   - Verification log: | Source | Topic Mentioned | Entry Added? |
```

## Entry Format
```markdown
- [[source#Section]] - One-line summary
```
- Must link down to section level: `[[source#Section]]`
- New topic cluster (3+ entries) → new subsection `### Topic Name (YYYY Month)`

## Frontmatter Standards
```yaml
---
aliases: Topic Name
tags:
  - tag1
  - tag2
related:
  - "[[Related Topic]]"
---

## Summary
```

**Prohibited**: `subtopics:`, `links:`, empty value fields

## Rules
- Use only content within the PKM (no external knowledge)
- Ignore `_` prefixed folders (`_Settings_/`, `_UserTest_/`, etc.) — system/test files should not be included as sources
- Link to original sources (not Topic indices)
- Read/update Topic files in parallel
- Process all mentioned Topics regardless of frequency — update even low-frequency Topics without omission
