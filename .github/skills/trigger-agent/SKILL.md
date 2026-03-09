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

## Instructions

1. If the user specified an agent, call `triggerAgent` MCP tool with that abbreviation
2. If the user specified a file, pass it as the `file` parameter
3. If no agent specified, call `listAgents` first and ask which to trigger
