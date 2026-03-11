#!/usr/bin/env python3
"""Main entry point for DuckyAI CLI — an AI-powered developer assistant."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import click
import logging
from pathlib import Path

from .show_config import show_config as show_config_handler
from .orchestrator import run_orchestrator_daemon
from .orch_cmd import orchestrator_group, _read_pid, orch_status, orch_list_agents
from .vault import find_vault_root, resolve_vault


def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) gracefully."""
    print("\n\nShutting down DuckyAI...")
    sys.exit(0)


def ensure_orchestrator_running(vault_root: Path, debug: bool = False):
    """Start the orchestrator as a detached background process if not already running.

    Delegates PID checks to orch_cmd module (single source of truth).

    Returns:
        True if orchestrator was freshly started, False if already running.
    """
    pid, alive = _read_pid(vault_root)
    if alive:
        return False  # already running

    pid_file = vault_root / ".orchestrator.pid"
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)

    duckyai_exe = shutil.which("duckyai")

    if os.name == "nt":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000
        flags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        cmd = [duckyai_exe, "-o"] if duckyai_exe else [sys.executable, "-m", "duckyai_cli.main.cli", "-o"]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(vault_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
            )
            new_pid = proc.pid
            for _ in range(10):
                if pid_file.exists():
                    try:
                        new_pid = int(pid_file.read_text(encoding="utf-8").strip())
                        break
                    except (ValueError, OSError):
                        pass
                time.sleep(0.5)
            click.echo(f"🚀 Orchestrator started (PID {new_pid})")
            return True
        except Exception as e:
            click.echo(f"⚠️  Failed to auto-start orchestrator: {e}", err=True)
            return False
    else:
        cmd = [duckyai_exe, "-o"] if duckyai_exe else [sys.executable, "-m", "duckyai_cli.main.cli", "-o"]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(vault_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            click.echo(f"🚀 Orchestrator started (PID {proc.pid})")
            return True
        except Exception as e:
            click.echo(f"⚠️  Failed to auto-start orchestrator: {e}", err=True)
            return False


def _detect_ides() -> list:
    """Detect installed IDEs (VS Code, VS Code Insiders). Returns list of (name, exe_path)."""
    ides = []
    for name, cmd in [("VS Code Insiders", "code-insiders"), ("VS Code", "code")]:
        exe = shutil.which(cmd)
        if exe:
            ides.append((name, exe))
    return ides


def _open_vault_in_ide(vault_root: Path):
    """Prompt user to pick an IDE and open the vault."""
    ides = _detect_ides()
    if not ides:
        return

    if len(ides) == 1:
        name, exe = ides[0]
        try:
            subprocess.Popen([exe, str(vault_root)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            click.echo(f"🖥️  Opened vault in {name}")
        except Exception:
            pass
        return

    # Multiple IDEs — use arrow-key selector
    from .vault import _interactive_select
    click.echo("\n🖥️  Open vault in: (↑↓ to move, Enter to select)\n")
    items = [{"name": name, "path": exe} for name, exe in ides]
    choice = _interactive_select(items, default_index=0)
    if choice is not None:
        name, exe = ides[choice]
        try:
            subprocess.Popen([exe, str(vault_root)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            click.echo(f"\n  ✓ Opened vault in {name}")
        except Exception:
            pass


def _enqueue_tcs_task(vault_root: Path):
    """Write a QUEUED TCS task file for the running orchestrator daemon to pick up."""
    from datetime import datetime
    from ..config import Config

    config = Config(vault_path=vault_root)
    tasks_dir = Path(config.get_orchestrator_tasks_dir())
    tasks_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime('%H%M')
    date_str = now.strftime('%Y-%m-%d')
    filename = f"{date_str} TCS - startup-{timestamp}.md"
    task_path = tasks_dir / filename

    if task_path.exists():
        return  # Already queued

    trigger_data = '{\\"path\\": \\"\\", \\"event_type\\": \\"manual\\"}'
    content = f"""---
title: "TCS - startup-{timestamp}"
created: "{now.isoformat()}"
archived: "false"
worker: "copilot_sdk"
status: "QUEUED"
priority: "medium"
output: ""
task_type: "TCS"
generation_log: ""
trigger_data_json: "{trigger_data}"
---

## Input

Manual event triggered Teams Chat Summary (TCS) processing.

## Output

Teams Chat Summary (TCS) will update this section with output information.

## Instructions

## Process Log

## Evaluation Log
"""
    task_path.write_text(content, encoding='utf-8')


def _enqueue_tms_task(vault_root: Path):
    """Write a QUEUED TMS task file for the running orchestrator daemon to pick up."""
    from datetime import datetime
    from ..config import Config

    config = Config(vault_path=vault_root)
    tasks_dir = Path(config.get_orchestrator_tasks_dir())
    tasks_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime('%H%M')
    date_str = now.strftime('%Y-%m-%d')
    filename = f"{date_str} TMS - startup-{timestamp}.md"
    task_path = tasks_dir / filename

    if task_path.exists():
        return

    trigger_data = '{\\"path\\": \\"\\", \\"event_type\\": \\"manual\\"}'
    content = f"""---
title: "TMS - startup-{timestamp}"
created: "{now.isoformat()}"
archived: "false"
worker: "copilot_sdk"
status: "QUEUED"
priority: "medium"
output: ""
task_type: "TMS"
generation_log: ""
trigger_data_json: "{trigger_data}"
---

## Input

Manual event triggered Teams Meeting Summary (TMS) processing.

## Output

Teams Meeting Summary (TMS) will update this section with output information.

## Instructions

## Process Log

## Evaluation Log
"""
    task_path.write_text(content, encoding='utf-8')


def _is_junction(path: Path) -> bool:
    """Check if a path is a directory junction (works on Python 3.8+)."""
    if os.name != 'nt':
        return False
    try:
        import ctypes
        FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        return attrs != -1 and bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except Exception:
        return False


def ensure_init(vault_root: Path):
    """Auto-init user directories: .github/skills/ and ~/.duckyai/ global runtime dirs.

    System files (prompts-agent, bases, templates, etc.) live in the
    CLI package's .playbook/ and are NOT exposed in .github/.
    """
    github_dir = vault_root / '.github'

    # Clean up legacy junction/symlink if .github points to whole .playbook
    if github_dir.is_symlink() or _is_junction(github_dir):
        if os.name == 'nt':
            os.rmdir(str(github_dir))
        else:
            github_dir.unlink()
    elif github_dir.is_file():
        # Broken git-style file symlink
        github_dir.unlink()

    # Ensure .github/ is a real directory
    github_dir.mkdir(parents=True, exist_ok=True)

    # Clean up legacy junctions inside .github/ (from previous versions)
    for subdir in ('prompts-agent', 'bases', 'templates', 'guidelines', 'prompts'):
        link = github_dir / subdir
        if link.is_symlink() or _is_junction(link):
            if os.name == 'nt':
                os.rmdir(str(link))
            else:
                link.unlink()

    # Ensure .github/skills/ exists (user-owned)
    skills_dir = github_dir / 'skills'
    skills_dir.mkdir(parents=True, exist_ok=True)

    # Symlink built-in playbook skills into .github/skills/
    # so Copilot CLI auto-discovers them alongside user skills.
    playbook_skills = Path(__file__).resolve().parent.parent / '.playbook' / 'skills'
    if playbook_skills.is_dir():
        for skill in playbook_skills.iterdir():
            if not skill.is_dir():
                continue
            target = skills_dir / skill.name
            if target.exists() or target.is_symlink() or _is_junction(target):
                continue  # user-owned or already linked — don't overwrite
            try:
                if os.name == 'nt':
                    # Windows: directory junction (no admin rights needed)
                    import subprocess as _sp
                    _sp.run(
                        ['cmd', '/c', 'mklink', '/J', str(target), str(skill)],
                        check=True, capture_output=True,
                    )
                else:
                    target.symlink_to(skill)
            except Exception:
                pass  # non-critical — skill just won't be auto-discovered

    # Create global ~/.duckyai runtime dirs (logs, tasks, history)
    from duckyai_cli.config import get_global_runtime_dir
    try:
        # Read vault_id from orchestrator.yaml
        import yaml
        orch_path = vault_root / "orchestrator.yaml"
        vault_id = "default"
        if orch_path.exists():
            with orch_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
                vault_id = data.get("id", "default")
        runtime_dir = get_global_runtime_dir(vault_id)
        for subdir in ["tasks", "logs", "history"]:
            (runtime_dir / subdir).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass  # non-critical


def get_mcp_config(vault_root: Path) -> str:
    """Build MCP config JSON for DuckyAI MCP servers."""
    config = {"mcpServers": {}}

    # Vault MCP server — check embedded (CLI package) first, then vault-local
    mcp_index = None
    try:
        from ..mcp_server import get_mcp_index_js
        embedded = get_mcp_index_js()
        if embedded.exists():
            mcp_index = embedded
    except ImportError:
        pass

    if not mcp_index:
        local = vault_root / 'mcp-server' / 'dist' / 'index.js'
        if local.exists():
            mcp_index = local

    if mcp_index:
        config["mcpServers"]["duckyai-vault"] = {
            "command": "node",
            "args": [str(mcp_index)],
            "env": {"DUCKYAI_VAULT_ROOT": str(vault_root)}
        }

    # Release Dashboard MCP server (Python)
    rd_pkg = vault_root / 'mcp-server' / 'release-dashboard' / 'src' / 'release_dashboard_mcp' / 'server.py'
    if rd_pkg.exists():
        rd_config = vault_root / 'mcp-server' / 'release-dashboard' / 'config.yaml'
        config["mcpServers"]["release-dashboard"] = {
            "command": "release-dashboard-mcp",
            "args": [],
            "env": {
                "RELEASE_DASHBOARD_CONFIG": str(rd_config),
            }
        }

    # Microsoft WorkIQ MCP server (M365 Copilot data)
    config["mcpServers"]["workiq"] = {
        "command": "npx",
        "args": ["-y", "@microsoft/workiq", "mcp"]
    }

    return json.dumps(config) if config["mcpServers"] else None


def launch_copilot(vault_root: Path, prompt: str = None, interactive_prompt: str = None,
                   mcp_config: tuple = None, session_id: str = None, model: str = None):
    """Launch GitHub Copilot CLI from the vault root."""
    cmd = ['copilot']

    if prompt:
        cmd.extend(['--prompt', prompt])
    elif interactive_prompt:
        cmd.extend(['-i', interactive_prompt])
    # else: no args = fully interactive

    # Auto-configure vault MCP server
    auto_mcp = get_mcp_config(vault_root)
    if auto_mcp:
        cmd.extend(['--additional-mcp-config', auto_mcp])

    # Additional MCP configs from CLI flags
    if mcp_config:
        for config in mcp_config:
            cmd.extend(['--additional-mcp-config', config])

    if session_id:
        cmd.extend(['--session-id', session_id])

    if model:
        cmd.extend(['--model', model])

    try:
        result = subprocess.run(cmd, cwd=str(vault_root))
        return result.returncode
    except FileNotFoundError:
        click.echo("Error: 'copilot' CLI not found. Install GitHub Copilot CLI first.", err=True)
        click.echo("  brew install gh && gh extension install github/gh-copilot", err=True)
        return 1


@click.group(invoke_without_command=True)
@click.option(
    "-o",
    "--orchestrator",
    "orchestrator",
    is_flag=True,
    help="Run orchestrator daemon (file watcher + cron scheduler)",
)
@click.option(
    "--orchestrator-status",
    is_flag=True,
    help="Show orchestrator status and loaded agents",
)
@click.option(
    "-c",
    "--config-file",
    "config_file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    help="Path to orchestrator config file (default: orchestrator.yaml)",
)
@click.option("-d", "--debug", is_flag=True, help="Enable debug logging")
@click.option(
    "--list-agents", is_flag=True, help="List available AI agents and their status"
)
@click.option("--show-config", is_flag=True, help="Show current configuration")
@click.option(
    "-w",
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=str),
    help="Working directory for the vault",
)
@click.option(
    "-p",
    "--prompt",
    "prompt_text",
    type=str,
    help="Execute a one-time prompt (non-interactive)",
)
@click.option(
    "-i",
    "--interactive",
    "interactive_prompt",
    type=str,
    help="Start interactive session and execute this prompt first",
)
@click.option(
    "-s",
    "--session-id",
    "session_id",
    type=str,
    help="Session ID — resumes if exists, creates if not",
)
@click.option(
    "--mcp-config",
    "mcp_config",
    multiple=True,
    help="Additional MCP server config (JSON file or string, repeatable)",
)
@click.option(
    "-m",
    "--model",
    "model",
    type=str,
    help="AI model to use",
)
@click.option(
    "--vault",
    "vault_id",
    type=str,
    help="Use a specific registered vault by ID (skips selection prompt)",
)
@click.pass_context
def main(
    ctx,
    orchestrator,
    orchestrator_status,
    config_file,
    debug,
    list_agents,
    show_config,
    working_dir,
    prompt_text,
    interactive_prompt,
    session_id,
    mcp_config,
    model,
    vault_id,
):
    """DuckyAI — AI-powered developer assistant.

    \b
    Run with no arguments to start an interactive AI session.
    The assistant has full access to your vault, skills, and tools.

    \b
    Examples:
        duckyai                          # Interactive AI session
        duckyai -p "create a new task"   # One-shot prompt
        duckyai -o                       # Start orchestrator daemon
    """
    signal.signal(signal.SIGINT, signal_handler)

    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Resolve vault root
    if vault_id:
        # Explicit --vault flag: look up from registry
        from ..vault_registry import list_vaults as _list_vaults, touch_vault as _touch
        _match = next((v for v in _list_vaults() if v["id"] == vault_id), None)
        if _match and Path(_match["path"]).exists():
            vault_root = Path(_match["path"])
            _touch(vault_id)
        else:
            click.echo(f"⚠️  Vault '{vault_id}' not found in registry.", err=True)
            raise SystemExit(1)
    elif orchestrator or orchestrator_status or list_agents or show_config:
        # Flag-based commands: use CWD-based resolution (no interactive prompt)
        vault_root = find_vault_root(Path(working_dir) if working_dir else None)
    else:
        # Interactive use: full vault resolution with selection prompt
        vault_root = resolve_vault(working_dir)

    # Store context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["working_dir"] = working_dir
    ctx.obj["config_file"] = config_file
    ctx.obj["debug"] = debug
    ctx.obj["mcp_config"] = mcp_config
    ctx.obj["vault_root"] = vault_root

    # If a subcommand was invoked, let it handle execution
    if ctx.invoked_subcommand is not None:
        return

    # Handle flag-based commands (shortcuts for subcommands)
    if orchestrator_status:
        ctx.invoke(orch_status, json_out=False)
    elif orchestrator:
        run_orchestrator_daemon(vault_path=vault_root, debug=debug, working_dir=working_dir, config_file=config_file, mcp_config=mcp_config)
    elif list_agents:
        ctx.invoke(orch_list_agents, json_out=False)
    elif show_config:
        show_config_handler()
    elif prompt_text or interactive_prompt or not any([orchestrator, orchestrator_status, list_agents, show_config]):
        # Check if onboarding is needed (first-time user)
        from .setup import needs_onboarding, run_onboarding
        if needs_onboarding(vault_root):
            run_onboarding(vault_root=vault_root)
            return

        # Auto-init .github symlink
        ensure_init(vault_root)

        # Check for WorkIQ auth expired flag
        from duckyai_cli.orchestrator.execution_manager import ExecutionManager
        from duckyai_cli.config import Config as _Config
        _cfg = _Config(vault_path=vault_root)
        _vault_id = _cfg.get("id", "default")
        if ExecutionManager.check_workiq_auth_flag(_vault_id):
            try:
                click.echo("\n⚠️  WorkIQ authentication expired (permission denied on last run).")
                response = input("Re-accept WorkIQ EULA now? (y/n): ").strip().lower()
                if response in ("y", "yes"):
                    from duckyai_cli.config import get_global_runtime_dir
                    ExecutionManager.clear_workiq_auth_flag(_vault_id)
                    click.echo("✓ Auth flag cleared. WorkIQ EULA will be re-accepted on next agent run.")
                    click.echo("  (If prompted by WorkIQ in your Copilot session, accept the EULA.)")
            except (EOFError, KeyboardInterrupt):
                pass

        # Auto-start orchestrator if enabled in duckyai.yaml
        from duckyai_cli.config import WorkspaceConfig
        ws_config = WorkspaceConfig(vault_path=vault_root)
        if ws_config.orchestrator_auto_start:
            freshly_started = ensure_orchestrator_running(vault_root, debug=debug)

            # Prompt Teams sync when orchestrator was freshly started
            if freshly_started:
                try:
                    response = input("\n🔄 Sync Teams chats & meetings now? (y/n): ").strip().lower()
                    if response in ("y", "yes"):
                        _enqueue_tcs_task(vault_root)
                        _enqueue_tms_task(vault_root)
                        click.echo("✓ TCS & TMS queued — orchestrator will pick them up shortly")
                except (EOFError, KeyboardInterrupt):
                    pass  # Non-interactive — skip prompt

        # Open vault in IDE
        _open_vault_in_ide(vault_root)

        # Launch Copilot (interactive if no -p flag)
        returncode = launch_copilot(
            vault_root,
            prompt=prompt_text,
            interactive_prompt=interactive_prompt,
            mcp_config=mcp_config,
            session_id=session_id,
            model=model,
        )
        sys.exit(returncode)


# Register subcommand groups
main.add_command(orchestrator_group)

# Keep 'trigger' as top-level subcommand for backward compat (duckyai trigger EIC)
from .trigger import trigger_cli
main.add_command(trigger_cli)

# Onboarding wizard
from .setup import setup_command, new_command
main.add_command(setup_command)
main.add_command(new_command)

# Voice AI
from .voice_cmd import voice_command
main.add_command(voice_command)


if __name__ == "__main__":
    main()
