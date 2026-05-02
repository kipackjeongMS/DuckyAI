#!/usr/bin/env python3
"""Self-update command for DuckyAI CLI."""

import os
import platform
import re
import shutil
import site
import sys
import sysconfig
import tempfile
import time
import zipfile
import subprocess
from pathlib import Path
from importlib.metadata import version as get_installed_version, PackageNotFoundError
from typing import Optional

import click
import requests
import psutil

# GitHub repository configuration
GITHUB_REPO = "kipackjeongMS/DuckyAI"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"


def get_current_version() -> Optional[str]:
    """Get the currently installed version of duckyai."""
    try:
        return get_installed_version("duckyai")
    except PackageNotFoundError:
        return None


def get_releases() -> list[dict]:
    """Fetch all releases from GitHub API."""
    try:
        response = requests.get(f"{GITHUB_API_BASE}/releases", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []


def get_latest_release() -> Optional[dict]:
    """Fetch the latest release from GitHub API."""
    try:
        response = requests.get(f"{GITHUB_API_BASE}/releases/latest", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def get_release_by_tag(tag: str) -> Optional[dict]:
    """Fetch a specific release by tag name."""
    try:
        response = requests.get(f"{GITHUB_API_BASE}/releases/tags/{tag}", timeout=10)
        if response.status_code == 200:
            return response.json()
    except requests.RequestException:
        pass
    return None


def download_zip(url: str, dest_path: Path) -> None:
    """Download a ZIP file from URL with progress indicator."""
    click.echo("Downloading...")
    
    response = requests.get(url, stream=True, timeout=60, allow_redirects=True)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    
    with open(dest_path, 'wb') as f:
        if total_size == 0:
            f.write(response.content)
        else:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                percent = int(100 * downloaded / total_size)
                click.echo(f"\rProgress: {percent}%", nl=False)
    
    click.echo("\nDownload complete.")


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Extract ZIP file and return path to extracted content."""
    click.echo("Extracting...")
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest_dir)
    
    # GitHub ZIPs contain a single directory
    extracted_dirs = [d for d in dest_dir.iterdir() if d.is_dir()]
    if len(extracted_dirs) == 1:
        return extracted_dirs[0]
    
    return dest_dir


def _normalize_version(v: str) -> str:
    """Strip leading 'v' for consistent comparison (v0.1.20 → 0.1.20)."""
    return v.lstrip("v") if v else v


def _patch_pyproject_version(install_dir: Path, version: str) -> bool:
    """Patch pyproject.toml version to match the release tag before pip install.

    GitHub release zips may have a stale version in pyproject.toml.
    This ensures pip builds the wheel with the correct version.
    """
    import re

    pyproject = install_dir / "pyproject.toml"
    if not pyproject.is_file():
        return False
    text = pyproject.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'^(version\s*=\s*")[^"]*(")', rf"\g<1>{version}\2", text, count=1, flags=re.MULTILINE
    )
    if count == 0:
        return False
    pyproject.write_text(new_text, encoding="utf-8")
    return True


def _get_update_log_dir() -> Path:
    """Return the persistent directory for update logs (~/.duckyai/logs/)."""
    log_dir = Path.home() / ".duckyai" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _recent_failed_update_log() -> Optional[Path]:
    """Return the most recent update-*.log if it indicates a failed update.

    Used by ``duckyai doctor`` to surface silent install failures.
    """
    log_dir = Path.home() / ".duckyai" / "logs"
    if not log_dir.is_dir():
        return None
    logs = sorted(log_dir.glob("update-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return None
    most_recent = logs[0]
    try:
        # Only flag logs from the last 7 days
        if time.time() - most_recent.stat().st_mtime > 7 * 86400:
            return None
        text = most_recent.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Markers written by the deferred bat or non-Windows install
    failure_markers = ("UPDATE FAILED", "VERSION MISMATCH", "ERROR: Could not install")
    success_marker = "UPDATE VERIFIED"
    if any(m in text for m in failure_markers) and success_marker not in text.split("UPDATE VERIFIED")[-1:][0]:
        return most_recent
    return None


def _cleanup_corrupt_distributions() -> int:
    """Remove orphaned ~duckyai* directories in site-packages.

    Pip renames dist-info dirs with a ``~`` prefix during uninstall.
    If the install fails mid-way, these orphans cause noisy warnings.
    """
    removed = 0
    for sp in site.getsitepackages():
        sp_path = Path(sp)
        if not sp_path.is_dir():
            continue
        for d in sp_path.iterdir():
            if d.is_dir() and d.name.startswith("~") and "uckyai" in d.name:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
    return removed


def _rename_locked_scripts() -> list[Path]:
    """On Windows, rename duckyai*.exe so pip can write new ones.

    Windows allows renaming a running executable but not overwriting it.
    Returns a list of ``.old`` paths for later cleanup.
    """
    if platform.system() != "Windows":
        return []

    scripts_dir = Path(sysconfig.get_path("scripts"))
    renamed: list[Path] = []

    for name in ("duckyai.exe", "duckyai-vault-mcp.exe"):
        exe = scripts_dir / name
        if not exe.exists():
            continue
        old = exe.with_suffix(".exe.old")
        try:
            if old.exists():
                old.unlink()
        except OSError:
            pass
        try:
            os.rename(str(exe), str(old))
            renamed.append(old)
        except OSError:
            pass
    return renamed


def _cleanup_old_scripts() -> None:
    """Remove leftover .old executables from a prior update."""
    if platform.system() != "Windows":
        return

    scripts_dir = Path(sysconfig.get_path("scripts"))
    if not scripts_dir.is_dir():
        return
    for old_file in scripts_dir.glob("duckyai*.exe.old"):
        try:
            old_file.unlink()
        except OSError:
            pass


def _stop_duckyai_processes() -> list[dict]:
    """Stop all running DuckyAI daemon and chat server processes.

    Returns a list of stopped process dicts (pid, vault_path) for restarting.
    """
    stopped: list[dict] = []

    # 1. Stop orchestrator daemons via the existing stop mechanism
    for vault_path in _find_active_vaults():
        try:
            from .orch_cmd import _stop_single_vault
            result = _stop_single_vault(vault_path, vault_path.name)
            if result.get("status") == "stopped":
                stopped.append({"type": "daemon", "vault": str(vault_path), "pid": result.get("pid")})
                click.echo(f"  Stopped daemon for {vault_path.name}")
        except Exception:
            pass

        # 2. Stop chat server for this vault
        try:
            from ..chat_server import stop_chat_server
            if stop_chat_server(str(vault_path)):
                stopped.append({"type": "chat", "vault": str(vault_path)})
                click.echo(f"  Stopped chat server for {vault_path.name}")
        except Exception:
            pass

        # 3. Stop terminal server for this vault
        try:
            from ..terminal_server import stop_terminal_server
            if stop_terminal_server(str(vault_path)):
                stopped.append({"type": "terminal", "vault": str(vault_path)})
                click.echo(f"  Stopped terminal server for {vault_path.name}")
        except Exception:
            pass

    # 4. Kill any remaining duckyai processes (not ourselves)
    # Collect our own PID and all ancestor PIDs — on Windows duckyai.exe
    # is a launcher shim (PID A) that spawns python.exe (PID B, us).
    # We must skip both to avoid killing the running update process.
    exclude_pids = {os.getpid()}
    try:
        for parent in psutil.Process(os.getpid()).parents():
            exclude_pids.add(parent.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    for proc in psutil.process_iter(["pid", "name", "cmdline", "exe"]):
        try:
            if proc.pid in exclude_pids:
                continue
            pname = (proc.info.get("name") or "").lower()
            exe_path = (proc.info.get("exe") or "").lower()
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()

            # Match duckyai executables (duckyai.exe, duckyai-vault-mcp.exe)
            is_duckyai_exe = "duckyai" in pname

            # Match duckyai python subprocesses (orchestrator, chat, daemon)
            is_duckyai_py = "duckyai" in cmdline and any(
                k in cmdline for k in ("orchestrator", "chat", "daemon", "vault-mcp")
            )

            # Match any process whose executable lives inside the duckyai
            # site-packages tree — these hold .pyc locks that block pip.
            is_duckyai_sitepkg = (
                "site-packages" in exe_path and "duckyai" in exe_path
            )

            # Match generic python.exe that imported duckyai (e.g. spawned by
            # Obsidian / Claude Desktop / Copilot CLI as an MCP child).
            is_python_with_duckyai = (
                pname in ("python.exe", "pythonw.exe", "py.exe")
                and "duckyai" in cmdline
            )

            if is_duckyai_exe or is_duckyai_py or is_duckyai_sitepkg or is_python_with_duckyai:
                proc.terminate()
                proc.wait(timeout=5)
                click.echo(f"  Terminated process PID {proc.pid} ({pname})")
                stopped.append({"type": "process", "pid": proc.pid, "name": pname})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            pass

    return stopped


def _restart_duckyai_processes(stopped: list[dict]) -> None:
    """Restart previously stopped DuckyAI processes."""
    vault_paths_to_restart = set()
    for entry in stopped:
        if entry.get("vault"):
            vault_paths_to_restart.add(entry["vault"])

    for vault_str in vault_paths_to_restart:
        try:
            subprocess.Popen(
                [sys.executable, "-m", "duckyai", "-o"],
                cwd=vault_str,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                **({"creationflags": 0x00000200 | 0x08000000} if platform.system() == "Windows" else {}),
            )
            click.echo(f"  Restarted daemon for {Path(vault_str).name}")
        except Exception as e:
            click.echo(f"  ⚠️  Failed to restart daemon for {Path(vault_str).name}: {e}", err=True)


def install_package(package_dir: Path) -> bool:
    """Install the package using pip."""
    click.echo("Installing...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", str(package_dir)],
            capture_output=True,
            text=True,
            check=True,
        )
        click.echo(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        click.echo(f"Installation failed: {e.stderr}", err=True)
        return False


def _deferred_install(
    package_dir: Path,
    vaults: list[Path],
    stopped: list[dict],
    expected_version: Optional[str] = None,
) -> None:
    """Spawn a detached batch script that waits for us to exit, then runs pip install.

    On Windows the running ``duckyai.exe`` shim holds a file-lock that
    prevents pip from overwriting it.  This function writes a small batch
    script that:
      1. Waits for our parent ``duckyai.exe`` to exit (polls with ``tasklist``).
      2. Runs ``python -m pip install --upgrade <package_dir>``.
      3. Verifies the installed version matches ``expected_version``.
      4. Syncs vault files via ``duckyai update --sync-only``.
      5. Restarts previously-stopped daemon processes.
      6. Writes a persistent log to ``~/.duckyai/logs/update-{ts}.log``.
      7. Cleans up temp files and itself.
    """
    # Find our launcher PID (the duckyai.exe shim)
    launcher_pid = os.getpid()
    try:
        parent = psutil.Process(os.getpid()).parent()
        if parent and "duckyai" in (parent.name() or "").lower():
            launcher_pid = parent.pid
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    python_exe = sys.executable
    scripts_dir = Path(sysconfig.get_path("scripts"))

    # Rename any locked duckyai*.exe shims to .exe.old so pip can write
    # fresh ones — Windows allows rename of held files but not overwrite.
    _rename_locked_scripts()

    # The temp directory containing the extracted release
    tmpdir = package_dir.parent
    if tmpdir.name == "backend":
        tmpdir = tmpdir.parent

    # Persistent log file for diagnosing silent failures
    log_dir = _get_update_log_dir()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    logfile = log_dir / f"update-{timestamp}.log"

    # Build vault restart commands
    restart_cmds = ""
    vault_paths_to_restart = {e["vault"] for e in stopped if e.get("vault")}
    for vault_str in vault_paths_to_restart:
        restart_cmds += (
            f'start "" /B "{python_exe}" -m duckyai -o\n'
        )

    expected_clean = (expected_version or "").lstrip("v") or "unknown"

    bat_path = Path(tempfile.gettempdir()) / "duckyai_update.bat"
    bat_content = f"""@echo off
REM DuckyAI deferred updater
setlocal EnableDelayedExpansion
set "LOGFILE={logfile}"
set "EXPECTED={expected_clean}"

echo ====================================  >> "%LOGFILE%" 2>&1
echo DuckyAI deferred update                  >> "%LOGFILE%" 2>&1
echo Started: %DATE% %TIME%                   >> "%LOGFILE%" 2>&1
echo Expected version: %EXPECTED%             >> "%LOGFILE%" 2>&1
echo Python: {python_exe}                     >> "%LOGFILE%" 2>&1
echo Package: {package_dir}                   >> "%LOGFILE%" 2>&1
echo ====================================  >> "%LOGFILE%" 2>&1

echo DuckyAI deferred installer
echo Log: %LOGFILE%
echo.

:wait
tasklist /FI "PID eq {launcher_pid}" 2>NUL | find /I "{launcher_pid}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto wait
)

REM ---- Pre-pip lock cleanup -----------------------------------------------
REM Host apps (Obsidian, Claude Desktop, Copilot CLI) may respawn
REM duckyai-vault-mcp.exe between the parent's kill and pip's run.
REM Loop a few times to drain any respawned children before pip starts.
echo Killing any lingering duckyai processes...      >> "%LOGFILE%" 2>&1
for /L %%i in (1,1,5) do (
    taskkill /F /IM duckyai-vault-mcp.exe >NUL 2>&1
    taskkill /F /IM duckyai.exe >NUL 2>&1
    timeout /t 1 /nobreak >NUL
)

REM Re-rename any freshly-respawned .exe shims so pip can write them.
echo Re-renaming locked .exe shims...                >> "%LOGFILE%" 2>&1
if exist "{scripts_dir}\\duckyai.exe" (
    move /Y "{scripts_dir}\\duckyai.exe" "{scripts_dir}\\duckyai.exe.old" >> "%LOGFILE%" 2>&1
)
if exist "{scripts_dir}\\duckyai-vault-mcp.exe" (
    move /Y "{scripts_dir}\\duckyai-vault-mcp.exe" "{scripts_dir}\\duckyai-vault-mcp.exe.old" >> "%LOGFILE%" 2>&1
)

echo Running pip install...
echo Running pip install...                   >> "%LOGFILE%" 2>&1
set PIP_EXIT=1
for /L %%a in (1,1,3) do (
    if !PIP_EXIT! NEQ 0 (
        echo pip attempt %%a ...                >> "%LOGFILE%" 2>&1
        "{python_exe}" -m pip install --upgrade --force-reinstall --no-deps "{package_dir}"  >> "%LOGFILE%" 2>&1
        set PIP_EXIT=!ERRORLEVEL!
        if !PIP_EXIT! NEQ 0 (
            echo pip attempt %%a failed (exit !PIP_EXIT!), draining locks... >> "%LOGFILE%" 2>&1
            taskkill /F /IM duckyai-vault-mcp.exe >NUL 2>&1
            taskkill /F /IM duckyai.exe >NUL 2>&1
            timeout /t 3 /nobreak >NUL
        )
    )
)
echo pip --no-deps final exit code: !PIP_EXIT!  >> "%LOGFILE%" 2>&1

echo Updating dependencies...
echo Updating dependencies...                 >> "%LOGFILE%" 2>&1
"{python_exe}" -m pip install --upgrade "{package_dir}"  >> "%LOGFILE%" 2>&1
set PIP_DEPS_EXIT=!ERRORLEVEL!
echo pip deps exit code: !PIP_DEPS_EXIT!      >> "%LOGFILE%" 2>&1

REM Verify installed version matches expected
echo Verifying installed version...
set "INSTALLED="
for /f "usebackq" %%v in (`"{python_exe}" -c "from importlib.metadata import version; print(version('duckyai'))" 2^>NUL`) do set "INSTALLED=%%v"
echo Installed version after pip: %INSTALLED% >> "%LOGFILE%" 2>&1

if /I "%INSTALLED%"=="%EXPECTED%" (
    echo UPDATE VERIFIED: %INSTALLED% matches expected  >> "%LOGFILE%" 2>&1
    echo.
    echo ====================================
    echo DuckyAI updated to %INSTALLED%
    echo ====================================

    echo Syncing vault files...
    echo Syncing vault files...               >> "%LOGFILE%" 2>&1
    "{python_exe}" -m duckyai update --sync-only  >> "%LOGFILE%" 2>&1

    echo Installing agency CLI...
    echo Installing agency CLI...             >> "%LOGFILE%" 2>&1
    where agency >NUL 2>&1
    if errorlevel 1 (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "iex \\"& {{ $(irm aka.ms/InstallTool.ps1)}} agency\\"" >> "%LOGFILE%" 2>&1
        echo agency install exit code: %ERRORLEVEL% >> "%LOGFILE%" 2>&1
    ) else (
        echo agency CLI already installed     >> "%LOGFILE%" 2>&1
    )

    echo Cleaning up old executables...
    del /F /Q "{scripts_dir}\\duckyai*.exe.old" >NUL 2>&1

{restart_cmds}
    timeout /t 3 /nobreak >NUL
) else (
    echo UPDATE FAILED: VERSION MISMATCH      >> "%LOGFILE%" 2>&1
    echo Expected: %EXPECTED%                 >> "%LOGFILE%" 2>&1
    echo Got: %INSTALLED%                     >> "%LOGFILE%" 2>&1
    echo.
    echo ====================================
    echo  DuckyAI UPDATE FAILED
    echo ====================================
    echo Expected: %EXPECTED%
    echo Got:      %INSTALLED%
    echo.
    echo Most likely cause: a duckyai.exe or duckyai-vault-mcp.exe was
    echo locked by Obsidian, Copilot CLI, Claude Desktop, or another
    echo MCP host that respawned a child during install.
    echo.
    echo pip exit codes: --no-deps=!PIP_EXIT!  deps=!PIP_DEPS_EXIT!
    echo.
    echo Log file: %LOGFILE%
    echo.
    echo Run 'duckyai doctor' to see this error again.
    echo Run 'duckyai update --force' after closing Obsidian / Copilot
    echo to retry.
    echo.
    pause
)

:cleanup
rmdir /S /Q "{tmpdir}" >NUL 2>&1
del /F /Q "%~f0" >NUL 2>&1
endlocal
"""
    bat_path.write_text(bat_content, encoding="utf-8")

    # Launch the batch script fully detached
    subprocess.Popen(
        ["cmd.exe", "/C", str(bat_path)],
        creationflags=0x00000010 | 0x00000200,  # CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
        close_fds=True,
    )
    click.echo(f"  Deferred installer launched (waiting for PID {launcher_pid} to exit)")
    click.echo(f"  Log: {logfile}")
    click.echo("  The update will finish in a new console window.")


# ---------------------------------------------------------------------------
# Vault sync — update CLI-managed files in the user's vault
# ---------------------------------------------------------------------------

# Files that are always overwritten on update (CLI-managed, not user-editable)
_SYSTEM_FILES = {
    ".obsidian/plugins/duckyai/main.js",
    ".obsidian/plugins/duckyai/manifest.json",
    ".obsidian/plugins/duckyai/styles.css",
}


def _sync_config_nodes(vault_root: Path) -> None:
    """Add missing agent nodes to the user's duckyai.yml.

    Compares node names in the user's config against the canonical
    nodes-defaults.yml shipped with the package. Any nodes not present
    (by name) are appended to the user's config file.
    """
    import yaml

    config_path = vault_root / ".duckyai" / "duckyai.yml"
    if not config_path.is_file():
        return

    defaults_path = Path(__file__).resolve().parent.parent / ".playbook" / "nodes-defaults.yml"
    if not defaults_path.is_file():
        return

    # Load user config
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
    except Exception:
        click.echo("  ⚠ Could not parse duckyai.yml — skipping node sync", err=True)
        return

    # Load canonical defaults
    try:
        with open(defaults_path, "r", encoding="utf-8") as f:
            default_nodes = yaml.safe_load(f) or []
    except Exception:
        return

    if not isinstance(default_nodes, list):
        return

    user_nodes = user_config.get("nodes", []) or []
    existing_names = {n.get("name", "") for n in user_nodes if isinstance(n, dict)}

    # Find missing nodes
    missing = [n for n in default_nodes if n.get("name", "") not in existing_names]
    if not missing:
        return

    # Append missing nodes to the YAML file (preserving user formatting)
    # We append raw YAML text to avoid rewriting/reordering the entire file
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    additions = []
    for node in missing:
        # Serialize each node as a YAML block
        node_yaml = yaml.dump([node], default_flow_style=False, sort_keys=False)
        # yaml.dump wraps in a list; strip the leading "- " at top level
        # and re-indent as a proper nodes list entry
        lines = node_yaml.strip().splitlines()
        additions.append("\n" + "\n".join(lines))

    content = content.rstrip() + "\n" + "\n".join(additions) + "\n"

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)

    names = [n["name"] for n in missing]
    click.echo(f"  ✓ {len(missing)} new agent node(s) added: {', '.join(names)}")


def sync_vault(vault_root: Path) -> None:
    """Sync CLI-managed vault files after a package update.

    1. Calls ensure_init() to sync .playbook prompts, copilot-instructions, skills.
    2. Force-overwrites CLI-managed system files (Obsidian plugin).
    3. Copies new vault-template files that don't exist yet (skip-if-exists).
    4. Adds missing agent nodes to duckyai.yml.
    """
    from .cli import ensure_init

    click.echo()
    click.echo("Syncing vault files...")

    # 1) .playbook → .github/ (prompts-agent, copilot-instructions, skills)
    ensure_init(vault_root)
    click.echo("  ✓ Prompts, copilot-instructions, and skills synced")

    # 2) Vault-template files
    vault_template_dir = Path(__file__).resolve().parent.parent / ".vault-template"
    if not vault_template_dir.is_dir():
        click.echo("  ⚠ Bundled vault-template not found — skipping", err=True)
        return

    updated = 0
    created = 0
    for item in vault_template_dir.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(vault_template_dir)
        rel_posix = rel.as_posix()
        dest = vault_root / rel

        if rel_posix in _SYSTEM_FILES:
            # Always overwrite system files
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(dest))
            updated += 1
        elif not dest.exists():
            # New template file — copy it
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(dest))
            created += 1
        # else: user-owned file exists — leave it alone

    if updated:
        click.echo(f"  ✓ {updated} system file(s) updated (Obsidian plugin)")
    if created:
        click.echo(f"  ✓ {created} new template file(s) added")
    if not updated and not created:
        click.echo("  · Vault files already up to date")

    # 3) Sync missing agent nodes into duckyai.yml
    _sync_config_nodes(vault_root)


def _find_active_vaults() -> list[Path]:
    """Return all known vault roots."""
    vaults: list[Path] = []

    # Check the vault registry (home vault)
    try:
        from duckyai.vault_registry import get_home_vault
        home = get_home_vault()
        if home:
            p = Path(home["path"])
            if p.is_dir():
                vaults.append(p)
    except Exception:
        pass

    # Also try to find vault from current directory
    try:
        from .vault import find_vault_root, is_inside_vault
        if is_inside_vault():
            cwd_vault = find_vault_root()
            if cwd_vault.resolve() not in [v.resolve() for v in vaults]:
                vaults.append(cwd_vault)
    except Exception:
        pass

    return vaults


@click.command("update")
@click.option("--force", "-f", is_flag=True, help="Force update even if already up to date")
@click.option("--version", "-v", "target_version", type=str, help="Install a specific version")
@click.option("--list", "-l", "list_releases", is_flag=True, help="List available releases")
@click.option("--sync-only", is_flag=True, help="Skip pip install, only sync vault files")
def update_cli(force: bool, target_version: Optional[str], list_releases: bool, sync_only: bool) -> None:
    """Self-update the DuckyAI CLI from GitHub releases."""
    # Housekeeping: clean up leftover .old exes from a prior update
    _cleanup_old_scripts()

    click.echo("=" * 50)
    click.echo("DuckyAI CLI Self-Update")
    click.echo("=" * 50)
    click.echo()

    if list_releases:
        releases = get_releases()
        if not releases:
            click.echo("No releases available.")
            return

        click.echo("Available releases:")
        for release in releases[:10]:
            tag = release.get("tag_name", "unknown")
            name = release.get("name", "")
            prerelease = " (pre-release)" if release.get("prerelease") else ""
            click.echo(f"  {tag}{prerelease} - {name}")

        if len(releases) > 10:
            click.echo(f"  ... and {len(releases) - 10} more")
        return

    # --sync-only: skip pip install, just sync vault files
    if sync_only:
        click.echo("Sync-only mode — skipping pip install")
        _sync_all_vaults()
        return

    current_version = get_current_version()
    click.echo(f"Current version: {current_version or 'not installed'}")

    if target_version:
        release = get_release_by_tag(target_version)
        if not release:
            click.echo(f"Error: Release '{target_version}' not found.", err=True)
            click.echo("Use --list to see available releases.", err=True)
            sys.exit(1)
    else:
        release = get_latest_release()
        if not release:
            click.echo("Error: No releases available.", err=True)
            sys.exit(1)

    release_version = release.get("tag_name", "unknown")
    zipball_url = release.get("zipball_url")

    click.echo(f"Target version:  {release_version}")
    click.echo()

    release_ver_normalized = _normalize_version(release_version)
    if not force and current_version and current_version == release_ver_normalized:
        click.echo("Already up to date!")
        # Still sync vault files in case they're stale
        _sync_all_vaults()
        return

    if not zipball_url:
        click.echo("Error: No download URL found for release.", err=True)
        sys.exit(1)

    # Stop running DuckyAI processes so pip can overwrite files
    click.echo("Stopping DuckyAI processes...")
    stopped = _stop_duckyai_processes()
    if not stopped:
        click.echo("  No running processes found")

    # Use a persistent temp directory (not auto-deleted) so a deferred
    # installer batch script can access the files after we exit.
    tmpdir_path = Path(tempfile.mkdtemp(prefix="duckyai_update_"))
    zip_path = tmpdir_path / "release.zip"

    try:
        download_zip(zipball_url, zip_path)
        extracted_path = extract_zip(zip_path, tmpdir_path)

        # pyproject.toml lives in backend/ subdirectory
        backend_path = extracted_path / "backend"
        install_dir = backend_path if backend_path.is_dir() and (backend_path / "pyproject.toml").exists() else extracted_path

        # Patch version in pyproject.toml to match the release tag
        if _patch_pyproject_version(install_dir, release_ver_normalized):
            click.echo(f"  Patched pyproject.toml version → {release_ver_normalized}")

        # Pre-install cleanup
        cleaned = _cleanup_corrupt_distributions()
        if cleaned:
            click.echo(f"  Cleaned {cleaned} orphaned dist-info dir(s)")

    except requests.RequestException as e:
        shutil.rmtree(tmpdir_path, ignore_errors=True)
        click.echo(f"Download failed: {e}", err=True)
        sys.exit(1)
    except zipfile.BadZipFile as e:
        shutil.rmtree(tmpdir_path, ignore_errors=True)
        click.echo(f"Extraction failed: {e}", err=True)
        sys.exit(1)

    # On Windows, delegate pip install to a batch script that runs after
    # we exit — the running duckyai.exe shim holds a file-lock.
    if platform.system() == "Windows":
        click.echo()
        click.echo("Launching deferred installer (Windows file-lock workaround)...")
        vaults = _find_active_vaults()
        _deferred_install(install_dir, vaults, stopped, expected_version=release_ver_normalized)
        click.echo()
        click.echo("=" * 50)
        click.echo("Update will complete momentarily in a new window.")
        click.echo("=" * 50)
        sys.exit(0)

    # Non-Windows: direct install
    renamed = _rename_locked_scripts()
    if install_package(install_dir):
        click.echo()
        click.echo("✓ Python package updated")
    else:
        shutil.rmtree(tmpdir_path, ignore_errors=True)
        click.echo("Update failed.", err=True)
        sys.exit(1)

    shutil.rmtree(tmpdir_path, ignore_errors=True)

    # After pip install, sync vault files with the new package contents
    _sync_all_vaults()

    # Install agency CLI if not present
    if not shutil.which('agency') and platform.system() == 'Windows':
        click.echo("Installing agency CLI...")
        from ..prereqs import install_agency_cli
        if install_agency_cli():
            click.echo("  ✓ Agency CLI installed")
        else:
            click.echo("  ⚠ Agency CLI install failed (TCS/TMS will fall back to copilot_sdk)")

    # Restart previously stopped processes
    if stopped:
        click.echo()
        click.echo("Restarting DuckyAI processes...")
        _restart_duckyai_processes(stopped)

    click.echo()
    click.echo("=" * 50)
    click.echo("Update completed successfully!")
    click.echo("=" * 50)


def _sync_all_vaults() -> None:
    """Find all registered vaults and sync each one."""
    vaults = _find_active_vaults()
    if not vaults:
        click.echo()
        click.echo("No vaults found — run 'duckyai setup' to create one.")
        return

    for vault in vaults:
        click.echo()
        click.echo(f"─── Syncing vault: {vault} ───")
        try:
            sync_vault(vault)
        except Exception as e:
            click.echo(f"  ⚠ Error syncing vault: {e}", err=True)


if __name__ == "__main__":
    update_cli()
