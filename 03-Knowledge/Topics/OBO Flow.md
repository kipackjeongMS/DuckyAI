---
aliases: OBO Flow
tags:
  - authentication
  - obo
  - azure-ad
  - depa
related:
  - "[[DEPA 1CS Compliance Assessment]]"
  - "[[SDL Compliance]]"
---

## Summary

On-Behalf-Of (OBO) flow is an OAuth 2.0 authentication pattern where a service acts on behalf of a user by exchanging tokens. In DEPA, the OBO flow is critical for accessing Azure DevOps data with user-delegated permissions but is currently blocked by admin consent and platform constraints.

## Experiences

- [[02-People/Meetings/2026-03-9 Deployment Agent Weekly Meeting#OBO (On-Behalf-Of) Flow Blocker (Kipack Jeong)]] - OBO blocked by admin consent; proposed ADO pre-authorization for delegated permissions as workaround
- [[02-People/Meetings/2026-03-9 Deployment Agent Weekly Meeting#Milestone & Release Planning]] - Manual deployment adopted due to OBO blocker; full automation deferred to next milestone
- [[04-Periodic/Daily/2026-03-11#Carried from yesterday]] - Follow up on OBO Flow App Preauthorization pending ADO response
