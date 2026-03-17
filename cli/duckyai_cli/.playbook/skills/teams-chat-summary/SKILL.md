---
name: teams-chat-summary
description: 'Summarize Microsoft Teams chats and embed source links. Use when asked to summarize chats, recap Teams conversations, teams chat summary, weekly chat roundup, or fetch chat history. Always embeds deep links to original Teams messages.'
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Create
---

# Teams Chat Summary

Summarize Microsoft Teams **1:1 and group chats** via WorkIQ and produce vault-ready notes with **embedded deep links** to every referenced message. **Excludes Teams channel messages** — only person-to-person and group chats are processed. Supports both manual invocation and automated hourly cron sync with watermark tracking.

## When to Use This Skill

Activate when:
- User asks to summarize Teams chats (daily, weekly, or custom range)
- User asks for a chat recap or conversation history
- User wants chat-based action items or decisions extracted
- Any workflow that ingests Teams chat data into the vault
- Triggered automatically by the TCS cron agent (hourly)

## Prerequisites

- **WorkIQ MCP** must be available (`ask_work_iq` tool)
- Target vault folders must exist (`04-Periodic/Weekly/`, `04-Periodic/Daily/`)

## MCP Tools (duckyai-vault server)

### `getTeamsChatSyncState`
Returns the timestamp watermark of the last successful sync. Use this to avoid re-processing old chats.

**Returns**: JSON with `lastSynced` (ISO timestamp or null), `processedThreads` (array of thread IDs), `syncCount`.

### `updateTeamsChatSyncState`
Updates the watermark after a successful sync.

**Parameters**:
- `lastSynced` (required): ISO timestamp of this sync
- `processedThreadIds` (optional): Array of thread/conversation IDs processed

### `appendTeamsChatHighlights`
Appends a "## Teams Chat Highlights" section to the daily note. Idempotent — updates existing section if present. Also creates/updates person contact notes.

**Parameters**:
- `date` (optional): YYYY-MM-DD, defaults to today
- `highlights` (required): Markdown content for the section
- `people` (optional): Array of person names mentioned
- `personNotes` (optional): Array of `{ name, note }` to append to person contact files

## Watermark Tracking

The sync state is stored at `<vault_root>/.duckyai/state/tcs-last-sync.json`:

```json
{
  "lastSynced": "2026-03-09T20:00:00Z",
  "previousSynced": "2026-03-09T19:00:00Z",
  "processedThreads": ["thread-id-1", "thread-id-2"],
  "syncCount": 42,
  "updatedAt": "2026-03-09T20:00:05Z"
}
```

This prevents re-processing chats across cron runs. Always call `getTeamsChatSyncState` first and `updateTeamsChatSyncState` last.

## Step-by-Step Workflow

### Step 1: Determine Date Range

**Manual invocation**: Use the range the user explicitly specified (e.g., "January chats", "last week", "2026-03-01 to 2026-03-07"). Parse natural language into concrete `{start}` and `{end}` timestamps.

**Automated cron**: Call `getTeamsChatSyncState` to get the watermark.
- If `lastSynced` is `null`, use start of current day as `{start}`.
- Otherwise, use `lastSynced` as `{start}`.
- Use the current UTC timestamp as `{end}`.

### Step 2: Fetch Chats with Source Links

Query WorkIQ with an explicit request for **message-level deep links** and the **resolved date range**:

```
"Summarize all Teams 1:1 and group chats I had between {start} and {end} (inclusive).
STRICT DATE FILTER: Only include messages that occurred within this exact window — do NOT include anything before {start} or after {end}.
Only include person-to-person and group chats — do NOT include Teams channel messages.
For EACH topic or key message, include the Teams deep link URL.
For 1:1 chats, group highlights by person.
For group chats, include who said what to whom for each key point.
Include decisions and action items."
```

**CRITICAL**: The prompt MUST ask for deep links. WorkIQ returns them as numbered references like `[1](https://teams.microsoft.com/l/message/...)`. Extract and preserve every one.

**Strictness rule**: Regardless of how `{start}` / `{end}` were determined, always enforce them. **Discard any item WorkIQ returns that falls outside the window** — do not trust WorkIQ to filter perfectly; validate each item's timestamp before writing to the vault.

### Step 3: Parse Response and Extract Links

From the WorkIQ response, identify the **chat type** first, then extract accordingly:

**1:1 chats:**
1. Person name and dates of conversation
2. Topics discussed — each with its source link
3. Decisions made — each with its source link
4. Action items — with owner and source link

**Group chats:**
1. Group chat name
2. Key highlights — each with speaker name and source link
3. Decisions — attributed to the person who made them
4. Action items — with owner and source link

### Step 4: Update Vault

Call `appendTeamsChatHighlights` with the formatted highlights, people list, and person notes.

For action items, call `createTask` with appropriate title, description, and priority.

### Step 5: Update Watermark

Call `updateTeamsChatSyncState` with the current timestamp and any thread IDs.

## Output Format

### Daily Note — Teams Chat Highlights

Use **different formats based on chat type**:

- **1:1 chats** → H3 = participant name, H4 = topic/thread
- **Group chats** → H3 = group chat name (plain text, not a wiki link), flat bullet list of highlights with speaker attribution

```markdown
## Teams Chat Highlights

### [[Alice Smith]]
#### Project Standup
- Discussed sprint priorities and auth module ownership [🔗](https://teams.microsoft.com/l/message/...)
- Agreed on JWT over session tokens [🔗](https://teams.microsoft.com/l/message/...)
- [[Alice Smith]]: Handle auth module implementation
- [[Alice Smith]]: Share design doc by Wednesday

#### Code Review Follow-up
- Reviewed PR #142 feedback [🔗](https://teams.microsoft.com/l/message/...)
- [[Alice Smith]]: Address review comments and re-submit

### [[Bob Jones]]
#### Sprint Demo Prep
- Moved demo to Friday [🔗](https://teams.microsoft.com/l/message/...)
- [[Bob Jones]]: Prepare demo environment by Thursday

### API Design Working Group
- [[Alice Smith]] proposed switching to REST over gRPC [🔗](https://teams.microsoft.com/l/message/...)
- [[Bob Jones]] raised latency concerns with REST for high-frequency calls [🔗](https://teams.microsoft.com/l/message/...)
- [[Alice Smith]] → [[Bob Jones]]: suggested benchmarking both approaches before deciding [🔗](https://teams.microsoft.com/l/message/...)
- ✅ Decided to run a latency benchmark by end of week [🔗](https://teams.microsoft.com/l/message/...)
- [[Carol White]]: Write up a REST vs gRPC comparison doc by Friday
- [[Bob Jones]]: Set up benchmark environment by Wednesday
```

**Format rules:**
- **1:1 chats**:
  - H3 (`###`) = Participant name as wiki link `[[Full Name]]` — exclude "Me"/the user
  - H4 (`####`) = Chat context/thread topic
  - Action items prefixed with `[[Name]]:` indicating owner
- **Group chats**:
  - H3 (`###`) = Group chat name (plain text — no wiki link, it's not a person)
  - Flat bullet list — no H4 sub-headings
  - Each bullet prefixed with `[[Speaker Name]]` to show who said it
  - For directed remarks, use `[[Sender]] → [[Recipient]]:` format
  - Decisions prefixed with `✅`
  - Action items prefixed with `[[Name]]:` indicating owner
- Deep links appended to key point bullets where available

### Person Notes
Each person gets a dated entry under their `## Notes` section:
```markdown
- [2026-03-09] Discussed sprint priorities in standup; taking auth module
```

### Weekly Summary (manual invocation)
For weekly recaps, create `04-Periodic/Weekly/YYYY-Www Chat Summary.md` with full template:

```markdown
---
created: YYYY-MM-DD HH:MM:SS
type: weekly-chat-summary
date: YYYY-MM-DD
period: YYYY-MM-DD to YYYY-MM-DD
tags:
  - weekly
  - chat-summary
  - teams
---

# Week NN Chat Summary (Mon D – D, YYYY)

## Person Name
**Dates:** Mon D, D

### Topics
- **Topic description** [🔗](https://teams.microsoft.com/l/message/...)

### Decisions
- ✅ Decision text [🔗](https://teams.microsoft.com/l/message/...)

### Action Items
- [ ] @Owner: Action description [🔗](https://teams.microsoft.com/l/message/...)
```

## Link Format Rules

### Teams Deep Links (External)
Always use markdown link format with a 🔗 emoji:
```markdown
[🔗](https://teams.microsoft.com/l/message/19:...@thread.v2/1234567?context=...)
```

### Vault Wiki Links (Internal)
Follow `obsidian-links` skill conventions:
```markdown
[[Person Name]]
[[04-Periodic/Daily/2026-03-06]]
```

## Cron Schedule

Default: `0 * * * *` (every hour on the hour).
Customizable via `duckyai.yml`:

```yaml
- type: agent
  name: Teams Chat Summary (TCS)
  cron: "0 * * * *"        # Change to "0 9,12,17 * * 1-5" for 3x daily on weekdays
  output_path: 04-Periodic/Daily
  output_type: update_file
  enabled: true
```

## Quality Checklist

- [ ] Watermark checked before fetching (no re-processing)
- [ ] WorkIQ query included explicit `{lastSynced}` to `{now}` date range
- [ ] Each returned item's timestamp validated — items outside the window discarded
- [ ] Every topic bullet has a Teams deep link
- [ ] Every decision has a Teams deep link
- [ ] Every action item has a Teams deep link
- [ ] Vault wiki links verified to exist
- [ ] Daily notes updated (not duplicated)
- [ ] Person notes appended (not duplicated)
- [ ] Watermark updated after successful sync
- [ ] Names use wiki link format: `[[Person Name]]`
