#!/usr/bin/env pwsh
# find-bash.ps1 — Discover bash executable on Windows/macOS/Linux
#
# Usage:
#   ./find-bash.ps1                  # prints path to bash
#   $bash = ./find-bash.ps1          # capture path
#   & (./find-bash.ps1) script.sh    # invoke bash with a script
#
# Returns the first working bash found. Exit code 1 if none found.

$ErrorActionPreference = 'SilentlyContinue'

$candidates = @()

if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    $candidates += @(
        # Git for Windows (most common)
        "$env:ProgramFiles\Git\bin\bash.exe"
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
        # WSL
        "$env:SystemRoot\System32\wsl.exe"
        # MSYS2
        "C:\msys64\usr\bin\bash.exe"
        # Cygwin
        "C:\cygwin64\bin\bash.exe"
        "C:\cygwin\bin\bash.exe"
    )
    # Check PATH
    $pathBash = Get-Command bash.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if ($pathBash) { $candidates = @($pathBash) + $candidates }
} else {
    # macOS / Linux
    $candidates += @(
        "/bin/bash"
        "/usr/bin/bash"
        "/usr/local/bin/bash"    # Homebrew bash on macOS
        "/opt/homebrew/bin/bash" # Apple Silicon Homebrew
    )
    $pathBash = Get-Command bash -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if ($pathBash) { $candidates = @($pathBash) + $candidates }
}

foreach ($c in $candidates) {
    if (Test-Path $c) {
        # Verify it actually runs
        try {
            $result = & $c -c 'echo ok' 2>$null
            if ($result -eq 'ok') {
                Write-Output $c
                exit 0
            }
        } catch {}
    }
}

Write-Error "bash not found. Install Git for Windows (includes bash) or WSL."
exit 1
