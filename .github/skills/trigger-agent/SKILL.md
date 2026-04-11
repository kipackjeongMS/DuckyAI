---
name: trigger-agent
description: 'Trigger a DuckyAI orchestrator agent. Use when asked to trigger an agent, run CEA, trigger enrichment, or manually run an agent.'
---

# Trigger Agent

Manually trigger a DuckyAI orchestrator agent.

## Available Agents
- **CEA** — Content Enrichment Agent (enriches articles in 00-Inbox/)
- **TCS** - Teams Chat Summarization (summarize Teams chats)
- **TMS** - Teams Meeting Summarization (summarize Teams meetings)

## Instructions

1. If the user specified an agent, run `duckyai orchestrator trigger <AGENT>` (e.g., `duckyai orchestrator trigger CEA`)
2. If the user specified a file, add `--file <path>` (e.g., `duckyai orchestrator trigger CEA --file 00-Inbox/article.md`)
3. If the user wants custom instructions passed to the agent, add `--agent-params '{"user_instructions": "<instructions>"}'`
4. If no agent specified, run `duckyai orchestrator list-agents` first and ask which to trigger

Add `--json-output` flag if you need to parse the result programmatically.
