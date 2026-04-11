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
from typing import Optional

import click

from ..logger import Logger
from .install_health import get_duckyai_launch_cmd

logger = Logger(console_output=True)


def _get_psutil():
    """Import psutil lazily so tests can stub it and startup can degrade gracefully."""
    try:
        import psutil
    except ImportError:
        return None
    return psutil


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


def _read_discovery(vault_root: Path) -> Optional[dict]:
    """Read the API discovery file when present."""
    discovery_file = vault_root / ".duckyai" / "api.json"
    if not discovery_file.exists():
        return None
    try:
        data = json.loads(discovery_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _probe_discovery_health(discovery: Optional[dict]) -> Optional[int]:
    """Return the PID from a healthy discovery endpoint when available."""
    if not discovery:
        return None

    url = discovery.get("url")
    if not url:
        host = discovery.get("host")
        port = discovery.get("port")
        if host and port:
            url = f"http://{host}:{port}"
    if not url:
        return None

    try:
        import requests

        response = requests.get(f"{str(url).rstrip('/')}/api/health", timeout=1.5)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None

    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None

    pid = payload.get("pid")
    try:
        return int(pid) if pid is not None else None
    except (TypeError, ValueError):
        return None


def _same_path(left: Optional[str], right: Path) -> bool:
    """Return True when two paths resolve to the same location."""
    if not left:
        return False
    try:
        return Path(left).resolve() == right.resolve()
    except OSError:
        return False


def _looks_like_orchestrator_cmd(cmdline: list[str]) -> bool:
    """Identify a DuckyAI orchestrator daemon command line."""
    if not cmdline:
        return False

    normalized = [str(part).lower() for part in cmdline if part]
    joined = " ".join(normalized)
    if "duckyai" not in joined and "duckyai_cli" not in joined:
        return False
    return "-o" in normalized


def _find_matching_orchestrator_processes(vault_root: Path) -> tuple[list[dict], Optional[int]]:
    """Find running orchestrator processes that belong to the given vault."""
    discovery = _read_discovery(vault_root)
    healthy_pid = _probe_discovery_health(discovery)
    pid_from_file, _ = _read_pid(vault_root)

    known_pids = set()
    for candidate in (pid_from_file, discovery.get("pid") if discovery else None, healthy_pid):
        try:
            if candidate is not None:
                known_pids.add(int(candidate))
        except (TypeError, ValueError):
            continue

    psutil = _get_psutil()
    if psutil is None:
        return [], healthy_pid

    matches: dict[int, dict] = {}
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            if proc.pid == os.getpid():
                continue

            cmdline = proc.info.get("cmdline") or []
            cwd = proc.cwd()
            same_vault = _same_path(cwd, vault_root)
            reasons = []

            if healthy_pid and proc.pid == healthy_pid:
                reasons.append("api_health")
            if same_vault and _looks_like_orchestrator_cmd(cmdline):
                reasons.append("cwd_cmdline")
            if proc.pid in known_pids and same_vault:
                reasons.append("known_pid")

            if reasons:
                matches[proc.pid] = {
                    "process": proc,
                    "pid": proc.pid,
                    "cmdline": cmdline,
                    "cwd": cwd,
                    "healthy": proc.pid == healthy_pid,
                    "reasons": reasons,
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue

    return list(matches.values()), healthy_pid


def _cleanup_orchestrator_processes(
    vault_root: Path,
    *,
    fresh_start: bool,
    timeout_seconds: float = 5.0,
) -> dict:
    """Clean up stale or duplicate orchestrator processes for a vault.

    When `fresh_start` is true, all matching processes are terminated so a new
    daemon can start cleanly. Otherwise, one healthy matching process is kept
    and only stale or duplicate processes are removed.
    """
    matches, healthy_pid = _find_matching_orchestrator_processes(vault_root)
    kept_pid = None if fresh_start else healthy_pid
    targets = [entry for entry in matches if entry["pid"] != kept_pid]

    terminated_pids: list[int] = []
    killed_pids: list[int] = []
    errors: list[str] = []

    psutil = _get_psutil()
    if targets and psutil is not None:
        processes = []
        for entry in targets:
            proc = entry["process"]
            try:
                proc.terminate()
                processes.append(proc)
            except (psutil.NoSuchProcess, ProcessLookupError):
                terminated_pids.append(entry["pid"])
            except (psutil.AccessDenied, OSError) as exc:
                errors.append(f"PID {entry['pid']}: terminate failed ({exc})")

        if processes:
            gone, alive = psutil.wait_procs(processes, timeout=timeout_seconds)
            terminated_pids.extend(proc.pid for proc in gone)

            for proc in alive:
                try:
                    proc.kill()
                except (psutil.NoSuchProcess, ProcessLookupError):
                    terminated_pids.append(proc.pid)
                except (psutil.AccessDenied, OSError) as exc:
                    errors.append(f"PID {proc.pid}: kill failed ({exc})")

            if alive:
                gone_after_kill, still_alive = psutil.wait_procs(alive, timeout=2.0)
                killed_pids.extend(proc.pid for proc in gone_after_kill)
                for proc in still_alive:
                    errors.append(f"PID {proc.pid}: still alive after forced kill")
    elif targets:
        errors.append("psutil unavailable; could not inspect or terminate matching orchestrator processes")

    cleaned_pid_file = False
    cleaned_discovery = False
    pid_file = vault_root / ".orchestrator.pid"
    discovery_file = vault_root / ".duckyai" / "api.json"

    if fresh_start or kept_pid is None:
        if pid_file.exists():
            pid_file.unlink(missing_ok=True)
            cleaned_pid_file = True
        if discovery_file.exists():
            discovery_file.unlink(missing_ok=True)
            cleaned_discovery = True

    return {
        "matched_pids": [entry["pid"] for entry in matches],
        "terminated_pids": sorted(set(terminated_pids)),
        "killed_pids": sorted(set(killed_pids)),
        "healthy_pid": kept_pid,
        "errors": errors,
        "cleaned_pid_file": cleaned_pid_file,
        "cleaned_discovery": cleaned_discovery,
    }


def _get_vault_root(ctx) -> Path:
    """Resolve vault root from click context."""
    obj = ctx.obj or {}
    if obj.get("vault_root"):
        return Path(obj["vault_root"])
    from .vault import resolve_vault
    working_dir = obj.get("working_dir")
    return resolve_vault(working_dir)


def _show_all_vault_status(json_out: bool = False):
    """Show orchestrator status for the configured home vault."""
    from ..vault_registry import get_home_vault
    from ..config import Config
    from ..orchestrator.core import Orchestrator

    home_vault = get_home_vault()
    if not home_vault:
        if json_out:
            click.echo(json.dumps({"home_vault": None}))
        else:
            click.echo("No home vault configured. Use 'duckyai init' or 'duckyai setup'.")
        return

    if json_out:
        vault_path = Path(home_vault["path"])
        exists = vault_path.exists()
        pid, alive = _read_pid(vault_path) if exists else (None, False)
        result = {
            "id": home_vault["id"],
            "name": home_vault["name"],
            "path": home_vault["path"],
            "running": alive,
            "pid": pid,
        }
        if exists and alive:
            try:
                config = Config(vault_path=vault_path)
                orch = Orchestrator(vault_path=vault_path, config=config)
                status = orch.get_status()
                result["agents_loaded"] = status.get("agents_loaded", 0)
            except Exception:
                result["agents_loaded"] = None
        click.echo(json.dumps({"home_vault": result}, indent=2))
    else:
        from rich.table import Table
        from rich.console import Console

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
                config = Config(vault_path=vault_path)
                orch = Orchestrator(vault_path=vault_path, config=config)
                status = orch.get_status()
                agent_count = str(status.get("agents_loaded", 0))
            except Exception:
                pass

            table.add_row(home_vault["name"], status_str, pid_str, agent_count, home_vault["path"])

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

    # Check duckyai.yml exists
    config_yaml = vault_path / CONFIG_FILENAME
    if not config_yaml.exists():
        return {"vault": vault_name, "path": str(vault_path), "status": "error", "message": "duckyai.yml not found"}

    cleanup = _cleanup_orchestrator_processes(vault_path, fresh_start=True)

    # Spawn orchestrator as detached background process
    cmd = get_duckyai_launch_cmd("-o")

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

        status = "restarted" if cleanup["terminated_pids"] or cleanup["killed_pids"] else "started"
        return {
            "vault": vault_name,
            "path": str(vault_path),
            "status": status,
            "pid": new_pid,
            "replaced_pids": cleanup["terminated_pids"] + cleanup["killed_pids"],
            "cleanup_errors": cleanup["errors"],
        }
    except Exception as e:
        return {"vault": vault_name, "path": str(vault_path), "status": "error", "message": str(e)}


def _echo_start_result(result: dict):
    """Print a human-readable start result."""
    name = result.get("vault", "?")
    status = result.get("status")
    pid = result.get("pid")

    if status == "started":
        click.echo(f"  🚀 {name} — started (PID {pid})")
    elif status == "restarted":
        replaced = result.get("replaced_pids") or []
        replaced_str = f" after stopping PID(s) {', '.join(str(p) for p in replaced)}" if replaced else ""
        click.echo(f"  ♻️  {name} — restarted (PID {pid}){replaced_str}")
    elif status == "error":
        click.echo(f"  ⚠️  {name} — error: {result.get('message')}")
    elif status == "missing":
        click.echo(f"  ⚠️  {name} — vault path missing: {result.get('path')}")


@orchestrator_group.command("start")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON for machine consumption")
@click.pass_context
def orch_start(ctx, json_out):
    """Start the orchestrator as a detached background daemon.

    \b
    Starts the orchestrator for the resolved home vault.

    \b
    Examples:
        duckyai orchestrator start
    """
    vault_root = _get_vault_root(ctx)
    result = _start_single_vault(vault_root, vault_root.name)
    if json_out:
        click.echo(json.dumps(result))
    else:
        _echo_start_result(result)


# =============================================================================
# duckyai orchestrator stop
# =============================================================================
def _stop_single_vault(vault_path: Path, vault_name: str) -> dict:
    """Stop the orchestrator for a single vault. Returns a result dict.

    Uses _cleanup_orchestrator_processes with fresh_start=True to robustly
    find and terminate all matching orchestrator processes (daemon + children),
    clean up the PID file, and clean up the discovery file.
    """
    pid, alive = _read_pid(vault_path)

    if not pid and not alive:
        # No PID file — still try cleanup in case orphan processes exist
        cleanup = _cleanup_orchestrator_processes(vault_path, fresh_start=True)
        if cleanup["terminated_pids"] or cleanup["killed_pids"]:
            killed = cleanup["terminated_pids"] + cleanup["killed_pids"]
            return {
                "vault": vault_name,
                "path": str(vault_path),
                "status": "stopped",
                "pids_killed": killed,
            }
        return {"vault": vault_name, "path": str(vault_path), "status": "not_running"}

    cleanup = _cleanup_orchestrator_processes(vault_path, fresh_start=True)
    killed = cleanup["terminated_pids"] + cleanup["killed_pids"]

    if cleanup["errors"]:
        return {
            "vault": vault_name,
            "path": str(vault_path),
            "status": "error",
            "message": "; ".join(cleanup["errors"]),
            "pids_killed": killed,
        }

    if killed or not alive:
        return {
            "vault": vault_name,
            "path": str(vault_path),
            "status": "stopped",
            "pid": pid,
            "pids_killed": killed,
        }

    return {"vault": vault_name, "path": str(vault_path), "status": "not_running"}


@orchestrator_group.command("stop")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON for machine consumption")
@click.pass_context
def orch_stop(ctx, json_out):
    """Stop the running orchestrator daemon.

    \b
    Stops the orchestrator for the resolved home vault.

    \b
    Examples:
        duckyai orchestrator stop
    """
    vault_root = _get_vault_root(ctx)
    result = _stop_single_vault(vault_root, vault_root.name)
    if json_out:
        click.echo(json.dumps(result))
    else:
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

    Shows status for the resolved home vault.
    """
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
@click.option("--lookback", "lookback_hours", type=int, default=None, help="Lookback N hours (ignores watermark). For TCS/TMS.")
@click.option("--since-last-sync", "since_last_sync", is_flag=True, default=False, help="Use watermark (since last sync). Default for TCS/TMS when watermark exists.")
@click.pass_context
def orch_trigger(ctx, agent, input_file, json_out, mcp_config, claude_settings, lookback_hours, since_last_sync):
    """Trigger an orchestrator agent by abbreviation.

    \b
    If AGENT is provided, triggers it directly.
    Otherwise, shows an interactive selector (human mode only).

    \b
    Time range for TCS/TMS:
      --since-last-sync     Fetch only messages since last sync watermark (default)
      --lookback 24         Fetch messages from the last 24 hours (ignores watermark)

    \b
    Examples:
        duckyai orchestrator trigger TCS
        duckyai orchestrator trigger TCS --since-last-sync
        duckyai orchestrator trigger TCS --lookback 8
    """
    obj = ctx.obj or {}
    working_dir = obj.get("working_dir")
    config_file = obj.get("config_file")
    parent_mcp_config = obj.get("mcp_config", ())
    combined_mcp_config = parent_mcp_config + mcp_config if mcp_config else parent_mcp_config
    effective_claude_settings = claude_settings or obj.get("claude_settings")

    vault_root = _get_vault_root(ctx)

    # Auto-discover MCP config if none provided
    if not combined_mcp_config:
        from .cli import get_mcp_config
        auto_mcp = get_mcp_config(vault_root)
        if auto_mcp:
            combined_mcp_config = (auto_mcp,)

    if json_out and not agent:
        if json_out:
            click.echo(json.dumps({"status": "error", "message": "Agent abbreviation required for non-interactive mode"}))
        sys.exit(1)

    if json_out:
        _trigger_agent_json(
            agent, input_file, config_file, working_dir,
            combined_mcp_config, effective_claude_settings, ctx,
            vault_root=vault_root,
            lookback_hours=lookback_hours,
            since_last_sync=since_last_sync,
            json_out=json_out,
        )
    else:
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


def _trigger_agent_json(agent, input_file, config_file, working_dir, mcp_config, claude_settings, ctx, vault_root=None, lookback_hours=None, since_last_sync=False, json_out=True):
    """Trigger an agent non-interactively. Outputs JSON when json_out=True, plain text otherwise."""
    import time as _time
    from ..config import Config
    from ..logger import Logger
    from ..orchestrator.core import Orchestrator

    def _output(data: dict):
        if json_out:
            click.echo(json.dumps(data))
        else:
            status = data.get("status", "unknown")
            msg = data.get("message") or data.get("error") or ""
            agent_name = data.get("agent", agent)
            duration = data.get("duration_seconds")
            if status == "completed":
                line = f"  ✓ {agent_name} completed"
                if duration:
                    line += f" ({duration}s)"
                click.echo(line)
            elif status in ("failed", "error"):
                click.echo(f"  ⚠️  {agent_name}: {msg}", err=True)
            else:
                click.echo(f"  {agent_name}: {msg}")

    if vault_root is None:
        vault_root = _get_vault_root(ctx)
    Logger(console_output=True).reconfigure(vault_root)
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
        _output({"status": "error", "message": f"Failed to init orchestrator: {e}"})
        sys.exit(1)

    agent_upper = agent.upper()
    if agent_upper not in orch.agent_registry.agents:
        available = sorted(orch.agent_registry.agents.keys())
        _output({
            "status": "error",
            "message": f"Agent '{agent}' not found",
            "available_agents": available,
        })
        sys.exit(1)

    start = _time.time()
    try:
        agent_params_override = None
        if lookback_hours is not None:
            agent_params_override = {'lookback_hours': lookback_hours, 'ignore_watermark': True}
        elif since_last_sync:
            # Explicit watermark mode — don't set lookback_hours, let watermark take over
            agent_params_override = {'ignore_watermark': False}
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
            _output(result)
        else:
            error_msg = ctx_result.error_message if ctx_result else "Unknown error"
            _output({
                "status": "failed",
                "agent": agent_upper,
                "duration_seconds": round(elapsed, 1),
                "error": error_msg,
            })
            sys.exit(1)
    except Exception as e:
        elapsed = _time.time() - start
        _output({
            "status": "error",
            "agent": agent_upper,
            "duration_seconds": round(elapsed, 1),
            "error": str(e),
        })
        sys.exit(1)
