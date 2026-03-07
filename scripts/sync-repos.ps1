<#
.SYNOPSIS
    Syncs documentation repositories defined in repos.json.

.DESCRIPTION
    Clones new repositories and pulls updates for existing ones.
    Uses Git credential manager for authentication (no PAT needed).
    
    First-time setup:
      - Ensure Git is installed
      - Git credential manager handles ADO auth automatically

.EXAMPLE
    .\sync-repos.ps1

.EXAMPLE
    .\sync-repos.ps1 -Force  # Re-clone even if exists

.EXAMPLE
    .\sync-repos.ps1 -RepoName "specific-repo"  # Sync only one repo
#>

param(
    [string]$ConfigPath = "",
    [string]$RepoName = "",
    [switch]$Force
)

# Default config path
if (-not $ConfigPath) {
    $ConfigPath = Join-Path $PSScriptRoot "repos.json"
}

if (-not (Test-Path $ConfigPath)) {
    Write-Error "Config file not found: $ConfigPath"
    exit 1
}

# Check git is available
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Git not found. Please install Git."
    exit 1
}

# Load config
$config = Get-Content $ConfigPath | ConvertFrom-Json
$reposDir = Join-Path (Join-Path $PSScriptRoot "..") $config.reposDir

# Create repos directory if needed
if (-not (Test-Path $reposDir)) {
    Write-Host "Creating repos directory: $reposDir" -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $reposDir -Force | Out-Null
}

# Add to .gitignore if not already there
$gitignorePath = Join-Path (Join-Path $PSScriptRoot "..") ".gitignore"
$ignoreEntry = $config.reposDir + "/"
if (Test-Path $gitignorePath) {
    $gitignoreContent = Get-Content $gitignorePath -Raw
    if ($gitignoreContent -notmatch [regex]::Escape($ignoreEntry)) {
        Add-Content -Path $gitignorePath -Value "`n# Synced doc repos`n$ignoreEntry"
        Write-Host "Added $ignoreEntry to .gitignore" -ForegroundColor Yellow
    }
}

$successCount = 0
$failCount = 0
$skippedCount = 0

foreach ($repo in $config.repositories) {
    # Filter by name if specified
    if ($RepoName -and $repo.name -ne $RepoName) {
        continue
    }
    
    # Skip disabled repos
    if (-not $repo.enabled) {
        Write-Host "[$($repo.name)] Skipped (disabled)" -ForegroundColor DarkGray
        $skippedCount++
        continue
    }
    
    $repoPath = Join-Path $reposDir $repo.name
    $branch = if ($repo.branch) { $repo.branch } else { "main" }
    
    Write-Host "`n[$($repo.name)]" -ForegroundColor Cyan
    if ($repo.description) {
        Write-Host "  $($repo.description)" -ForegroundColor DarkGray
    }
    
    try {
        if ((Test-Path $repoPath) -and -not $Force) {
            # Repo exists - pull updates
            Write-Host "  Pulling latest..." -ForegroundColor White
            
            # For sparse checkouts or repos without tracking, use fetch + reset
            $result = git -C $repoPath fetch origin $branch 2>&1
            if ($LASTEXITCODE -eq 0) {
                $result = git -C $repoPath reset --hard "origin/$branch" 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "  Updated successfully" -ForegroundColor Green
                    $successCount++
                } else {
                    Write-Host "  Reset failed: $result" -ForegroundColor Red
                    $failCount++
                }
            } else {
                Write-Host "  Fetch failed: $result" -ForegroundColor Red
                $failCount++
            }
        } else {
            # Clone new repo
            if ($Force -and (Test-Path $repoPath)) {
                Write-Host "  Removing existing (--Force)..." -ForegroundColor Yellow
                Remove-Item -Path $repoPath -Recurse -Force
            }
            
            # Check if sparse checkout is needed
            if ($repo.sparse) {
                Write-Host "  Cloning with sparse checkout ($($repo.sparse))..." -ForegroundColor White
                
                # Initialize empty repo
                New-Item -ItemType Directory -Path $repoPath -Force | Out-Null
                git -C $repoPath init 2>&1 | Out-Null
                git -C $repoPath remote add origin $repo.url 2>&1 | Out-Null
                
                # Enable sparse checkout (use cone mode for better performance)
                git -C $repoPath sparse-checkout init --cone 2>&1 | Out-Null
                git -C $repoPath sparse-checkout set $repo.sparse 2>&1 | Out-Null
                
                # Fetch and checkout with tracking
                $result = git -C $repoPath fetch --depth 1 origin $branch 2>&1
                if ($LASTEXITCODE -eq 0) {
                    git -C $repoPath checkout -b $branch "origin/$branch" 2>&1 | Out-Null
                    Write-Host "  Cloned successfully (sparse: $($repo.sparse))" -ForegroundColor Green
                    $successCount++
                } else {
                    Write-Host "  Clone failed: $result" -ForegroundColor Red
                    $failCount++
                }
            } else {
                Write-Host "  Cloning..." -ForegroundColor White
                $result = git clone --branch $branch --single-branch $repo.url $repoPath 2>&1
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "  Cloned successfully" -ForegroundColor Green
                    $successCount++
                } else {
                    Write-Host "  Clone failed: $result" -ForegroundColor Red
                    $failCount++
                }
            }
        }
    }
    catch {
        Write-Host "  Error: $_" -ForegroundColor Red
        $failCount++
    }
}

# Summary
Write-Host "`n-----------------------------------" -ForegroundColor DarkGray
Write-Host "Sync complete: " -NoNewline
Write-Host "$successCount succeeded" -ForegroundColor Green -NoNewline
if ($failCount -gt 0) {
    Write-Host ", $failCount failed" -ForegroundColor Red -NoNewline
}
if ($skippedCount -gt 0) {
    Write-Host ", $skippedCount skipped" -ForegroundColor DarkGray -NoNewline
}
Write-Host ""

if ($failCount -gt 0) {
    exit 1
}
