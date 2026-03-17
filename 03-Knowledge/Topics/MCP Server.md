---
aliases: MCP Server
tags:
  - mcp
  - model-context-protocol
  - ai-agent
  - tool-calling
  - depa
related:
  - "[[DEPA 1CS Compliance Assessment]]"
---

## Summary

Model Context Protocol (MCP) Server is an open standard that enables AI language models to interact with external tools and data sources through a unified interface. In DEPA, MCP servers expose ADO and other service integrations as callable tools for AI deployment agents.

## Experiences

- [[04-Periodic/Daily/2026-03-16#ICM Workflow & MCP Server Investigation]] - MCP tools for ADO not invoked by agent despite being passed correctly; root cause was missing func_choice config; fixed by setting agent func_choice behavior to `auto` in yaml
