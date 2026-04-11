---
aliases: CCOA
tags:
  - ccoa
  - deployment
  - change-control
  - microsoft
related:
  - "[[SDL Compliance]]"
  - "[[Feature Flags]]"
---

## Summary

CCOA (Change Control / Outage Avoidance) is a Microsoft deployment restriction window that limits or freezes production changes during high-risk periods (e.g., major holidays, major sporting events). Teams must plan releases around CCOA windows or implement workarounds such as partial regional deployment to exclude affected regions.

## Experiences

- [[04-Periodic/Daily/2026-03-18#Teams Chat Highlights]] - Discussed excluding CCOA regions from release; pipeline changes confirmed to support partial deployment as a workaround
- [[04-Periodic/Daily/2026-03-22#Teams Chat Highlights]] - Emergency CCOA triggered for sovereign cloud regions (UAE, Qatar, Israel); blocking release cancelled and custom exclusion parameters required for release pipeline
