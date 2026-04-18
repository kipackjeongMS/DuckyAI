---
name: system-status
description: 'Show DuckyAI system status. Use when asked for status, system status, what is running, health check, or dashboard.'
---

# System Status

Show comprehensive DuckyAI system status.

## Instructions

1. Run `duckyai orchestrator status` to check daemon state
2. Run `duckyai orchestrator list-agents` to show available agents
3. Summarize: running state, agent count, next scheduled jobs

Add `--json-output` flag if you need to parse the results programmatically.
