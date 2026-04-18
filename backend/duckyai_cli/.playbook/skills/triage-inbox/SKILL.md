---
name: triage-inbox
description: 'Triage inbox items. Use when asked to triage inbox, clean inbox, sort inbox, categorize inbox, process inbox items, or organize 00-Inbox.'
---

# Triage Inbox

Categorize items in 00-Inbox/ into appropriate vault folders.

## Instructions

1. First call `triageInbox` MCP tool with `dryRun: true` to preview
2. Show the user what would be moved
3. Ask if they want to proceed
4. If yes, call again with `dryRun: false`
