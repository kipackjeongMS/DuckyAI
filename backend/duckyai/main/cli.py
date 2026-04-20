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

from .install_health import get_duckyai_launch_cmd
from .show_config import show_config as show_config_handler
from .orchestrator import run_orchestrator_daemon
from .orch_cmd import orchestrator_group, _cleanup_orchestrator_processes, _read_pid, orch_status, orch_list_agents
from .vault import find_vault_root, is_inside_vault, resolve_vault


def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) gracefully."""
    print("\n\nShutting down DuckyAI...")
    sys.exit(0)


def _get_onboarding_target(
    *,
    invoked_subcommand,
    orchestrator: bool,
    orchestrator_status: bool,
    show_config: bool,
    list_agents: bool,
    prompt_text: str | None,
    interactive_prompt: bool,
    working_dir: str | None,
) -> Path | None:
    """Return the path that should trigger first-run onboarding, if any."""
    from ..vault_registry import get_home_vault

    if invoked_subcommand is not None:
        return None

    if orchestrator or orchestrator_status or show_config or list_agents:
        return None

    if prompt_text or interactive_prompt:
        return None

    candidate = Path(working_dir).resolve() if working_dir else Path.cwd().resolve()
    if is_inside_vault(candidate):
        return None

    if get_home_vault():
        return None

    return candidate


def ensure_orchestrator_running(vault_root: Path, debug: bool = False):
    """Start the orchestrator as a detached background process if not already running.

    Delegates PID checks to orch_cmd module (single source of truth).

    Returns:
        True if orchestrator was freshly started, False if already running.
    """
    cleanup = _cleanup_orchestrator_processes(vault_root, fresh_start=False)
    if cleanup.get("healthy_pid"):
        return False  # already running

    pid_file = vault_root / ".orchestrator.pid"
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)

    if os.name == "nt":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000
        flags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        cmd = get_duckyai_launch_cmd("-o")
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
        cmd = get_duckyai_launch_cmd("-o")
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


def _select_ide() -> tuple | None:
    """Prompt user to pick an IDE and return the selection."""
    ides = _detect_ides()
    if not ides:
        return None

    if len(ides) == 1:
        return ides[0]

    # Multiple IDEs — use arrow-key selector
    from .vault import _interactive_select
    click.echo("\n🖥️  Open vault in: (↑↓ to move, Enter to select)\n")
    items = [{"name": name, "path": exe} for name, exe in ides]
    choice = _interactive_select(items, default_index=0)
    if choice is not None:
        return ides[choice]
    return None


def _open_vault_in_selected_ide(vault_root: Path, selected_ide: tuple | None):
    """Open the vault in the selected IDE."""
    if not selected_ide:
        return

    name, exe = selected_ide
    try:
        subprocess.Popen([exe, str(vault_root)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        click.echo(f"\n  ✓ Opened vault in {name}")
    except Exception:
        pass


def _open_vault_in_ide(vault_root: Path):
    """Backward-compatible wrapper that selects and opens the vault in an IDE."""
    _open_vault_in_selected_ide(vault_root, _select_ide())


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
        agent_params_line = f'\nagent_params:\n  lookback_hours: {lookback_hours}\n  ignore_watermark: true'
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
        agent_params_line = f'\nagent_params:\n  lookback_hours: {lookback_hours}\n  ignore_watermark: true'
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


def _prompt_startup_teams_sync(vault_root: Path) -> None:
    """Prompt to queue Teams sync after startup orchestration is ready."""
    from .trigger_agent import _prompt_yn, _prompt_teams_sync_lookback
    from rich.console import Console

    try:
        if _prompt_yn("\n🔄 Sync Teams chats & meetings now?"):
            override = _prompt_teams_sync_lookback(vault_root, Console())
            lookback_hours = override.get("lookback_hours") if override else None
            _enqueue_tcs_task(vault_root, lookback_hours=lookback_hours)
            _enqueue_tms_task(vault_root, lookback_hours=lookback_hours)
            click.echo("✓ TCS & TMS queued — orchestrator will pick them up shortly")
    except (EOFError, KeyboardInterrupt):
        pass


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
    """Auto-init user directories: .github/skills/, prompts-agent/, and runtime dirs.

    Syncs built-in agent prompt files from the CLI package's .playbook/ into
    .github/prompts-agent/ so the orchestrator daemon can always find them
    regardless of how the editable install resolves at startup time.
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

    # Sync CLI-managed copilot-instructions.md from playbook (always kept up to date)
    playbook_ci = Path(__file__).resolve().parent.parent / '.playbook' / 'copilot-instructions.md'
    ci_file = github_dir / 'copilot-instructions.md'
    if playbook_ci.exists():
        import shutil as _shutil
        _shutil.copy2(str(playbook_ci), str(ci_file))

    # Sync built-in agent prompt files into .github/prompts-agent/
    # This ensures the orchestrator can find them even if the playbook path
    # is unreachable (e.g., editable install points to a stale worktree).
    playbook_prompts = Path(__file__).resolve().parent.parent / '.playbook' / 'prompts-agent'
    if playbook_prompts.is_dir():
        import shutil as _shutil2
        prompts_dir = github_dir / 'prompts-agent'
        prompts_dir.mkdir(parents=True, exist_ok=True)
        for prompt_file in playbook_prompts.glob('*.md'):
            target = prompts_dir / prompt_file.name
            # Always sync built-in prompts (overwrite with latest version)
            _shutil2.copy2(str(prompt_file), str(target))

    # Create user customizations stub if it doesn't exist (never overwritten)
    user_ci_file = github_dir / 'copilot-instructions-user.md'
    if not user_ci_file.exists():
        user_ci_file.write_text(
            "# My Customizations\n\n"
            "This file is yours — the DuckyAI CLI will never overwrite it.\n"
            "Add your personal context here: role, team, technologies, aliases, domain knowledge.\n\n"
            "## About Me\n\n"
            "- **Role:** \n"
            "- **Team:** \n"
            "- **Technologies:** \n\n"
            "## Person Aliases\n\n"
            "| Alias | Links To |\n"
            "|-------|----------|\n"
            "| | |\n\n"
            "## Domain Knowledge\n\n"
            "<!-- Add any domain-specific context here -->\n",
            encoding="utf-8"
        )

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
    from duckyai.config import get_global_runtime_dir, CONFIG_FILENAME
    try:
        # Read vault_id from duckyai.yml
        import yaml
        config_path = vault_root / CONFIG_FILENAME
        vault_id = "default"
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
                vault_id = data.get("id", "default")
        runtime_dir = get_global_runtime_dir(vault_id, vault_path=vault_root)
        for subdir in ["tasks", "logs", "history"]:
            (runtime_dir / subdir).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass  # non-critical

    # Ensure services directory and .services junction exist
    try:
        from ..services import ensure_services_dir
        ensure_services_dir(vault_root)
    except Exception:
        pass  # non-critical


def _resolve_node_cmd_shim(cmd_name: str) -> tuple[str, list[str]] | None:
    """Resolve a Node.js .cmd shim to (node_path, [js_entry_point]).

    On Windows, npm creates .cmd wrapper scripts that cannot be spawned by
    Node.js child_process.spawn() without shell=true.  The Copilot CLI's
    MCP server launcher uses spawn(), so .cmd commands silently fail.

    This function reads the .cmd file to extract the underlying .js entry
    point and returns a (node, [script.js]) pair that spawn() can handle.

    Returns None if the command isn't a .cmd shim or can't be resolved.
    """
    if os.name != "nt":
        return None

    resolved = shutil.which(cmd_name)
    if not resolved:
        return None

    # Only process .cmd files
    if not resolved.lower().endswith(".cmd"):
        return None

    try:
        content = Path(resolved).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # npm .cmd shims end with a line like:
    #   "%_prog%" "%dp0%\node_modules\@pkg\bin\entry.js" %*
    # Extract the .js path relative to the cmd file's directory
    import re
    # Match patterns like "%dp0%\path\to\file.js" or "%dp0%/path/to/file.js"
    match = re.search(r'"%dp0%[\\\/]([^"]+\.js)"', content)
    if not match:
        return None

    js_rel = match.group(1)
    cmd_dir = Path(resolved).parent
    js_path = cmd_dir / js_rel

    if not js_path.exists():
        return None

    node = shutil.which("node")
    if not node:
        return None

    return (node, [str(js_path)])


def get_mcp_config(vault_root: Path) -> str:
    """Build MCP config JSON for DuckyAI MCP servers."""
    config = {"mcpServers": {}}

    config["mcpServers"]["duckyai-vault"] = {
        "command": "duckyai-vault-mcp",
        "args": [],
        "env": {"DUCKYAI_VAULT_ROOT": str(vault_root)},
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
    # On Windows, npx is a .cmd shim that Node.js child_process.spawn()
    # cannot execute.  Resolve to a direct node invocation instead.
    workiq_resolved = _resolve_node_cmd_shim("workiq")
    if workiq_resolved:
        node_bin, js_args = workiq_resolved
        config["mcpServers"]["workiq"] = {
            "command": node_bin,
            "args": js_args + ["mcp"],
        }
    else:
        # Fallback: use npx (works on macOS/Linux where npx isn't a .cmd)
        config["mcpServers"]["workiq"] = {
            "command": "npx",
            "args": ["-y", "@microsoft/workiq", "mcp"]
        }

    return json.dumps(config) if config["mcpServers"] else None


def _resolve_copilot_command() -> list[str]:
    """Resolve the best available Copilot launcher for the current platform."""
    if os.name == "nt":
        for candidate in ("copilot.exe", "copilot.bat", "copilot"):
            resolved = shutil.which(candidate)
            if resolved:
                return [resolved]
    return ["copilot"]


def _launch_copilot_in_new_terminal(cmd: list[str], vault_root: Path) -> int:
    """Launch Copilot in a separate terminal window when supported."""
    if os.name == "nt":
        CREATE_NEW_CONSOLE = 0x00000010
        subprocess.Popen(
            cmd,
            cwd=str(vault_root),
            creationflags=CREATE_NEW_CONSOLE,
        )
        click.echo("Launching Copilot in a new terminal...")
        return 0

    result = subprocess.run(cmd, cwd=str(vault_root))
    return result.returncode


def launch_copilot(vault_root: Path, prompt: str = None, interactive_prompt: str = None,
                   mcp_config: tuple = None, session_id: str = None, model: str = None):
    """Launch GitHub Copilot CLI from the vault root."""
    cmd = _resolve_copilot_command()

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
        if prompt is None:
            return _launch_copilot_in_new_terminal(cmd, vault_root)

        result = subprocess.run(cmd, cwd=str(vault_root))
        return result.returncode
    except FileNotFoundError:
        click.echo("Error: 'copilot' CLI not found. Install GitHub Copilot CLI first.", err=True)
        click.echo("  brew install gh && gh extension install github/gh-copilot", err=True)
        return 1


def _show_global_orchestrator_status():
    """Show orchestrator status for the configured home vault."""
    from ..vault_registry import get_home_vault
    from rich.table import Table
    from rich.console import Console

    home_vault = get_home_vault()
    if not home_vault:
        click.echo("No home vault configured. Use 'duckyai init' or 'duckyai setup'.")
        return

    table = Table(title="Orchestrator Status")
    table.add_column("Vault", style="cyan bold")
    table.add_column("Status", justify="center")
    table.add_column("PID", justify="right")
    table.add_column("Agents", justify="right")
    table.add_column("Path")

    vault_path = Path(home_vault["path"])
    if not vault_path.exists():
        table.add_row(home_vault["name"], "⚠️  Missing", "-", "-", home_vault["path"])
    else:
        pid, alive = _read_pid(vault_path)
        status_str = "🟢 Running" if alive else "🔴 Stopped"
        pid_str = str(pid) if pid else "-"

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

        table.add_row(home_vault["name"], status_str, pid_str, agent_count, home_vault["path"])

    Console().print(table)


def _show_global_agents():
    """Show agents for the configured home vault."""
    from ..vault_registry import get_home_vault
    from ..config import Config
    from ..orchestrator.core import Orchestrator
    from rich.table import Table
    from rich.console import Console

    home_vault = get_home_vault()
    if not home_vault:
        click.echo("No home vault configured. Use 'duckyai init' or 'duckyai setup'.")
        return

    table = Table(title="Agents")
    table.add_column("Vault", style="cyan")
    table.add_column("Abbr", style="bold")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Cron")

    vault_path = Path(home_vault["path"])
    if vault_path.exists():
        try:
            config = Config(vault_path=vault_path)
            orch = Orchestrator(vault_path=vault_path, config=config)
            status = orch.get_status()
            for a in status.get("agent_list", []):
                agent_obj = orch.agent_registry.agents.get(a["abbreviation"])
                cron = agent_obj.cron if agent_obj else "-"
                table.add_row(
                    home_vault["name"], a["abbreviation"], a["name"],
                    a.get("category", "-"), cron or "-"
                )
        except Exception:
            table.add_row(home_vault["name"], "⚠️", "Error loading agents", "-", "-")

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

    onboarding_target = _get_onboarding_target(
        invoked_subcommand=ctx.invoked_subcommand,
        orchestrator=orchestrator,
        orchestrator_status=orchestrator_status,
        show_config=show_config,
        list_agents=list_agents,
        prompt_text=prompt_text,
        interactive_prompt=interactive_prompt,
        working_dir=working_dir,
    )
    if onboarding_target is not None:
        from .setup import run_onboarding

        click.echo("No home vault configured. Starting first-time setup...")
        run_onboarding(vault_root=onboarding_target)
        return

    # Resolve vault root
    vault_root = None
    if ctx.invoked_subcommand is not None:
        # Subcommand will handle its own vault resolution if needed
        from .vault import is_inside_vault
        candidate = Path(working_dir) if working_dir else None
        if is_inside_vault(candidate):
            vault_root = find_vault_root(candidate)
        else:
            vault_root = resolve_vault(working_dir)
    elif orchestrator or show_config or orchestrator_status or list_agents:
        vault_root = resolve_vault(working_dir)
    else:
        vault_root = resolve_vault(working_dir)

    # Store context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["working_dir"] = working_dir
    ctx.obj["config_file"] = config_file
    ctx.obj["debug"] = debug
    ctx.obj["mcp_config"] = mcp_config
    ctx.obj["vault_root"] = vault_root

    # Reconfigure logger for the resolved vault
    if vault_root:
        from .trigger_agent import logger as _trig_logger
        from ..logger import Logger
        Logger(console_output=True).reconfigure(vault_root)

    # If a subcommand was invoked, let it handle execution
    if ctx.invoked_subcommand is not None:
        return

    # Handle flag-based commands (shortcuts for subcommands)
    if orchestrator_status:
        if vault_root:
            ctx.invoke(orch_status, json_out=False)
        else:
            _show_global_orchestrator_status()
    elif orchestrator:
        run_orchestrator_daemon(vault_path=vault_root, debug=debug, working_dir=working_dir, config_file=config_file, mcp_config=mcp_config)
    elif list_agents:
        if vault_root:
            ctx.invoke(orch_list_agents, json_out=False)
        else:
            _show_global_agents()
    elif show_config:
        show_config_handler(vault_root)
    elif prompt_text or interactive_prompt or not any([orchestrator, orchestrator_status, list_agents, show_config]):
        # Auto-init .github symlink, skills, services junction, etc.
        ensure_init(vault_root)

        # Check for WorkIQ auth expired flag (interactive TTY only)
        from duckyai.orchestrator.execution_manager import ExecutionManager
        from duckyai.config import Config as _Config
        _cfg = _Config(vault_path=vault_root)
        _vault_id = _cfg.get("id", "default")
        if sys.stdin and sys.stdin.isatty() and ExecutionManager.check_workiq_auth_flag(_vault_id, vault_path=vault_root):
            try:
                click.echo("\n⚠️  WorkIQ authentication expired (permission denied on last run).")
                from .trigger_agent import _prompt_yn
                if _prompt_yn("Re-accept WorkIQ EULA now?"):
                    ExecutionManager.clear_workiq_auth_flag(_vault_id, vault_path=vault_root)
                    click.echo("✓ Auth flag cleared. WorkIQ EULA will be re-accepted on next agent run.")
                    click.echo("  (If prompted by WorkIQ in your Copilot session, accept the EULA.)")
            except (EOFError, KeyboardInterrupt):
                pass

        # Ask for IDE selection first so startup ordering stays consistent
        selected_ide = _select_ide()

        # Auto-start orchestrator if enabled in duckyai.yml, after IDE open flow
        from duckyai.config import Config
        ws_config = Config(vault_path=vault_root)
        if ws_config.orchestrator_auto_start:
            click.echo("Starting orchestrator background service...")
            ensure_orchestrator_running(vault_root, debug=debug)
            _prompt_startup_teams_sync(vault_root)

        # Open vault in IDE after background startup and sync prompt
        _open_vault_in_selected_ide(vault_root, selected_ide)

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
from .vault_cmd import init_command, vault_group
main.add_command(vault_group)
main.add_command(init_command)

# Onboarding wizard
from .setup import setup_command
main.add_command(setup_command)

# Service management
from .service_cmd import service_group
main.add_command(service_group)

# Installation diagnostics / repair
from .doctor import doctor_command
main.add_command(doctor_command)

# Chat server
from .chat_cmd import chat_group
main.add_command(chat_group)


if __name__ == "__main__":
    main()
