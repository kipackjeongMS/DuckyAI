---
name: orchestrator
description: 'Manage the DuckyAI orchestrator daemon. Use when asked to start the orchestrator, stop the orchestrator, check orchestrator status, start file watching, start the daemon, or manage automated agents.'
---

# Orchestrator Control

Manage the DuckyAI orchestrator daemon (file watcher + cron scheduler).

## Instructions

Use the appropriate MCP tool based on the user's intent:

- **Start**: Call `startOrchestrator` MCP tool
- **Stop**: Call `stopOrchestrator` MCP tool
- **Status** (or no specific action): Call `orchestratorStatus` MCP tool

Report the result clearly to the user.
