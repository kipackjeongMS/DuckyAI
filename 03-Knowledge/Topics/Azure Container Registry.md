---
aliases: Azure Container Registry
tags:
  - azure
  - acr
  - containers
  - infrastructure
related:
  - "[[Azure Container Apps]]"
  - "[[Managed Identity]]"
---

## Summary

Azure Container Registry (ACR) is a Microsoft Azure managed service for storing and managing OCI-compatible container images. In pipeline infrastructure, a best practice under SFI compliance is to parameterize ACR references rather than hardcoding them, improving portability, security posture, and long-term maintainability.

## Experiences

- [[04-Periodic/Daily/2026-03-18#Teams Chat Highlights]] - Reviewed SFI-related pipeline PRs removing hardcoded ACR references; parameterization approach discussed and approved
