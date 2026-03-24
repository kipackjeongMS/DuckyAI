---
aliases: DNS Delegation
tags:
  - dns
  - networking
  - infrastructure
  - depa
related:
  - "[[RBAC]]"
---

## Summary

DNS Delegation is a networking mechanism that assigns authority over a DNS subdomain to a designated set of name servers, enabling independent management of subdomain resolution separate from the parent zone. In DEPA, DNS delegation is evaluated as an ingress architecture model to enforce Corpnet-only access constraints.

## Experiences

- [[02-People/Meetings/2026-03-19 DEPA Ingress and DNS Discussion#Discussion]] - DNS delegation model chosen to support Corpnet-only access; Seung Moon assigned to finalize delegation design documentation
