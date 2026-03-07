**All generic rules are defined in @AGENTS.md 

Refer to that file for:
- Core Mission & Principles
- Prompts & Workflows
- Content Creation Requirements
- Link Format Standards
- File Management
- Core Operational Principles
- Properties & Frontmatter Standards
- Quality Standards

---
# Claude Code Specific Rules

## 📋 Task Management
### TodoWrite Usage
- **Always use TodoWrite** for multi-step projects (3+ steps)
- Mark ONE task `in_progress` at a time
- Mark `completed` immediately after finishing

## Version Control
### Commit Message Format for Workflows
- Use format: `Workflow: [Name] - YYYY-MM-DD`
- Only include affected files (don’t commit unaffected files)
- Include brief summary of changes
- Add emoji and Co-Authored-By signature
- Example:
```
Workflow: DIR - 2025-08-28

Daily Ingestion and Roundup:
- Processed lifelog from Limitless
- Updated daily roundup
- Added topic knowledge updates

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Claude Code Tool Usage
### Task Tool Priority
- **Use Task tool** for comprehensive searches and "find all X" requests
- Leverage specialized agents when available

### 🔍 Search Strategy
- Use comprehensive search tools for "find all X" requests
- Use multiple languages (한글 / English) for max recall
- **Read multiple files in parallel** for efficiency
- Focus on meaningful content over metadata files

## Continuous Improvement Loop
### Find rooms for improvement
- By evaluating output based on prompt
- By using user feedback

### Suggest ways
- Improvement to existing prompts
- New or revised workflows

## Additional Guidelines
### Workflow Completion
- Run all steps (i.e. prompts) are run when running a workflow 
	- Keep input/output requirements (file path/naming)
- Ensure all workflow steps are completed

### Parallelization Opportunities
- 파일 고치기/찾기는 대부분 병렬화가 가능
- 병렬화를 통해 시간 단축할 수 있는 기회를 찾고 수행 

### Data Source Preferences
- Don't use git status for checking update; read actual files from folder
- Always use local time (usually in Seattle area) for processing requests