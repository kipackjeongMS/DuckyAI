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


def _show_all_vault_status(json_out: bool = False):
    """Show orchestrator status for all registered vaults."""
    from ..vault_registry import list_vaults
    from ..config import Config
    from ..orchestrator.core import Orchestrator

    vaults = list_vaults()
    if not vaults:
        if json_out:
            click.echo(json.dumps({"vaults": []}))
        else:
            click.echo("No vaults registered. Use 'duckyai vault new <path>' or 'duckyai init'.")
        return

    if json_out:
        results = []
        for v in vaults:
            vault_path = Path(v["path"])
            exists = vault_path.exists()
            pid, alive = _read_pid(vault_path) if exists else (None, False)
            entry = {
                "id": v["id"],
                "name": v["name"],
                "path": v["path"],
                "running": alive,
                "pid": pid,
            }
            if exists and alive:
                try:
                    config = Config(vault_path=vault_path)
                    orch = Orchestrator(vault_path=vault_path, config=config)
                    status = orch.get_status()
                    entry["agents_loaded"] = status.get("agents_loaded", 0)
                except Exception:
                    entry["agents_loaded"] = None
            results.append(entry)
        click.echo(json.dumps({"vaults": results}, indent=2))
    else:
        from rich.table import Table
        from rich.console import Console

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

            agent_count = "-"
            try:
                config = Config(vault_path=vault_path)
                orch = Orchestrator(vault_path=vault_path, config=config)
                status = orch.get_status()
                agent_count = str(status.get("agents_loaded", 0))
            except Exception:
                pass

            table.add_row(v["name"], status_str, pid_str, agent_count, v["path"])

        Console().print(table)


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
def _start_single_vault(vault_path: Path, vault_name: str) -> dict:
    """Start the orchestrator for a single vault. Returns a result dict."""
    from duckyai_cli.config import CONFIG_FILENAME

    pid_file = vault_path / ".orchestrator.pid"

    # Check if already running
    pid, alive = _read_pid(vault_path)
    if alive:
        return {"vault": vault_name, "path": str(vault_path), "status": "already_running", "pid": pid}

    # Clean stale PID file
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)

    # Check duckyai.yml exists
    config_yaml = vault_path / CONFIG_FILENAME
    if not config_yaml.exists():
        return {"vault": vault_name, "path": str(vault_path), "status": "error", "message": "duckyai.yml not found"}

    # Spawn orchestrator as detached background process
    duckyai_exe = shutil.which("duckyai")
    cmd = [duckyai_exe, "-o"] if duckyai_exe else [sys.executable, "-m", "duckyai_cli.main.cli", "-o"]

    try:
        popen_kwargs = dict(
            cwd=str(vault_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        if os.name == "nt":
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_NO_WINDOW = 0x08000000
            popen_kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        else:
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmd, **popen_kwargs)

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

        return {"vault": vault_name, "path": str(vault_path), "status": "started", "pid": new_pid}
    except Exception as e:
        return {"vault": vault_name, "path": str(vault_path), "status": "error", "message": str(e)}


def _echo_start_result(result: dict):
    """Print a human-readable start result."""
    name = result.get("vault", "?")
    status = result.get("status")
    pid = result.get("pid")

    if status == "started":
        click.echo(f"  🚀 {name} — started (PID {pid})")
    elif status == "already_running":
        click.echo(f"  🟢 {name} — already running (PID {pid})")
    elif status == "error":
        click.echo(f"  ⚠️  {name} — error: {result.get('message')}")
    elif status == "missing":
        click.echo(f"  ⚠️  {name} — vault path missing: {result.get('path')}")


@orchestrator_group.command("start")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON for machine consumption")
@click.option("--all", "start_all", is_flag=True, help="Start orchestrators for all registered vaults")
@click.pass_context
def orch_start(ctx, json_out, start_all):
    """Start the orchestrator as a detached background daemon.

    \b
    Without flags, shows an interactive picker to choose which vault(s)
    to start. Use --vault <id> to target a specific vault, or --all
    to start every registered vault.

    \b
    Examples:
        duckyai orchestrator start                  # Interactive picker
        duckyai orchestrator start --vault doitall   # Start specific vault
        duckyai orchestrator start --all             # Start all vaults
    """
    from ..vault_registry import list_vaults

    obj = ctx.obj or {}

    # --- Case 1: --all → start every registered vault ---
    if start_all:
        vaults = list_vaults()
        if not vaults:
            if json_out:
                click.echo(json.dumps({"results": []}))
            else:
                click.echo("No vaults registered.")
            return

        results = []
        for v in vaults:
            vault_path = Path(v["path"])
            if vault_path.exists():
                results.append(_start_single_vault(vault_path, v["name"]))
            else:
                results.append({"vault": v["name"], "status": "missing", "path": v["path"]})

        if json_out:
            click.echo(json.dumps({"results": results}))
        else:
            for r in results:
                _echo_start_result(r)
        return

    # --- Case 2: --vault was explicitly provided → start that vault ---
    if obj.get("vault_explicit") and obj.get("vault_root"):
        vault_root = Path(obj["vault_root"])
        result = _start_single_vault(vault_root, vault_root.name)
        if json_out:
            click.echo(json.dumps(result))
        else:
            _echo_start_result(result)
        return

    # --- Case 3: No --vault, no --all → discover vaults and prompt ---
    vaults = list_vaults()
    if not vaults:
        if json_out:
            click.echo(json.dumps({"status": "error", "message": "No vaults registered"}))
        else:
            click.echo("No vaults registered. Use 'duckyai vault new <path>' or 'duckyai init'.")
        return

    # Partition into stopped/running
    stopped = []
    running = []
    for v in vaults:
        vault_path = Path(v["path"])
        if not vault_path.exists():
            continue
        pid, alive = _read_pid(vault_path)
        entry = {"id": v["id"], "name": v["name"], "path": v["path"], "pid": pid}
        if alive:
            running.append(entry)
        else:
            stopped.append(entry)

    if not stopped:
        if json_out:
            click.echo(json.dumps({"status": "all_running", "running": running}))
        else:
            click.echo("All registered orchestrators are already running.")
            for v in running:
                click.echo(f"  🟢 {v['name']} (PID {v['pid']})")
        return

    if len(stopped) == 1 and not running:
        # Only one vault and it's stopped — start it directly
        v = stopped[0]
        result = _start_single_vault(Path(v["path"]), v["name"])
        if json_out:
            click.echo(json.dumps(result))
        else:
            _echo_start_result(result)
        return

    if json_out:
        click.echo(json.dumps({
            "status": "multiple_vaults",
            "message": "Multiple vaults available. Use --vault <id> or --all.",
            "stopped": stopped,
            "running": running,
        }))
        return

    # Interactive picker — arrow-key navigation
    from .vault import _interactive_select

    if running:
        click.echo(f"\n  Already running:")
        for v in running:
            click.echo(f"    🟢 {v['name']} (PID {v['pid']})")
        click.echo()

    click.echo("  Select vault to start (↑/↓ navigate, Enter select, q quit):\n")
    menu_items = [{"name": v["name"], "path": v["path"]} for v in stopped]
    menu_items.append({"name": "Start all", "path": f"{len(stopped)} vaults"})

    idx = _interactive_select(menu_items)
    if idx is None:
        click.echo("  Cancelled.")
        return

    if idx == len(stopped):
        for v in stopped:
            result = _start_single_vault(Path(v["path"]), v["name"])
            _echo_start_result(result)
    else:
        v = stopped[idx]
        result = _start_single_vault(Path(v["path"]), v["name"])
        _echo_start_result(result)


# =============================================================================
# duckyai orchestrator stop
# =============================================================================
def _stop_single_vault(vault_path: Path, vault_name: str) -> dict:
    """Stop the orchestrator for a single vault. Returns a result dict."""
    pid_file = vault_path / ".orchestrator.pid"
    pid, alive = _read_pid(vault_path)

    if not pid:
        return {"vault": vault_name, "path": str(vault_path), "status": "not_running"}

    if alive:
        try:
            os.kill(pid, signal.SIGTERM)
            pid_file.unlink(missing_ok=True)
            return {"vault": vault_name, "path": str(vault_path), "status": "stopped", "pid": pid}
        except Exception as e:
            pid_file.unlink(missing_ok=True)
            return {"vault": vault_name, "path": str(vault_path), "status": "error", "message": str(e)}
    else:
        pid_file.unlink(missing_ok=True)
        return {"vault": vault_name, "path": str(vault_path), "status": "not_running", "message": "Stale PID file cleaned up"}


@orchestrator_group.command("stop")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON for machine consumption")
@click.option("--all", "stop_all", is_flag=True, help="Stop orchestrators for all registered vaults")
@click.pass_context
def orch_stop(ctx, json_out, stop_all):
    """Stop the running orchestrator daemon.

    \b
    Without flags, shows an interactive picker if multiple orchestrators
    are running. Use --vault <id> to target a specific vault, or --all
    to stop every running orchestrator.

    \b
    Examples:
        duckyai orchestrator stop                  # Interactive picker
        duckyai orchestrator stop --vault doitall   # Stop specific vault
        duckyai orchestrator stop --all             # Stop all vaults
    """
    from ..vault_registry import list_vaults

    obj = ctx.obj or {}

    # --- Case 1: --all → stop every registered vault (highest priority) ---
    if stop_all:
        vaults = list_vaults()
        if not vaults:
            if json_out:
                click.echo(json.dumps({"results": []}))
            else:
                click.echo("No vaults registered.")
            return

        results = []
        for v in vaults:
            vault_path = Path(v["path"])
            if vault_path.exists():
                results.append(_stop_single_vault(vault_path, v["name"]))
            else:
                results.append({"vault": v["name"], "status": "missing", "path": v["path"]})

        if json_out:
            click.echo(json.dumps({"results": results}))
        else:
            for r in results:
                _echo_stop_result(r)
        return

    # --- Case 2: --vault was explicitly provided → stop that specific vault ---
    if obj.get("vault_explicit") and obj.get("vault_root"):
        vault_root = Path(obj["vault_root"])
        result = _stop_single_vault(vault_root, vault_root.name)
        if json_out:
            click.echo(json.dumps(result))
        else:
            _echo_stop_result(result)
        return

    # --- Case 3: No --vault, no --all → discover running orchestrators and prompt ---
    vaults = list_vaults()
    running = []
    for v in vaults:
        vault_path = Path(v["path"])
        if vault_path.exists():
            pid, alive = _read_pid(vault_path)
            if alive:
                running.append({"id": v["id"], "name": v["name"], "path": v["path"], "pid": pid})

    if not running:
        if json_out:
            click.echo(json.dumps({"status": "none_running"}))
        else:
            click.echo("No orchestrators are currently running.")
        return

    if len(running) == 1:
        # Only one running — stop it directly
        v = running[0]
        result = _stop_single_vault(Path(v["path"]), v["name"])
        if json_out:
            click.echo(json.dumps(result))
        else:
            _echo_stop_result(result)
        return

    if json_out:
        # Non-interactive mode without --all or --vault: report what's running
        click.echo(json.dumps({
            "status": "multiple_running",
            "message": "Multiple orchestrators running. Use --vault <id> or --all.",
            "running": running,
        }))
        return

    # Interactive picker — arrow-key navigation
    from .vault import _interactive_select

    click.echo("  Select orchestrator to stop (↑/↓ navigate, Enter select, q quit):\n")
    menu_items = [{"name": f"{v['name']} (PID {v['pid']})", "path": v["path"]} for v in running]
    menu_items.append({"name": "Stop all", "path": f"{len(running)} orchestrators"})

    idx = _interactive_select(menu_items)
    if idx is None:
        click.echo("  Cancelled.")
        return

    if idx == len(running):
        for v in running:
            result = _stop_single_vault(Path(v["path"]), v["name"])
            _echo_stop_result(result)
    else:
        v = running[idx]
        result = _stop_single_vault(Path(v["path"]), v["name"])
        _echo_stop_result(result)


def _echo_stop_result(result: dict):
    """Print a human-readable stop result."""
    name = result.get("vault", "?")
    status = result.get("status")
    pid = result.get("pid")

    if status == "stopped":
        click.echo(f"  ✅ {name} — stopped (PID {pid})")
    elif status == "not_running":
        msg = result.get("message", "")
        suffix = f" ({msg})" if msg else ""
        click.echo(f"  ⚪ {name} — not running{suffix}")
    elif status == "error":
        click.echo(f"  ⚠️  {name} — error: {result.get('message')}")
    elif status == "missing":
        click.echo(f"  ⚠️  {name} — vault path missing: {result.get('path')}")


# =============================================================================
# duckyai orchestrator status
# =============================================================================
@orchestrator_group.command("status")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON for machine consumption")
@click.pass_context
def orch_status(ctx, json_out):
    """Show orchestrator status, loaded agents, and schedules.

    Without --vault, shows status for all registered vaults.
    With --vault, shows detailed status for that specific vault.
    """
    from ..config import Config
    from ..orchestrator.core import Orchestrator
    from rich.panel import Panel

    obj = ctx.obj or {}

    # If --vault was explicitly provided, show single-vault detail
    # Otherwise show global multi-vault status
    if not obj.get("vault_root"):
        _show_all_vault_status(json_out)
        return

    vault_root = Path(obj["vault_root"])
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
@click.option("--lookback", "lookback_hours", type=int, default=None, help="Lookback hours for Teams agents (TCS/TMS) on first run or manual trigger.")
@click.pass_context
def orch_trigger(ctx, agent, input_file, json_out, mcp_config, claude_settings, lookback_hours):
    """Trigger an orchestrator agent by abbreviation.

    \b
    If AGENT is provided, triggers it directly.
    Otherwise, shows an interactive selector (human mode only).
    Without --vault, prompts for vault selection when multiple exist.

    \b
    Examples:
        duckyai orchestrator trigger EIC
        duckyai orchestrator trigger EIC --file 00-Inbox/article.md
        duckyai --vault doitall orchestrator trigger TCS
    """
    from ..vault_registry import list_vaults

    obj = ctx.obj or {}
    working_dir = obj.get("working_dir")
    config_file = obj.get("config_file")
    parent_mcp_config = obj.get("mcp_config", ())
    combined_mcp_config = parent_mcp_config + mcp_config if mcp_config else parent_mcp_config
    effective_claude_settings = claude_settings or obj.get("claude_settings")

    # --- Resolve vault root (with interactive picker if needed) ---
    if obj.get("vault_explicit") and obj.get("vault_root"):
        vault_root = Path(obj["vault_root"])
    else:
        vaults = list_vaults()
        valid_vaults = [v for v in vaults if Path(v["path"]).exists()]

        if not valid_vaults:
            click.echo("No vaults registered. Use 'duckyai vault new <path>' or 'duckyai init'.")
            return
        elif len(valid_vaults) == 1:
            vault_root = Path(valid_vaults[0]["path"])
        elif json_out:
            click.echo(json.dumps({
                "status": "error",
                "message": "Multiple vaults available. Use --vault <id> to specify.",
                "vaults": [{"id": v["id"], "name": v["name"]} for v in valid_vaults],
            }))
            sys.exit(1)
        else:
            from .vault import _interactive_select
            click.echo("\n  Select vault (↑/↓ navigate, Enter select, q quit):\n")
            menu_items = [{"name": v["name"], "path": v["path"]} for v in valid_vaults]
            idx = _interactive_select(menu_items)
            if idx is None:
                click.echo("  Cancelled.")
                return
            vault_root = Path(valid_vaults[idx]["path"])

    # Auto-discover MCP config if none provided
    if not combined_mcp_config:
        from .cli import get_mcp_config
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
            vault_root=vault_root,
            lookback_hours=lookback_hours,
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
            vault_path=vault_root,
            lookback_hours=lookback_hours,
        )


def _trigger_agent_json(agent, input_file, config_file, working_dir, mcp_config, claude_settings, ctx, vault_root=None, lookback_hours=None):
    """Trigger an agent and return JSON result."""
    import time as _time
    from ..config import Config
    from ..orchestrator.core import Orchestrator

    if vault_root is None:
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
        agent_params_override = {'lookback_hours': lookback_hours} if lookback_hours is not None else None
        ctx_result = orch.trigger_agent_once(agent_upper, input_file=input_file, agent_params_override=agent_params_override)
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
