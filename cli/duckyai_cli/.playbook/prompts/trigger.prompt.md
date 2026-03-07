---
mode: agent
description: Trigger a DuckyAI orchestrator agent (EIC, GDR, TIU, EDM)
---

Trigger a DuckyAI orchestrator agent using the `triggerAgent` MCP tool.

## Available Agents
- **EIC** — Enrich Ingested Content
- **GDR** — Generate Daily Roundup
- **TIU** — Topic Index Update
- **EDM** — Extract Document to Markdown

## Instructions

1. If the user specified an agent, call `triggerAgent` with that agent abbreviation
2. If the user specified a file, pass it as the `file` parameter
3. If no agent specified, call `listAgents` first and ask which one to trigger
