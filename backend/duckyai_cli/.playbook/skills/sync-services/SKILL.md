---
name: sync-services
description: 'Sync vault services directory with Azure DevOps repos. Clones missing repos and fetches existing ones based on duckyai.yml config. Use when asked to sync services, clone repos, set up services directory, pull repos from ADO, initialize services, refresh code repos, or set up development environment.'
---

# Sync Services

Sync all Azure DevOps repositories defined in `duckyai.yml` into the vault's services directory. Automatically clones missing repos and fetches (updates) existing ones.

## Scripts

All scripts are bundled in `scripts/` within this skill folder:

| Script | Purpose |
|--------|---------|
| `sync-services.sh` | Reads duckyai.yml, iterates service entries, invokes clone-ado-repos.sh per service |
| `clone-ado-repos.sh` | Lists repos from ADO, filters by glob pattern, clones new / fetches existing |
| `find-bash.ps1` | Discovers bash.exe on Windows (Git Bash, WSL, MSYS2) |

## Behavior

For each service in `duckyai.yml` with `metadata.type: ado`:
- **Repo doesn't exist** on disk → `git clone`
- **Repo exists** (`.git` found) → `git fetch origin --prune` (sync)
- **Partial dir** (no `.git`) → remove and re-clone
- **Stale lock files** → auto-cleaned before fetch

## Quick Start

### Full sync (all services from config)
```bash
bash scripts/sync-services.sh --vault <vault-root>
```

### Dry run (preview without cloning)
```bash
bash scripts/sync-services.sh --vault <vault-root> --dry-run
```

### Single service (bypass config, clone directly)
```bash
bash scripts/clone-ado-repos.sh \
  --org msazure \
  --project "Azure AppConfig" \
  --repos "*" \
  --target ./Main-Services/AppConfig
```

### On Windows (PowerShell)
```powershell
$bash = & ./scripts/find-bash.ps1
& $bash ./scripts/sync-services.sh --vault C:\Users\me\Main
```

## sync-services.sh Arguments

| Arg | Required | Description |
|-----|----------|-------------|
| `--vault` | Yes* | Vault root — auto-discovers duckyai.yml + services path |
| `--config` | No | Explicit path to duckyai.yml |
| `--services-path` | No | Explicit services directory |
| `--dry-run` | No | Preview matching repos without cloning |
| `--depth` | No | Shallow clone depth for all repos |

## clone-ado-repos.sh Arguments

| Arg | Required | Description |
|-----|----------|-------------|
| `--org` | Yes | Azure DevOps organization |
| `--project` | Yes | Project name (quote if spaces) |
| `--repos` | Yes | Repo pattern — repeatable (`*`, `prefix*`, exact) |
| `--target` | No | Target directory (default: `.`) |
| `--depth` | No | Shallow clone depth |
| `--dry-run` | No | Preview only |

## Repository Patterns

| Pattern | Matches |
|---------|---------|
| `"*"` | All repos in the project |
| `"ServiceLinker*"` | Repos starting with `ServiceLinker` |
| `"Azconfig.*"` | Repos starting with `Azconfig.` |
| `"DeploymentAgent"` | Exact match only |

## Authentication

Uses `AZURE_DEVOPS_EXT_PAT` env var if set. Falls back to `az login` cached credentials.

## Prerequisites

- Azure CLI with `azure-devops` extension
- Git
- Bash (Git Bash on Windows)
- Authenticated: `az login` or `AZURE_DEVOPS_EXT_PAT`

## Example duckyai.yml Config

```yaml
services:
  path: "../Main-Services"
  entries:
  - name: "AppConfig"
    metadata:
      type: ado
      organization: "msazure"
      project: "Azure AppConfig"
      repositories: ["*"]
  - name: "ServiceConnector"
    metadata:
      type: ado
      organization: "msazure"
      project: "One"
      repositories: ["ServiceLinker*"]
```
