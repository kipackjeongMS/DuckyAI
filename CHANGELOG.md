# Changelog

All notable changes to the DuckyAI Template will be documented in this file.

## [Unreleased]

## [0.1.82] — 2026-06-03

### Removed
- **Chat feature removed entirely.** Eliminated the second-server architecture (port 52846 `chat_server.py`) that was the source of `/api/chat/*` 404 errors and PR-agent hang interactions. Deleted `chat_server.py`, `main/chat_cmd.py`, `shared/components/chat-panel.tsx`. Stripped all chat code from the Electron main/preload, Obsidian plugin bridge, App shell, TypewriterOverlay, shared types, and the `duckyai` CLI. The daemon is now a single orchestrator on port 52845.

### Added
- **WRS auto-wires on `duckyai update`**: added `Weekly Roundup Summary (WRS)` to `nodes-defaults.yml` so existing vaults receive the node + cron (5pm Fri) on the next update. WRS prompt is already synced via the standard prompt-sync path.
- **PR Review agent**: `/repo-cache` mount in `duckyai.yml.template` so cloned PR repos persist across runs. Warm `git fetch` (~1-3s) replaces cold `git clone` (~30-120s). Orchestrator auto-resolves `${repo_cache}` to `<vault>/.duckyai/repo-cache/`.
- **`vault-update` skill**: Step 5.5 patches existing users' `duckyai.yml` — adds the `/repo-cache` mount to the `PR Review (PR)` node (or inserts the node if missing).

## [0.1.81] — 2026-06-02

### Added
- **Weekly Roundup Summary (WRS) agent**: new aggregation agent that composes a high-signal weekly retro from daily notes, tasks, and meeting notes. Reads vault only — no external data sources.
- **MCP tools**: `gatherWeekData` (aggregates daily notes + tasks + meetings for a week) and `writeWeeklyRoundup` (writes the locked roundup structure to `04-Periodic/Weekly/YYYY-Www.md`).
- Consolidated `## Teams` section in the weekly roundup, grouping meetings (📅) and chats (💬) by date.

### Changed
- **TCS agent**: added Substance Filter (8 signal types) and Voice & Phrasing rule banning transcript voice ("I said / he said / we talked about"). Empty persons are omitted entirely.
- **TMS agent**: mirrored the same Substance Filter + outcome voice rules. Rewrote the legacy `Always-explicit subjects` rule that promoted speech-act phrasing. Empty meetings are omitted entirely.

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
