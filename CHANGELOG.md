# Changelog

All notable changes to the DuckyAI Template will be documented in this file.

## [Unreleased]

## [0.1.87] — 2026-06-19

### Added
- **DNP carry-forward into `## Tasks`**: DNP now pulls unfinished `- [ ]` items from past daily notes (`## Focus Today`, `## Tasks`, and EOD `### Carry forward to tomorrow`) into **today's `## Tasks`** section each morning. The list is **smart-aggregated**: recent notes are scanned newest-first, the latest sighting of each item wins, and anything whose latest sighting is checked (`- [x]`) is dropped — so a task left unchecked on 6/17 but checked on 6/19 does NOT reappear. Items linked to a Tasks/ file with `status: done`/`cancelled` are also excluded. `writeDailyNoteFromPlan` writes carried items with identity-dedup against existing `## Tasks` lines, so re-runs never duplicate. Empty placeholder checkboxes are ignored. 4 new unit tests.

## [0.1.86] — 2026-06-19

### Removed
- **`## Carried from past` section**: removed entirely from daily notes. DNP no longer carries forward unchecked tasks into a new note; the section header is gone from all daily-note templates (`vault-template`, `.playbook/templates`, `.vault-template`, and the `setup.py` fallback). Backend wiring (`_build_daily_note_from_template`, `prepareDailyNote`, `writeDailyNoteFromPlan`) no longer generates or writes the section, so it cannot reappear. The `gatherOpenItems.carried_from_past` data source and its dedup logic remain (informational only). The EOD `### Carry forward to tomorrow` section is unaffected.

### Changed
- **DNP agent**: refocused to surface open PR reviews only. It now always sends `carried_items: []` to `writeDailyNoteFromPlan`.
- **TMS agent**: now summarizes **all meetings the user was invited to** (organizer or attendee), regardless of attendance — no-shows are no longer auto-skipped. Added an explicit **office hours exclusion** (drops meetings whose title denotes an office-hours / open drop-in / Q&A session).

### Fixed
- **pyproject version drift**: `backend/pyproject.toml` `[project].version` is now kept in sync with `version.json`, and both the contributing guide and the vault-publish skill document the dual bump. Prevents `pip install git+...` from building a stale wheel.

## [0.1.85] — 2026-06-05

### Fixed
- **DNP carry-forward dedup**: completed tasks no longer reappear in a new daily note's `## Carried from past` section. Previously, an item that appeared as `- [ ]` on Mon/Tue and `- [x]` on Wed would still be carried forward to Thu because the per-line scan never compared the same logical item across days. Rewrote `gatherOpenItems` and `prepareDailyNote` to use a unified `_collect_carry_forward` that scans recent notes **newest-first**, keeps the first sighting per normalized identity, and drops any item whose latest sighting is checked. Wiki-linked items (`[[Ship feature X]]` & `[[Ship feature X|alias]]`) now share an identity, and items linked to a Tasks/ file with `status: done`/`cancelled` are dropped as well. `forgotten_items` is deprecated to `[]` (key retained for API compat). 4 new unit tests cover the bug repro, multi-day dedup, task-status drop, and alias dedup.

### Changed
- **TCS channel-detection heuristic**: raised participant threshold from 15 → 30 so large group chats (often 16-29 people) are no longer mis-classified as channels and silently dropped.

## [0.1.84] — 2026-06-04

### Changed
- **TCS / TMS / TM action-item contract**: introduced an explicit `**Action**` tag convention so action items are unambiguous for the downstream Task Manager.
  - **TCS** and **TMS** now emit action items as `- **Action** · [Owner]({vault_root_rel}02-People/Contacts/Owner.md): <concrete action>` — `[Me](...)` when owned by the user, any other person otherwise. Format rules, voice/phrasing guidance, and before/after examples updated to match.
  - **TM** restructured Step 2: `**Action**`-tagged bullets are now the **primary** extraction trigger. Bullets owned by someone other than the user are explicitly skipped (no task created in `## Tasks`). The previous heuristic phrase-matching is retained as a legacy fallback for older notes.
- **TCS** also gained a "scan for action items, especially MINE" instruction so user-owned actions are reliably surfaced for TM.

## [0.1.83] — 2026-06-03

### Fixed
- **`duckyai update` crashed on Windows consoles** with `UnicodeEncodeError: 'charmap' codec can't encode characters in position 0-2` when printing the `─── Syncing vault ───` header. The crash happened *after* the self-update check but *before* `sync_vault()`, which silently prevented the chat-free plugin and the new WRS node from being synced into vaults. Fixed by reconfiguring `sys.stdout`/`sys.stderr` to UTF-8 at module load — the existing `─`, `✓`, `⚠` characters now render safely on cp1252 terminals.

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
