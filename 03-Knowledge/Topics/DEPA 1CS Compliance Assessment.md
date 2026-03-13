---
created: 2026-03-11 18:45:00
title: DEPA 1CS Compliance Assessment
tags:
  - compliance
  - 1cs
  - depa
  - security
  - ai-telemetry
project: "[[Depo]]"
---

## Summary

1CS compliance assessment for DEPA (Azure DevOps AI Deployment Agents). Two KPIs were evaluated: **Code Signature Verification** and **AI System Telemetry Logging**. The code signature KPI does not apply to DEPA's core backend, while the AI telemetry KPI applies and has significant gaps.

## KPI 1: Code Signature Verification on Downloaded Content

### Applicability: 🟢 Does NOT Apply (to core backend)

This requirement applies to products that download executable content or security-sensitive configuration state. DEPA's core backend services (excluding the VS Code extension and deploy-backend.ps1 setup script):

- **NuGet packages** — standard .NET build-time restore, handled by NuGet's built-in signing
- **.NET binaries produced by CI/CD** — OneBranch pipeline has `linuxEsrpSigning: true` (ESRP signing)
- **Azure Key Vault certs** — fetched via Azure SDK + RBAC, not executable content
- **HTTP API calls** (ADO, ICM, etc.) — JSON data exchange, not executable content

The core backend does not download or install executable content at runtime. It is a web API service that processes data via API calls.

> **Note**: The VS Code extension and `deploy-backend.ps1` were excluded from scope per team decision. If those are re-evaluated in the future, they would need signature verification.

## KPI 2: AI System Telemetry Logging

### Applicability: 🔴 APPLIES — DEPA is an AI System

DEPA uses Azure OpenAI (GPT-4.1-mini, o4-mini, GPT-5-mini) with Semantic Kernel agents that process prompt/response interactions. This KPI requires logging all AI System activity for each user interaction.

### What DEPA Already Has

| Area | Status | Details |
|---|---|---|
| Application Insights + OpenTelemetry | ✅ | Configured in `ServiceDefaults/Extensions.cs` |
| Token usage logging | ✅ | Per-agent in `TokenUsageTracker.cs` (prompt, completion, reasoning, cached) |
| Agent/operation type | ✅ | PR, Test, ICM, SafeFly, EV2 analysis types logged |
| Semantic Kernel OTel metrics | ✅ | `AddMeter("Microsoft.SemanticKernel*")` auto-captured |
| CreationTime | ✅ | FirstInvocationUtc / LastInvocationUtc in TokenUsageSummary |
| Authentication | ✅ | MISE-based service authentication configured |

### Gaps — Required Fields Not Yet Logged

| Required Field | Status | Gap Description |
|---|---|---|
| **UserID** (AAD identity) | ❌ Missing | MISE auth exists but user identity not captured in telemetry |
| **ClientIPAddress** | ❌ Missing | Not logged from `HttpContext.Connection.RemoteIpAddress` |
| **ClientRegion** | ❌ Missing | Not derived from client IP |
| **Workload name** | ❌ Missing | No "DEPA" workload identifier in logs |
| **ModelTransparencyDetails** | ⚠️ Partial | Model deployment name exists (`AiFoundryConfigs.cs`), full schema (provider + model + API version) not populated |
| **ThreadID** | ⚠️ Partial | Session-scoped, not persistent message-level |
| **Messages** (PromptID, PromptSize, ResponseID, ResponseSize) | ❌ Missing | Token counts exist but not individual message IDs/byte sizes |
| **AccessedResources** (URIs + sensitivity labels) | ❌ Missing | Tool calls tracked but not resource-level details |
| **AISystemPlugin** (name, ID, version) | ⚠️ Partial | Agent names logged, no formal plugin schema |
| **Purview Audit integration** | ❌ Missing | Only App Insights today |
| **JIT access for SOC analysts** | ❌ Missing | Not configured |
| **CopilotLogVersion** | ❌ Missing | No schema version field |
| **LogRecordType** | ❌ Missing | No product family identifier |
| **AppHost** | ❌ Missing | Client app not captured |
| **Contexts** (ContainerId, ContextId, ContextType) | ❌ Missing | No app context schema |

### Required Actions

1. **Map required fields to OpenTelemetry framework** — either onboard to Microsoft Purview Audit or align existing App Insights telemetry with the 1CS schema
2. **Add UserID (AAD) to telemetry** — extract from MISE authentication context
3. **Add Client IP + Region** — log from `HttpContext` in middleware
4. **Add ModelTransparencyDetails** — log full provider name, model, API version per interaction
5. **Add Message-level IDs and sizes** — unique PromptID/ResponseID with byte sizes
6. **Add AccessedResources tracking** — log URIs of ADO repos, ICM incidents, etc. accessed per interaction
7. **Configure JIT access** for SOC analysts to the protected telemetry repository
8. **Contact**: SDL AI Security for AI questions, AzAuditLog@microsoft.com for C+AI auditing questions

## Key Files in DEPA Repo

| Area | File |
|---|---|
| AI Agent Builder | `src/AzDevSvcAI.DeploymentAgent.Core/AIAgent/AgentBuilder.cs` |
| AI Model Config | `src/AzDevSvcAI.DeploymentAgent.Core/AIAgent/AiFoundryConfigs.cs` |
| Token Tracking | `src/AzDevSvcAI.DeploymentAgent.Core/Telemetry/TokenUsageTracker.cs` |
| OpenTelemetry Setup | `src/AzDevSvcAI.DeploymentAgent.ServiceDefaults/Extensions.cs` |
| App Insights Config | `src/AzDevSvcAI.DeploymentAgent.WebApi/appsettings.json` |
| API Controllers | `src/AzDevSvcAI.DeploymentAgent.WebApi/Controllers/AnalyzerController.cs` |
| OneBranch Pipeline | `.pipelines/OneBranch.Official.yml` (ESRP signing) |

## Related

- [[Complete AI Product Review and Assessment for Depo]]
- [[2026-03-10 Deployment Agent Weekly Meeting]]
- [[2026-03-10 Ki-JM 1-1]]
