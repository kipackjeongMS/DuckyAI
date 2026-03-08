#!/usr/bin/env python3
"""Main entry point for DuckyAI CLI — an AI-powered developer assistant."""

import json
import os
import signal
import subprocess
import sys
import click
import logging
from pathlib import Path

from .list_agents import list_agents as list_agents_handler
from .show_config import show_config as show_config_handler
from .orchestrator import run_orchestrator_daemon, show_orchestrator_status
from .update import update_cli
from .template import template_group
from .trigger import trigger_cli
from .run import run_command
from .init import init_vault
from .vault import find_vault_root


def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) gracefully."""
    print("\n\nShutting down DuckyAI...")
    sys.exit(0)


def ensure_init(vault_root: Path):
    """Auto-init .github symlink and .duckyai runtime dirs if missing."""
    cli_playbook = Path(__file__).parent.parent / '.playbook'

    # Symlink .github
    github_dir = vault_root / '.github'
    if not github_dir.is_symlink() and cli_playbook.exists() and not github_dir.exists():
        rel_path = os.path.relpath(cli_playbook, vault_root)
        os.symlink(rel_path, github_dir)

    # Create .duckyai runtime dirs
    for d in ['.duckyai/tasks', '.duckyai/logs', '.duckyai/history']:
        (vault_root / d).mkdir(parents=True, exist_ok=True)


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
        duckyai run new-task             # Run a specific prompt
        duckyai trigger GDR              # Trigger an agent
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

    # Handle flag-based commands
    if orchestrator_status:
        show_orchestrator_status(working_dir=working_dir, config_file=config_file)
    elif orchestrator:
        run_orchestrator_daemon(debug=debug, working_dir=working_dir, config_file=config_file, mcp_config=mcp_config)
    elif list_agents:
        list_agents_handler()
    elif show_config:
        show_config_handler()
    elif prompt_text or interactive_prompt or not any([orchestrator, orchestrator_status, list_agents, show_config]):
        # Auto-init .github symlink
        ensure_init(vault_root)

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


# Register subcommands
main.add_command(trigger_cli, name="trigger")
main.add_command(update_cli, name="update")
main.add_command(template_group, name="template")
main.add_command(run_command, name="run")
main.add_command(init_vault, name="init")


if __name__ == "__main__":
    main()
