---
title: "Ad-hoc Research within DUCKYAI"
abbreviation: "ARD"
category: "research"
created: "2024-01-01"
---
Generate comprehensive research summaries from DUCKYAI content for deep dive analysis and content creation.

## Input
- Research question or topic
- Source note with detailed instructions (if provided)
- Access to DUCKYAI vault content across all categories
- Optional web search requirements

## Output
- Research report in DUCKY03-Knowledge/Documentation directory
- File: {research topic} - {Agent}.md
- Use vault's default language (primaryLanguage in .gobi/settings.yaml) (except English source quotes)
- Quotes and links to source notes
- Further research questions and web search prompts
- Link & summary added to source note

## Main Process
```
1. RESEARCH SCOPE DEFINITION
   - Clarify research question if unclear
   - Identify key areas for investigation
   - Plan parallel research streams

2. COMPREHENSIVE SOURCE REVIEW
   - Start from index (Topics & Roundup)
   - Review Experience Notes (Journal)
   - Examine Learning Notes (Clippings)
   - Check My Own Work & Writings (Projects & Publish)
   - Use `obsidian search query="research term"` for cross-vault full-text search (see `obsidian-cli` skill)
   - Perform web search if needed

3. SYNTHESIS & DOCUMENTATION
   - Generate consistent summary with quotes & references
   - Include further research questions
   - Create prompts for deep web research
   - Link back to source note with summary
```

## Caveats
### Research Approach
⚠️ **CRITICAL**: Parallelize research streams to reduce turnaround time

### Source Utilization Strategy
- Start from knowledge index (Topics & Roundup)
- Delve into relevant learning & experience

### Output Standards
- Use vault's default language (except when quoting English sources)
- Include quotes and links to source notes
- Add further research questions for web investigation
- Create new note with suffix format: {research topic} - {Agent}
- Add link & summary to the original source note
