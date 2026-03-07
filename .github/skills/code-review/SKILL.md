---
name: code-review
description: 'Perform a code review on any Azure DevOps pull request. Use when asked to review a PR, review code changes, check PR comments, fetch PR details, or start a code review. Handles repo cloning, fetching branches (read-only), independent diff review, and ADO API integration for PR metadata and comment threads. Works with any ADO organization and project.'
---

# Code Review Skill

Perform a thorough code review on any Azure DevOps PR by cloning the repo locally, reviewing the diff independently, and fetching PR metadata and existing comments via the ADO REST API.

**IMPORTANT: This skill is READ-ONLY. Never checkout branches, never commit, never push. All operations should only fetch and diff.**

## Configuration

This skill uses a configurable repos directory. Before starting, determine where repos are stored:

1. **Check `scripts/repos.json`** in the vault root for the `reposDir` field (default: `.repos`)
2. The repos directory path is **relative to the vault root**

```powershell
# Read the repos dir from config (do this once at the start)
$config = Get-Content "scripts/repos.json" | ConvertFrom-Json
$reposDir = $config.reposDir  # e.g., ".repos"
```

Use `$reposDir` as the base path for all repo operations below. If `scripts/repos.json` does not exist, fall back to `.repos`.

## Instructions

### Step 0: Parse the PR Input

The user will provide either:
- A PR URL: `https://msazure.visualstudio.com/{project}/_git/{repo}/pullrequest/{prId}`
- A repo name + branch name + project
- A PR ID + repo name + project

Extract from the URL:
- **Organization** (e.g., `msazure` from `msazure.visualstudio.com` or `dev.azure.com/msazure`)
- **Project** (e.g., `One`, `Azure AppConfig`)
- **Repository name** (e.g., `ServiceLinker`, `ServicePipelines`)
- **PR ID** (numeric, e.g., `14735430`)

Then fetch the PR to get:
- **Source branch** (e.g., `user/someone/feature`)
- **Target branch** (e.g., `main` or `dev`)

**Default values** (if not specified): org=`your-org`, project=`your-project`

> **Setup:** Update the defaults above to match your ADO organization and project. You can also provide them per-request.

### Step 1: Check if Repo Exists Locally

Check if the repository already exists in `{reposDir}/{RepoName}/`:

```powershell
Test-Path "{reposDir}/{RepoName}"
```

**If it exists**, skip to Step 2.

**If it doesn't exist**, clone it:

```powershell
cd {reposDir}
git clone "https://msazure.visualstudio.com/{Project}/_git/{RepoName}"
```

> **Note:** For repos you review regularly, add them to `scripts/repos.json` and use `.\scripts\sync-repos.ps1 -RepoName "{RepoName}"` for ongoing sync. For one-off reviews of external repos, direct cloning into `{reposDir}/` is sufficient.

### Step 2: Fetch Latest and PR Branch

Fetch the target and source branches to remote refs only (do NOT checkout):

```powershell
cd "{reposDir}/{RepoName}"
git fetch origin "{targetBranch}"
git fetch origin "+refs/heads/{sourceBranch}:refs/remotes/origin/{sourceBranch}"
```

### Step 3: Review the Diff Independently

Before looking at any existing comments, perform your own independent review.

**IMPORTANT:** Use the merge-base to get accurate PR changes. A simple `origin/dev..origin/feature` diff will include "phantom" changes if the target branch has moved forward since the feature branch was created.

```bash
# Find the merge base (where the feature branch diverged from target)
git merge-base origin/{targetBranch} origin/{sourceBranch}

# Diff from merge base to see ONLY the PR's changes
git diff --stat $(git merge-base origin/{targetBranch} origin/{sourceBranch})..origin/{sourceBranch}

# Full diff
git diff $(git merge-base origin/{targetBranch} origin/{sourceBranch})..origin/{sourceBranch}
```

Alternatively, use the three-dot syntax which automatically finds the merge-base:

```bash
git diff origin/{targetBranch}...origin/{sourceBranch}
```

Review the changes for:
- **Correctness**: Does the code do what it claims?
- **Spec compliance**: For skills, check Agent Skills spec (frontmatter fields, structure)
- **Best practices**: Code quality, naming, documentation
- **Bugs or issues**: Edge cases, error handling, security
- **Completeness**: Missing files, incomplete implementations

Compile your findings into a structured review before proceeding.

### Step 4: Fetch PR Metadata from ADO

Get PR details (title, status, author, reviewers, votes). **Use the correct project**:

```bash
az repos pr show \
  --id {prId} \
  --org "https://dev.azure.com/msazure" \
  --project "{Project}" \
  --query "{title:title, status:status, createdBy:createdBy.displayName, sourceRef:sourceRefName, targetRef:targetRefName, reviewers:reviewers[].{name:displayName,vote:vote}}" \
  -o json
```

Reviewer vote meanings:
| Vote | Meaning |
|------|---------|
| 10 | Approved |
| 5 | Approved with suggestions |
| 0 | No vote |
| -5 | Waiting for author |
| -10 | Rejected |

### Step 5: Fetch Existing Comments

Get all human comment threads (filter out system/bot threads). **Use the correct project**:

```bash
az devops invoke \
  --area git \
  --resource pullRequestThreads \
  --route-parameters project="{Project}" repositoryId={RepoName} pullRequestId={prId} \
  --org "https://dev.azure.com/msazure" \
  --query "value[?status=='active' || status=='fixed'].{id:id, status:status, filePath:threadContext.filePath, comments:comments[].{author:author.displayName, content:content}}" \
  -o json
```

### Step 6: Present the Review

Present findings in this structure:

1. **PR Summary**: Title, author, source → target branch, reviewer status
2. **Independent Review**: Your findings organized by file, with severity (blocker, needs-change, suggestion, nit)
3. **Existing Comments**: Map existing comments against your findings — note what's already covered and what's missing
4. **Recommended Actions**: What comments to add, what vote to cast

### Step 7: Log the Review

After the review is complete, use the MCP tool to log it:

```
logPRReview(action="reviewed", person="{authorName}", prNumber="{prId}", prUrl="{prUrl}", description="{brief summary}")
```

## Posting Comments (Optional)

If the user wants to post comments directly, comments can only be posted via the ADO REST API since `az repos pr thread` is not available in the CLI extension.

For now, present the comments for the user to post manually in the ADO UI, or investigate using `az devops invoke` with POST method for `pullRequestThreads`.

## Casting a Vote (Optional)

If the user wants to vote:

```bash
az repos pr set-vote \
  --id {prId} \
  --vote {voteValue} \
  --org "https://dev.azure.com/msazure" \
  --project "{Project}"
```

## Prerequisites

1. Azure CLI with DevOps extension: `az extension add --name azure-devops`
2. Authenticated to Azure CLI: `az login`
3. Git installed and credential manager configured
4. Read access to the target ADO repository
5. `scripts/repos.json` configured with `reposDir` (default: `.repos`)

## Notes

- **READ-ONLY**: Never checkout, commit, or push to any branch. Only fetch to remote refs and diff.
- **Use merge-base or three-dot diff**: `origin/dev..origin/feature` (two dots) shows all differences between current HEAD of dev and feature. Use `origin/dev...origin/feature` (three dots) or explicit merge-base to see only the PR's actual changes.
- Always perform your independent review (Step 3) BEFORE reading existing comments (Step 5) to avoid anchoring bias
- The `az repos pr thread` subcommand does not exist — use `az devops invoke` with the REST API for comment threads
- Synced repos live at `{reposDir}/{RepoName}/` — the `reposDir` is configured in `scripts/repos.json`
- For external repos (outside your org), clone directly into `{reposDir}/` rather than adding to repos.json
- PR URL formats:
  - `https://msazure.visualstudio.com/{Project}/_git/{Repo}/pullrequest/{id}`
  - `https://dev.azure.com/msazure/{Project}/_git/{Repo}/pullrequest/{id}`
