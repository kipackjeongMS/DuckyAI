---
name: trigger-agent
description: 'Trigger a DuckyAI orchestrator agent. Use when asked to trigger an agent, run EIC, run GDR, trigger daily roundup, trigger enrichment, trigger topic update, or manually run an agent.'
---

# Trigger Agent

Manually trigger a DuckyAI orchestrator agent.

## Available Agents
- **EIC** — Enrich Ingested Content (enriches articles in 00-Inbox/)
- **GDR** — Generate Daily Roundup (daily summary)
- **TIU** — Topic Index Update (refresh topic indices)
- **EDM** — Extract Document to Markdown (convert PDF/DOCX)
- **TCS** - Teams Chat Summarization (summarize Teams chats)

## Instructions

1. If the user specified an agent, run `duckyai orchestrator trigger <AGENT>` (e.g., `duckyai orchestrator trigger EIC`)
2. If the user specified a file, add `--file <path>` (e.g., `duckyai orchestrator trigger EIC --file 00-Inbox/article.md`)
3. If no agent specified, run `duckyai orchestrator list-agents` first and ask which to trigger

Add `--json-output` flag if you need to parse the result programmatically.
