# Changelog

All notable changes to the DuckyAI Template will be documented in this file.

## [Unreleased]

### Added
- **PR Review agent**: `/repo-cache` mount in `duckyai.yml.template` so cloned PR repos persist across runs. Warm `git fetch` (~1-3s) replaces cold `git clone` (~30-120s). Orchestrator auto-resolves `${repo_cache}` to `<vault>/.duckyai/repo-cache/`.
- **`vault-update` skill**: Step 5.5 patches existing users' `duckyai.yml` — adds the `/repo-cache` mount to the `PR Review (PR)` node (or inserts the node if missing).

## [1.0.0] — 2026-03-07

### Initial Release
- Vault folder structure (00-Inbox through 05-Archive)
- 9 Obsidian templates (Daily Note, Task, Project, Meeting, 1-on-1, Investigation, Person, Documentation, Weekly Review)
- MCP server with 9 automation tools (prepareDailyNote, logAction, createTask, etc.)
- 7 Copilot prompts (new-task, new-investigation, new-meeting, add-documentation, archive-task, prioritize-work, restructure-document)
- 3 Copilot skills (vault-setup, vault-update, code-review, make-skill-template)
- sync-repos.ps1 for documentation repo syncing
- Comprehensive copilot-instructions.md with schemas, conventions, and operations
- Interactive OOBE setup skill
- Safe update skill for pulling template changes
