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

The sync state is stored at `~/.duckyai/vaults/{vault_id}/state/tms-last-sync.json`:

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

### Step 1: Check Watermark
Call `getTeamsMeetingSyncState` to get the last sync timestamp.

### Step 2: Fetch Meetings
Query WorkIQ for meetings since the watermark. Request title, time, organizer, attendees, and any available notes/recap/transcript.

### Step 3: Summarize Each Meeting
For each meeting: summary, attendees, decisions, action items. Skip canceled/declined/trivial meetings.

### Step 4: Update Vault
- Call `appendTeamsMeetingHighlights` with formatted highlights
- Call `createTask` for action items
- Call `createMeeting` for substantial meetings

### Step 5: Update Watermark
Call `updateTeamsMeetingSyncState` with current timestamp and meeting IDs.

## Output Format

### Daily Note — Teams Meeting Highlights
```markdown
## Teams Meeting Highlights

### Sprint Planning (09:00 - 10:00)
**Organizer**: [[Alice Smith]]
**Attendees**: [[Alice Smith]], [[Bob Jones]], [[Carol White]]
**Summary**: Reviewed sprint backlog. Prioritized auth module and API refactor.

**Decisions**:
- Use JWT over session tokens
- Sprint demo moved to Friday

**Action Items**:
- [ ] @[[Bob Jones]]: Draft API schema by Wednesday
- [ ] @[[Carol White]]: Set up test environment
```

## Section Ordering in Daily Note

Meeting highlights are inserted **before** Chat highlights in the daily note:
1. `## Teams Meeting Highlights` (this skill)
2. `## Teams Chat Highlights` (teams-chat-summary skill)
3. `## End of Day`
