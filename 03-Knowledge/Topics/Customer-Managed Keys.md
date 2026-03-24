---
aliases: Customer-Managed Keys
tags:
  - cmk
  - encryption
  - azure
  - security
  - appconfig
related:
  - "[[Managed Identity]]"
  - "[[Network Security Perimeter]]"
---

## Summary

Customer-Managed Keys (CMK) is an Azure encryption feature allowing customers to own and control the encryption keys protecting their data in Azure services. Unlike Microsoft-managed keys, CMK enables customers to rotate, revoke, and audit key usage. AppConfig team actively monitors CMK-related incidents in production environments.

## Experiences

- [[02-People/Meetings/2026-03-17 scrum.azconfig.io#Discussion]] - CMK monitor issues flagged in production during AppConfig scrum; action item to monitor incident queue and escalate critical CMK issues
