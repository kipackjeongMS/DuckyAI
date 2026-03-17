---
aliases: Admin Consent
tags:
  - admin-consent
  - authentication
  - azure-ad
  - depa
related:
  - "[[OBO Flow]]"
  - "[[RBAC]]"
---

## Summary

Admin Consent is a Microsoft Entra ID (Azure AD) mechanism that grants tenant-wide delegated or application permissions on behalf of all users in an organization. In DEPA, the admin consent requirement is a recurring blocker for enabling Graph API permissions, ADO delegated access, and security group-based access controls.

## Experiences

- [[02-People/Meetings/2026-03-06 DEPA Web UI Design Review#3. Authentication & Permissions]] - No Graph/ADO API permissions configured in DEPA Web UI due to admin consent blocker; ADO API calls proxied through backend as workaround
- [[04-Periodic/Daily/2026-03-06#Chats]] - Haiyi Wen flagged admin consent as ongoing blocker alongside risk analysis parameter persistence and FE/BE local testing limitations
