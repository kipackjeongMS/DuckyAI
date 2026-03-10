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
from .orch_cmd import orchestrator_group, _read_pid, _is_orchestrator_alive, orch_status, orch_list_agents
from .vault import find_vault_root


def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) gracefully."""
    print("\n\nShutting down DuckyAI...")
    sys.exit(0)


def ensure_orchestrator_running(vault_root: Path, debug: bool = False):
    """Start the orchestrator as a detached background process if not already running.

    Delegates PID checks to orch_cmd module (single source of truth).
    """
    pid, alive = _read_pid(vault_root)
    if alive:
        return  # already running

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
        except Exception as e:
            click.echo(f"⚠️  Failed to auto-start orchestrator: {e}", err=True)
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
        except Exception as e:
            click.echo(f"⚠️  Failed to auto-start orchestrator: {e}", err=True)


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

    # Vault MCP server (TypeScript/Node)
    mcp_index = vault_root / 'mcp-server' / 'dist' / 'index.js'
    if mcp_index.exists():
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

    # Resolve vault root
    vault_root = find_vault_root(Path(working_dir) if working_dir else None)

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
        run_orchestrator_daemon(debug=debug, working_dir=working_dir, config_file=config_file, mcp_config=mcp_config)
    elif list_agents:
        ctx.invoke(orch_list_agents, json_out=False)
    elif show_config:
        show_config_handler()
    elif prompt_text or interactive_prompt or not any([orchestrator, orchestrator_status, list_agents, show_config]):
        # Auto-init .github symlink
        ensure_init(vault_root)

        # Auto-start orchestrator if enabled in duckyai.yaml
        from duckyai_cli.config import WorkspaceConfig
        ws_config = WorkspaceConfig(vault_path=vault_root)
        if ws_config.orchestrator_auto_start:
            ensure_orchestrator_running(vault_root, debug=debug)

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


if __name__ == "__main__":
    main()
