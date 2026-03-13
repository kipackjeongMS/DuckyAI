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


def _enqueue_tcs_task(vault_root: Path, lookback_hours: int = None):
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
    agent_params_line = ""
    if lookback_hours is not None:
        agent_params_line = f'\nagent_params:\n  lookback_hours: {lookback_hours}'
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
trigger_data_json: "{trigger_data}"{agent_params_line}
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


def _enqueue_tms_task(vault_root: Path, lookback_hours: int = None):
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
    agent_params_line = ""
    if lookback_hours is not None:
        agent_params_line = f'\nagent_params:\n  lookback_hours: {lookback_hours}'
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
trigger_data_json: "{trigger_data}"{agent_params_line}
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
    from duckyai_cli.config import get_global_runtime_dir, CONFIG_FILENAME
    try:
        # Read vault_id from duckyai.yml
        import yaml
        config_path = vault_root / CONFIG_FILENAME
        vault_id = "default"
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as fh:
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

    # Vault MCP server — resolve from vault root first, then installed package location
    mcp_index = vault_root / 'cli' / 'mcp-server' / 'dist' / 'index.js'
    if not mcp_index.exists():
        # Fallback: resolve relative to installed duckyai_cli package
        # Package layout: cli/duckyai_cli/ and cli/mcp-server/ are siblings
        pkg_dir = Path(__file__).resolve().parent  # duckyai_cli/main/
        mcp_index = pkg_dir.parent.parent / 'mcp-server' / 'dist' / 'index.js'
        if not mcp_index.exists():
            mcp_index = None

    if mcp_index:
        config["mcpServers"]["duckyai-vault"] = {
            "command": "node",
            "args": [str(mcp_index)],
            "env": {"DUCKYAI_VAULT_ROOT": str(vault_root)}
        }

    # Release Dashboard MCP server (Python)
    rd_pkg = vault_root / 'cli' / 'mcp-server' / 'release-dashboard' / 'src' / 'release_dashboard_mcp' / 'server.py'
    if rd_pkg.exists():
        rd_config = vault_root / 'cli' / 'mcp-server' / 'release-dashboard' / 'config.yaml'
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


def _show_global_orchestrator_status():
    """Show orchestrator status for all registered vaults."""
    from ..vault_registry import list_vaults
    from rich.table import Table
    from rich.console import Console

    vaults = list_vaults()
    if not vaults:
        click.echo("No vaults registered. Use 'duckyai vault new <path>' or 'duckyai init'.")
        return

    table = Table(title="Orchestrator Status (All Vaults)")
    table.add_column("Vault", style="cyan bold")
    table.add_column("Status", justify="center")
    table.add_column("PID", justify="right")
    table.add_column("Agents", justify="right")
    table.add_column("Path")

    for v in vaults:
        vault_path = Path(v["path"])
        if not vault_path.exists():
            table.add_row(v["name"], "⚠️  Missing", "-", "-", v["path"])
            continue

        pid, alive = _read_pid(vault_path)
        status_str = "🟢 Running" if alive else "🔴 Stopped"
        pid_str = str(pid) if pid else "-"

        # Count agents from config
        agent_count = "-"
        try:
            from ..config import Config
            from ..orchestrator.core import Orchestrator
            config = Config(vault_path=vault_path)
            orch = Orchestrator(vault_path=vault_path, config=config)
            status = orch.get_status()
            agent_count = str(status.get("agents_loaded", 0))
        except Exception:
            pass

        table.add_row(v["name"], status_str, pid_str, agent_count, v["path"])

    Console().print(table)


def _show_global_agents():
    """Show agents for all registered vaults."""
    from ..vault_registry import list_vaults
    from ..config import Config
    from ..orchestrator.core import Orchestrator
    from rich.table import Table
    from rich.console import Console

    vaults = list_vaults()
    if not vaults:
        click.echo("No vaults registered. Use 'duckyai vault new <path>' or 'duckyai init'.")
        return

    table = Table(title="Agents (All Vaults)")
    table.add_column("Vault", style="cyan")
    table.add_column("Abbr", style="bold")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Cron")

    for v in vaults:
        vault_path = Path(v["path"])
        if not vault_path.exists():
            continue

        try:
            config = Config(vault_path=vault_path)
            orch = Orchestrator(vault_path=vault_path, config=config)
            status = orch.get_status()
            for a in status.get("agent_list", []):
                agent_obj = orch.agent_registry.agents.get(a["abbreviation"])
                cron = agent_obj.cron if agent_obj else "-"
                table.add_row(
                    v["name"], a["abbreviation"], a["name"],
                    a.get("category", "-"), cron or "-"
                )
        except Exception:
            table.add_row(v["name"], "⚠️", "Error loading agents", "-", "-")

    Console().print(table)


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
    help="Path to vault config file (default: duckyai.yml)",
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
    vault_root = None
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
    elif ctx.invoked_subcommand is not None:
        # Subcommand will handle its own vault resolution if needed
        # Only resolve if CWD is inside a vault (cheap, no prompts)
        from .vault import is_inside_vault
        if is_inside_vault(Path(working_dir) if working_dir else None):
            vault_root = find_vault_root(Path(working_dir) if working_dir else None)
    elif orchestrator or show_config:
        # Flag-based commands that need a specific vault
        vault_root = find_vault_root(Path(working_dir) if working_dir else None)
    elif orchestrator_status or list_agents:
        # Global commands: vault_root stays None → triggers multi-vault display
        pass
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
    ctx.obj["vault_explicit"] = bool(vault_id)

    # If a subcommand was invoked, let it handle execution
    if ctx.invoked_subcommand is not None:
        return

    # Handle flag-based commands (shortcuts for subcommands)
    if orchestrator_status:
        if vault_id:
            # Single vault status
            ctx.invoke(orch_status, json_out=False)
        else:
            # Global status: show all vaults
            _show_global_orchestrator_status()
    elif orchestrator:
        run_orchestrator_daemon(vault_path=vault_root, debug=debug, working_dir=working_dir, config_file=config_file, mcp_config=mcp_config)
    elif list_agents:
        if vault_id:
            ctx.invoke(orch_list_agents, json_out=False)
        else:
            _show_global_agents()
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

        # Auto-start orchestrator if enabled in duckyai.yml
        from duckyai_cli.config import Config
        ws_config = Config(vault_path=vault_root)
        if ws_config.orchestrator_auto_start:
            freshly_started = ensure_orchestrator_running(vault_root, debug=debug)

            # Prompt Teams sync when orchestrator was freshly started
            if freshly_started:
                try:
                    response = input("\n🔄 Sync Teams chats & meetings now? (y/n): ").strip().lower()
                    if response in ("y", "yes"):
                        from .trigger_agent import _read_watermark, _prompt_lookback_or_watermark
                        from rich.console import Console
                        console = Console()

                        for abbr, default_h in [("TCS", 1), ("TMS", 24)]:
                            last_synced = _read_watermark(vault_root, abbr)
                            override = _prompt_lookback_or_watermark(abbr, default_h, last_synced, console)
                            lbh = override.get('lookback_hours') if override else None
                            _enqueue_tcs_task(vault_root, lookback_hours=lbh) if abbr == "TCS" else _enqueue_tms_task(vault_root, lookback_hours=lbh)

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

# Vault management (global scope)
from .vault_cmd import vault_group
main.add_command(vault_group)

# Onboarding wizard
from .setup import setup_command
main.add_command(setup_command)

# Voice AI
from .voice_cmd import voice_command
main.add_command(voice_command)


if __name__ == "__main__":
    main()
