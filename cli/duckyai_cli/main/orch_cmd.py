"""Orchestrator CLI subcommand group.

Single source of truth for all orchestrator lifecycle operations.
MCP server delegates to these subcommands via `duckyai orchestrator <cmd> --json`.
"""

import json
import os
import signal
import sys
import time
import shutil
import subprocess
from pathlib import Path

import click

from ..logger import Logger

logger = Logger(console_output=True)


def _is_orchestrator_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    if os.name == "nt":
        # Windows: os.kill(pid, 0) doesn't work reliably; use ctypes
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except (OSError, ProcessLookupError):
            return False


def _read_pid(vault_root: Path):
    """Read PID from .orchestrator.pid file. Returns (pid, alive) or (None, False)."""
    pid_file = vault_root / ".orchestrator.pid"
    if not pid_file.exists():
        return None, False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        return pid, _is_orchestrator_alive(pid)
    except (ValueError, OSError):
        return None, False


def _get_vault_root(ctx) -> Path:
    """Resolve vault root from click context."""
    obj = ctx.obj or {}
    if obj.get("vault_root"):
        return Path(obj["vault_root"])
    from .vault import find_vault_root
    working_dir = obj.get("working_dir")
    return find_vault_root(Path(working_dir) if working_dir else None)


@click.group("orchestrator")
@click.pass_context
def orchestrator_group(ctx):
    """Manage the DuckyAI orchestrator daemon.

    \b
    Examples:
        duckyai orchestrator start        # Start daemon
        duckyai orchestrator stop         # Stop daemon
        duckyai orchestrator status       # Show status
        duckyai orchestrator list-agents  # List loaded agents
        duckyai orchestrator trigger EIC  # Trigger an agent
    """
    ctx.ensure_object(dict)


# =============================================================================
# duckyai orchestrator start
# =============================================================================
@orchestrator_group.command("start")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON for machine consumption")
@click.pass_context
def orch_start(ctx, json_out):
    """Start the orchestrator as a detached background daemon."""
    vault_root = _get_vault_root(ctx)
    pid_file = vault_root / ".orchestrator.pid"

    # Check if already running
    pid, alive = _read_pid(vault_root)
    if alive:
        if json_out:
            click.echo(json.dumps({"status": "already_running", "pid": pid}))
        else:
            click.echo(f"Orchestrator already running (PID {pid}).")
        return

    # Clean stale PID file
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)

    # Check orchestrator.yaml exists
    orch_yaml = vault_root / "orchestrator.yaml"
    if not orch_yaml.exists():
        if json_out:
            click.echo(json.dumps({"status": "error", "message": "orchestrator.yaml not found"}))
        else:
            click.echo("orchestrator.yaml not found. Run 'duckyai init' first.", err=True)
        sys.exit(1)

    # Spawn orchestrator as detached background process
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
            # Wait for PID file to appear (written by daemon on startup)
            new_pid = proc.pid
            for _ in range(10):
                if pid_file.exists():
                    try:
                        new_pid = int(pid_file.read_text(encoding="utf-8").strip())
                        break
                    except (ValueError, OSError):
                        pass
                time.sleep(0.5)

            if json_out:
                click.echo(json.dumps({"status": "started", "pid": new_pid}))
            else:
                click.echo(f"🚀 Orchestrator started (PID {new_pid})")
        except Exception as e:
            if json_out:
                click.echo(json.dumps({"status": "error", "message": str(e)}))
            else:
                click.echo(f"⚠️  Failed to start orchestrator: {e}", err=True)
            sys.exit(1)
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
            if json_out:
                click.echo(json.dumps({"status": "started", "pid": proc.pid}))
            else:
                click.echo(f"🚀 Orchestrator started (PID {proc.pid})")
        except Exception as e:
            if json_out:
                click.echo(json.dumps({"status": "error", "message": str(e)}))
            else:
                click.echo(f"⚠️  Failed to start orchestrator: {e}", err=True)
            sys.exit(1)


# =============================================================================
# duckyai orchestrator stop
# =============================================================================
@orchestrator_group.command("stop")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON for machine consumption")
@click.pass_context
def orch_stop(ctx, json_out):
    """Stop the running orchestrator daemon."""
    vault_root = _get_vault_root(ctx)
    pid_file = vault_root / ".orchestrator.pid"

    pid, alive = _read_pid(vault_root)

    if not pid:
        if json_out:
            click.echo(json.dumps({"status": "not_running"}))
        else:
            click.echo("No orchestrator is currently running.")
        return

    if alive:
        try:
            if os.name == "nt":
                os.kill(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
            pid_file.unlink(missing_ok=True)
            if json_out:
                click.echo(json.dumps({"status": "stopped", "pid": pid}))
            else:
                click.echo(f"✅ Orchestrator stopped (PID {pid}).")
        except Exception as e:
            pid_file.unlink(missing_ok=True)
            if json_out:
                click.echo(json.dumps({"status": "error", "message": str(e)}))
            else:
                click.echo(f"⚠️  Failed to stop orchestrator: {e}", err=True)
    else:
        # Stale PID file
        pid_file.unlink(missing_ok=True)
        if json_out:
            click.echo(json.dumps({"status": "not_running", "message": "Stale PID file cleaned up"}))
        else:
            click.echo("Orchestrator was not running (stale PID file cleaned up).")


# =============================================================================
# duckyai orchestrator status
# =============================================================================
@orchestrator_group.command("status")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON for machine consumption")
@click.pass_context
def orch_status(ctx, json_out):
    """Show orchestrator status, loaded agents, and schedules."""
    from ..config import Config
    from ..orchestrator.core import Orchestrator
    from rich.panel import Panel

    obj = ctx.obj or {}
    vault_root = _get_vault_root(ctx)
    config_file = obj.get("config_file")
    working_dir = obj.get("working_dir")

    config = Config(
        config_file=str(config_file) if config_file else None,
        vault_path=vault_root,
    )

    # Check running state
    pid, alive = _read_pid(vault_root)

    # Load agent registry (read-only, don't start daemon)
    try:
        orch = Orchestrator(
            vault_path=vault_root,
            config=config,
            working_dir=Path(working_dir) if working_dir else None,
        )
        status = orch.get_status()
        pollers_list = list(orch.poller_manager.pollers.items())
    except Exception as e:
        if json_out:
            click.echo(json.dumps({
                "running": alive,
                "pid": pid,
                "error": str(e),
            }))
        else:
            click.echo(f"⚠️  Error loading orchestrator config: {e}", err=True)
        return

    if json_out:
        agents = []
        for a in status.get("agent_list", []):
            agent_data = {
                "abbreviation": a["abbreviation"],
                "name": a["name"],
                "category": a["category"],
            }
            # Include optional fields from agent registry
            agent_obj = orch.agent_registry.agents.get(a["abbreviation"])
            if agent_obj:
                agent_data["input_path"] = agent_obj.input_path
                agent_data["output_path"] = agent_obj.output_path
                agent_data["cron"] = agent_obj.cron
                agent_data["enabled"] = True
            agents.append(agent_data)

        pollers = []
        for pname, poller in pollers_list:
            pollers.append({
                "name": pname,
                "target_dir": poller.poller_config.get("target_dir", str(poller.target_dir)),
                "poll_interval": poller.poll_interval,
            })

        result = {
            "running": alive,
            "pid": pid,
            "vault_path": str(vault_root),
            "agents_loaded": status.get("agents_loaded", 0),
            "agents": agents,
            "pollers_loaded": len(pollers_list),
            "pollers": pollers,
            "max_concurrent": status.get("max_concurrent"),
        }
        click.echo(json.dumps(result))
    else:
        running_str = f"🟢 Running (PID {pid})" if alive else "🔴 Stopped"
        logger.info(Panel.fit(
            f"[bold]Status:[/bold] {running_str}\n"
            f"[bold]Vault:[/bold] {status['vault_path']}\n"
            f"[bold]Agents loaded:[/bold] {status['agents_loaded']}\n"
            f"[bold]Pollers loaded:[/bold] {len(pollers_list)}\n"
            f"[bold]Max concurrent:[/bold] {status['max_concurrent']}",
            title="Orchestrator Status",
        ))

        if status.get("agent_list"):
            logger.info("\n[bold]Available Agents:[/bold]")
            for a in status["agent_list"]:
                logger.info(
                    f"  • [{a['abbreviation']}] {a['name']}\n"
                    f"    Category: {a['category']}"
                )

        if pollers_list:
            logger.info("\n[bold]Available Pollers:[/bold]")
            for pname, poller in sorted(pollers_list, key=lambda p: p[0]):
                target_dir_rel = poller.poller_config.get("target_dir", str(poller.target_dir))
                logger.info(
                    f"  • {pname}\n"
                    f"    Target: {target_dir_rel}\n"
                    f"    Interval: {poller.poll_interval}s"
                )


# =============================================================================
# duckyai orchestrator list-agents
# =============================================================================
@orchestrator_group.command("list-agents")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON for machine consumption")
@click.pass_context
def orch_list_agents(ctx, json_out):
    """List available agents and their configuration."""
    from ..config import Config
    from ..orchestrator.core import Orchestrator
    from rich.table import Table

    obj = ctx.obj or {}
    vault_root = _get_vault_root(ctx)
    config_file = obj.get("config_file")
    working_dir = obj.get("working_dir")

    config = Config(
        config_file=str(config_file) if config_file else None,
        vault_path=vault_root,
    )

    try:
        orch = Orchestrator(
            vault_path=vault_root,
            config=config,
            working_dir=Path(working_dir) if working_dir else None,
        )
    except Exception as e:
        if json_out:
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"⚠️  Error loading orchestrator: {e}", err=True)
        return

    sorted_agents = sorted(
        orch.agent_registry.agents.values(),
        key=lambda a: a.abbreviation,
    )

    if json_out:
        agents = []
        for agent in sorted_agents:
            input_path = (
                ", ".join(agent.input_path)
                if isinstance(agent.input_path, list)
                else (agent.input_path or None)
            )
            agents.append({
                "abbreviation": agent.abbreviation,
                "name": agent.name,
                "category": agent.category,
                "input_path": input_path,
                "output_path": agent.output_path or None,
                "cron": agent.cron or None,
            })
        click.echo(json.dumps({"agents": agents}))
    else:
        if not sorted_agents:
            logger.info("[yellow]No agents found.[/yellow]")
            return

        table = Table(title="Available Agents")
        table.add_column("Abbreviation", style="cyan", no_wrap=True)
        table.add_column("Name", style="bold")
        table.add_column("Category", style="green")
        table.add_column("Input Path", style="dim")
        table.add_column("Output Path", style="dim")
        table.add_column("Cron", style="yellow")

        for agent in sorted_agents:
            input_path = (
                ", ".join(agent.input_path)
                if isinstance(agent.input_path, list)
                else (agent.input_path or "—")
            )
            table.add_row(
                agent.abbreviation,
                agent.name,
                agent.category,
                input_path,
                agent.output_path or "—",
                agent.cron or "—",
            )

        logger.info(table)


# =============================================================================
# duckyai orchestrator trigger
# =============================================================================
@orchestrator_group.command("trigger")
@click.argument("agent", required=False, default=None)
@click.option("--file", "input_file", default=None, help="Input file path to pass to the agent (relative to vault root)")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON for machine consumption")
@click.option(
    "--mcp-config",
    "mcp_config",
    multiple=True,
    help="Load MCP servers from JSON files or strings (can be specified multiple times)",
)
@click.option(
    "--claude-settings",
    "claude_settings",
    type=str,
    help="Path to settings JSON file or JSON string for Claude Code",
)
@click.pass_context
def orch_trigger(ctx, agent, input_file, json_out, mcp_config, claude_settings):
    """Trigger an orchestrator agent by abbreviation.

    \b
    If AGENT is provided, triggers it directly.
    Otherwise, shows an interactive selector (human mode only).

    \b
    Examples:
        duckyai orchestrator trigger EIC
        duckyai orchestrator trigger EIC --file 00-Inbox/article.md
        duckyai orchestrator trigger --json-output EIC
    """
    obj = ctx.obj or {}
    working_dir = obj.get("working_dir")
    config_file = obj.get("config_file")
    parent_mcp_config = obj.get("mcp_config", ())
    combined_mcp_config = parent_mcp_config + mcp_config if mcp_config else parent_mcp_config
    effective_claude_settings = claude_settings or obj.get("claude_settings")

    # Auto-discover MCP config if none provided
    if not combined_mcp_config:
        from .cli import get_mcp_config
        from .vault import find_vault_root
        vault_root = find_vault_root(Path(working_dir) if working_dir else None)
        auto_mcp = get_mcp_config(vault_root)
        if auto_mcp:
            combined_mcp_config = (auto_mcp,)

    if json_out and not agent:
        click.echo(json.dumps({"status": "error", "message": "Agent abbreviation required for JSON mode"}))
        sys.exit(1)

    if json_out:
        # Non-interactive JSON execution
        _trigger_agent_json(
            agent, input_file, config_file, working_dir,
            combined_mcp_config, effective_claude_settings, ctx,
        )
    else:
        # Delegate to existing interactive trigger logic
        from .trigger_agent import trigger_orchestrator_agent
        trigger_orchestrator_agent(
            abbreviation=agent,
            config_file=config_file,
            working_dir=working_dir,
            mcp_config=combined_mcp_config,
            claude_settings=effective_claude_settings,
            input_file=input_file,
            vault_path=_get_vault_root(ctx),
        )


def _trigger_agent_json(agent, input_file, config_file, working_dir, mcp_config, claude_settings, ctx):
    """Trigger an agent and return JSON result."""
    import time as _time
    from ..config import Config
    from ..orchestrator.core import Orchestrator

    vault_root = _get_vault_root(ctx)
    config = Config(
        config_file=str(config_file) if config_file else None,
        vault_path=vault_root,
    )

    try:
        orch = Orchestrator(
            vault_path=vault_root,
            config=config,
            working_dir=Path(working_dir) if working_dir else None,
            mcp_config=mcp_config,
            claude_settings=claude_settings,
        )
    except Exception as e:
        click.echo(json.dumps({"status": "error", "message": f"Failed to init orchestrator: {e}"}))
        sys.exit(1)

    agent_upper = agent.upper()
    if agent_upper not in orch.agent_registry.agents:
        available = sorted(orch.agent_registry.agents.keys())
        click.echo(json.dumps({
            "status": "error",
            "message": f"Agent '{agent}' not found",
            "available_agents": available,
        }))
        sys.exit(1)

    start = _time.time()
    try:
        ctx_result = orch.trigger_agent_once(agent_upper, input_file=input_file)
        elapsed = _time.time() - start

        if ctx_result and ctx_result.success:
            result = {
                "status": "completed",
                "agent": agent_upper,
                "duration_seconds": round(elapsed, 1),
            }
            if ctx_result.task_file:
                result["task_file"] = str(ctx_result.task_file.name)
            click.echo(json.dumps(result))
        else:
            error_msg = ctx_result.error_message if ctx_result else "Unknown error"
            click.echo(json.dumps({
                "status": "failed",
                "agent": agent_upper,
                "duration_seconds": round(elapsed, 1),
                "error": error_msg,
            }))
            sys.exit(1)
    except Exception as e:
        elapsed = _time.time() - start
        click.echo(json.dumps({
            "status": "error",
            "agent": agent_upper,
            "duration_seconds": round(elapsed, 1),
            "error": str(e),
        }))
        sys.exit(1)
