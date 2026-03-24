---
aliases: Managed Identity
tags:
  - managed-identity
  - azure
  - authentication
  - deployment
related:
  - "[[RBAC]]"
---

## Summary

Managed Identity is an Azure Active Directory feature that provides Azure services with an automatically managed identity, eliminating the need for credentials in code. It enables secure service-to-service authentication without storing secrets, commonly used for deployment pipelines and service access authorization.

## Experiences

- [[04-Periodic/Daily/2026-03-16#Seung Moon]] - Managed identity deployment issue surfaced; switching code encountered permission errors with deployment MI, requiring access permission troubleshooting
