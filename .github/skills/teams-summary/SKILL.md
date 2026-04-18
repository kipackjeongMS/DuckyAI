---
name: teams-summary
description: 'Trigger TCS (Teams Chat Summary) or TMS (Teams Meeting Summary) agents with custom verbal instructions. Use when asked to run TCS, run TMS, summarize chats, summarize meetings, recap Teams conversations or meetings with custom filters like person, topic, date range.'
---

# Teams Summary (Custom Trigger)

Trigger the **TCS** (Teams Chat Summary) or **TMS** (Teams Meeting Summary) orchestrator agent with custom user instructions passed through to the agent's prompt.

## When to Use

- User says "run TMS to summarize the sprint planning meeting today"
- User says "run TCS to summarize chats with Alice this week"
- User says "summarize meetings about appconfig deployment held this week"
- User says "recap all chat messages with Bob this month"
- Any request to run TCS/TMS with specific filtering or focus

## How It Works

1. Parse the user's request to determine **which agent** (TCS or TMS)
2. Extract the **custom instructions** (the rest of the user's request)
3. Trigger the agent via CLI with `--agent-params` containing `user_instructions`

## Agent Selection Rules

| User mentions | Agent |
|---------------|-------|
| chat, chats, messages, conversation, DM | **TCS** |
| meeting, meetings, call, recap, standup, sprint planning, 1:1 | **TMS** |
| ambiguous (e.g., "summarize Teams from today") | Ask the user to clarify |

## Instructions

### Step 1: Determine Agent

From the user's request, identify whether they want **TCS** (chats) or **TMS** (meetings). If unclear, ask.

### Step 2: Extract Custom Instructions

Take the user's full verbal request and format it as the `user_instructions` value. Keep it as-is — the agent prompt will interpret it. Examples:
- "run TMS to summarize the sprint planning meeting today" → `user_instructions`: "summarize the sprint planning meeting held today"
- "run TCS to summarize chats with Alice about the deployment" → `user_instructions`: "summarize chats with Alice about the deployment"

### Step 3: Trigger Agent

Run the CLI command:

```bash
duckyai trigger <AGENT> --agent-params '{"user_instructions": "<extracted instructions>"}'
```

**Examples:**

```bash
# Summarize a specific meeting
duckyai trigger TMS --agent-params '{"user_instructions": "summarize the sprint planning meeting held today"}'

# Summarize chats with a specific person
duckyai trigger TCS --agent-params '{"user_instructions": "summarize all chat messages with Alice Smith this week"}'

# Summarize meetings about a topic
duckyai trigger TMS --agent-params '{"user_instructions": "summarize meetings about appconfig deployment held this week"}'

# Summarize today's chats only
duckyai trigger TCS --agent-params '{"user_instructions": "summarize all chats from today only"}'
```

### Step 4: Report Status

After triggering, inform the user:
- Which agent was triggered (TCS/TMS)
- What instructions were passed
- That the agent runs in the background and results will appear in the daily note

## Notes

- The `user_instructions` parameter overrides the agent's default watermark-based date range
- The agent will adapt its WorkIQ queries to match the user's intent
- Results are written to the daily note under `## Teams Chat Highlights` (TCS) or `## Teams Meeting Highlights` (TMS)
- The `--agent-params` flag accepts any valid JSON object; `user_instructions` is the key the agent prompt looks for
