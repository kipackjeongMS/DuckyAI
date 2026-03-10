---
name: orchestrator
description: 'Manage the DuckyAI orchestrator daemon. Use when asked to start the orchestrator, stop the orchestrator, check orchestrator status, start file watching, start the daemon, or manage automated agents.'
---

# Orchestrator Control

Manage the DuckyAI orchestrator daemon (file watcher + cron scheduler).

## Instructions

Run the appropriate CLI command based on the user's intent:

- **Start**: Run `duckyai orchestrator start`
- **Stop**: Run `duckyai orchestrator stop`
- **Status** (or no specific action): Run `duckyai orchestrator status`

Add `--json-output` flag if you need to parse the result programmatically.

Report the result clearly to the user.
