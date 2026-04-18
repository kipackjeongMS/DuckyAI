---
name: teams-meeting-summary
description: 'Summarize Microsoft Teams meetings and embed highlights into daily notes. Use when asked to summarize meetings, recap Teams calls, meeting summary, weekly meeting roundup, or fetch meeting history. Processes calendar meetings only — chats are handled by teams-chat-summary.'
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Create
---

# Teams Meeting Summary

Summarize Microsoft Teams meetings via WorkIQ and produce vault-ready notes. Supports both manual invocation and automated hourly cron sync with watermark tracking.

**Scope boundary**: This skill handles **calendar meetings** only. For chat messages, use the `teams-chat-summary` skill instead.

## When to Use This Skill

Activate when:
- User asks to summarize Teams meetings (daily, weekly, or custom range)
- User asks for a meeting recap or meeting notes
- User wants meeting-based action items or decisions extracted
- Any workflow that ingests Teams meeting data into the vault
- Triggered automatically by the TMS cron agent (hourly)

## Prerequisites

- **WorkIQ MCP** must be available (`ask_work_iq` tool)
- Target vault folders must exist (`04-Periodic/Daily/`, `02-People/Meetings/`)

## MCP Tools (duckyai-vault server)

### `getTeamsMeetingSyncState`
Returns the timestamp watermark of the last successful meeting sync.

**Returns**: JSON with `lastSynced` (ISO timestamp or null), `processedMeetings` (array of meeting IDs), `syncCount`.

### `updateTeamsMeetingSyncState`
Updates the watermark after a successful sync.

**Parameters**:
- `lastSynced` (required): ISO timestamp of this sync
- `processedMeetingIds` (optional): Array of meeting/event IDs processed

### `appendTeamsMeetingHighlights`
Appends a "## Teams Meeting Highlights" section to the daily note. Idempotent — updates existing section if present. Also creates/updates person contact notes.

**Parameters**:
- `date` (optional): YYYY-MM-DD, defaults to today
- `highlights` (required): Markdown content for the section
- `people` (optional): Array of person names mentioned
- `personNotes` (optional): Array of `{ name, note }` to append to person contact files

## Watermark Tracking

The sync state is stored at `<vault_root>/.duckyai/state/tms-last-sync.json`:

```json
{
  "lastSynced": "2026-03-09T20:00:00Z",
  "previousSynced": "2026-03-09T19:00:00Z",
  "processedMeetings": ["meeting-id-1", "meeting-id-2"],
  "syncCount": 12,
  "updatedAt": "2026-03-09T20:00:05Z"
}
```

## Step-by-Step Workflow

### Step 1: Determine Date Range

**Manual invocation**: Use the range the user explicitly specified (e.g., "January meetings", "last week", "2026-03-01 to 2026-03-07"). Parse natural language into concrete `{start}` and `{end}` timestamps.

**Automated cron**: Call `getTeamsMeetingSyncState` to get the watermark.
- If `lastSynced` is `null`, use start of current day as `{start}`.
- Otherwise, use `lastSynced` as `{start}`.
- Use the current UTC timestamp as `{end}`.

### Step 2: Fetch Meetings

Query WorkIQ for meetings within the **resolved date range**:

```
"List all Teams meetings I attended between {start} and {end} (inclusive) that have ALREADY ENDED.
STRICT DATE FILTER: Only include PAST meetings — meetings whose end time is before the current time. Do NOT include upcoming, in-progress, or future scheduled meetings.
Only include meetings whose start time falls within this exact window — do NOT include anything before {start} or after {end}.
For each meeting include: title, start/end time, organizer, attendees, and any available notes, recap, or transcript."
```

**Strictness rules**:
1. **Past-only**: Discard any meeting whose **end time** is after `current_utc` (injected in Agent Parameters). Graph API returns calendar events by time range overlap, which can include upcoming or in-progress meetings — you must validate each meeting's end time and drop anything not yet concluded.
2. **Window boundary**: Discard any meeting WorkIQ returns that falls outside the `{start}`–`{end}` window — do not trust WorkIQ to filter perfectly; validate each meeting's start time before writing to the vault.

### Step 3: Summarize Each Meeting
For each meeting: summary, attendees, decisions, action items. Skip canceled/declined/trivial meetings.

### Step 4: Update Vault
- Call `appendTeamsMeetingHighlights` with formatted highlights
- Call `createTask` for action items
- Call `createMeeting` for substantial meetings

### Step 5: Update Watermark
Call `updateTeamsMeetingSyncState` with current timestamp and meeting IDs.

## Output Format

### Per-Meeting Note (`02-People/Meetings/YYYY-MM-DD Title.md`)
Full detailed record using the Meeting template — discussion, decisions, action items.

### Daily Note — Teams Meeting Highlights
Lightweight references with short summaries and links to full notes:
```markdown
## Teams Meeting Highlights

### Sprint Planning (09:00 - 10:00)
- Reviewed sprint backlog and prioritized auth module and API refactor
- Decided to use JWT over session tokens
- Sprint demo moved to Friday
→ **Full notes**: [[2026-03-10 Sprint Planning]]

### 1:1 with Bob (14:00 - 14:30)
- Discussed API schema progress and testing blockers
- Bob will draft schema by Wednesday
→ **Full notes**: [[2026-03-10 1:1 with Bob]]
```

## Section Ordering in Daily Note

Meeting highlights are inserted **before** Chat highlights in the daily note:
1. `## Teams Meeting Highlights` (this skill)
2. `## Teams Chat Highlights` (teams-chat-summary skill)
3. `## End of Day`
