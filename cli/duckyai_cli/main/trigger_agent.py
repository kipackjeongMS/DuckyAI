"""Handler for --trigger-agent command."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional
from rich.console import Console

from ..logger import Logger
from ..config import Config, get_global_runtime_dir
from ..orchestrator.core import Orchestrator

logger = Logger(console_output=True)


def _prompt_yn(message: str, default: bool = True) -> bool:
    """Prompt for y/n with input validation. Loops until valid input.
    
    Returns True for yes, False for no. Ctrl+C/EOF returns default.
    """
    hint = "Y/n" if default else "y/N"
    while True:
        try:
            response = input(f"{message} ({hint}): ").strip().lower()
            if response in ("y", "yes"):
                return True
            elif response in ("n", "no"):
                return False
            elif response == "":
                return default
            else:
                print("  Enter y or n")
        except (EOFError, KeyboardInterrupt):
            return default


def _read_watermark(vault_root: Path, agent_abbr: str) -> Optional[str]:
    """Read the lastSynced timestamp from the agent's watermark file. Returns ISO string or None."""
    config = Config(vault_path=vault_root)
    vault_id = config.get("id", "default")
    filename = "tcs-last-sync.json" if agent_abbr == "TCS" else "tms-last-sync.json"
    state_file = get_global_runtime_dir(vault_id) / "state" / filename
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return data.get("lastSynced")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def _format_watermark_age(last_synced_iso: str) -> str:
    """Format a watermark timestamp as a human-readable age string."""
    try:
        ts = datetime.fromisoformat(last_synced_iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - ts
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m ago"
        elif hours < 24:
            return f"{hours:.1f}h ago"
        else:
            days = hours / 24
            return f"{days:.1f}d ago"
    except (ValueError, TypeError):
        return "unknown"


def _prompt_lookback_or_watermark(agent_abbr: str, default_hours: int, last_synced: Optional[str], console: Console) -> Optional[Dict]:
    """Prompt user to choose between syncing from watermark or custom lookback hours.
    
    Returns agent_params_override dict or None to use watermark as-is.
    """
    if last_synced:
        age = _format_watermark_age(last_synced)
        console.print(f"\n[bold blue]{agent_abbr} Sync[/bold blue]")
        console.print(f"  Last synced: [cyan]{last_synced}[/cyan] ({age})")
        console.print(f"  [dim]1) Since last sync (default)[/dim]")
        console.print(f"  [dim]2) Custom lookback hours[/dim]")
        try:
            while True:
                choice = console.input(f"[bold]Choice [1]: [/bold]").strip()
                if choice in ("1", ""):
                    console.print(f"[dim]Syncing since last watermark[/dim]\n")
                    return None
                elif choice == "2":
                    while True:
                        try:
                            user_input = console.input(f"[bold]Hours [{default_hours}]: [/bold]").strip()
                            hours = int(user_input) if user_input else default_hours
                            if hours < 1:
                                console.print(f"  [red]Must be at least 1 hour[/red]")
                                continue
                            break
                        except ValueError:
                            console.print(f"  [red]Enter a number[/red]")
                    console.print(f"[dim]Using lookback: {hours} hours[/dim]\n")
                    return {'lookback_hours': hours, 'ignore_watermark': True}
                else:
                    console.print(f"  [red]Enter 1 or 2[/red]")
        except (EOFError, KeyboardInterrupt):
            return None
    else:
        # No watermark — first run, prompt for lookback hours
        console.print(f"\n[bold blue]{agent_abbr} first sync[/bold blue] — no previous watermark found")
        console.print(f"[dim]How far back should the agent fetch data? (default: {default_hours}h)[/dim]")
        try:
            while True:
                try:
                    user_input = console.input(f"[bold]Hours [{default_hours}]: [/bold]").strip()
                    hours = int(user_input) if user_input else default_hours
                    if hours < 1:
                        console.print(f"  [red]Must be at least 1 hour[/red]")
                        continue
                    break
                except ValueError:
                    console.print(f"  [red]Enter a number[/red]")
        except (EOFError, KeyboardInterrupt):
            hours = default_hours
        console.print(f"[dim]Using lookback: {hours} hours[/dim]\n")
        return {'lookback_hours': hours}


def _prompt_teams_sync_lookback(vault_root: Path, console: Console, default_hours: int = 24) -> Optional[Dict]:
    """Single lookback prompt for all Teams agents (TCS + TMS).

    Checks watermarks for both agents and presents one unified prompt.
    Returns agent_params_override dict or None to use watermarks as-is.
    """
    tcs_wm = _read_watermark(vault_root, "TCS")
    tms_wm = _read_watermark(vault_root, "TMS")
    has_watermark = tcs_wm or tms_wm

    if has_watermark:
        console.print(f"\n[bold blue]Teams Sync[/bold blue]")
        if tcs_wm:
            console.print(f"  TCS last synced: [cyan]{tcs_wm}[/cyan] ({_format_watermark_age(tcs_wm)})")
        else:
            console.print(f"  TCS: [yellow]no previous sync[/yellow]")
        if tms_wm:
            console.print(f"  TMS last synced: [cyan]{tms_wm}[/cyan] ({_format_watermark_age(tms_wm)})")
        else:
            console.print(f"  TMS: [yellow]no previous sync[/yellow]")
        console.print(f"  [dim]1) Since last sync (default)[/dim]")
        console.print(f"  [dim]2) Custom lookback hours[/dim]")
        try:
            while True:
                choice = console.input(f"[bold]Choice [1]: [/bold]").strip()
                if choice in ("1", ""):
                    console.print(f"[dim]Syncing since last watermark[/dim]\n")
                    return None
                elif choice == "2":
                    while True:
                        try:
                            user_input = console.input(f"[bold]Hours [{default_hours}]: [/bold]").strip()
                            hours = int(user_input) if user_input else default_hours
                            if hours < 1:
                                console.print(f"  [red]Must be at least 1 hour[/red]")
                                continue
                            break
                        except ValueError:
                            console.print(f"  [red]Enter a number[/red]")
                    console.print(f"[dim]Using lookback: {hours} hours[/dim]\n")
                    return {'lookback_hours': hours, 'ignore_watermark': True}
                else:
                    console.print(f"  [red]Enter 1 or 2[/red]")
        except (EOFError, KeyboardInterrupt):
            return None
    else:
        console.print(f"\n[bold blue]Teams first sync[/bold blue] — no previous data")
        console.print(f"[dim]How far back should we fetch? (default: {default_hours}h)[/dim]")
        try:
            while True:
                try:
                    user_input = console.input(f"[bold]Hours [{default_hours}]: [/bold]").strip()
                    hours = int(user_input) if user_input else default_hours
                    if hours < 1:
                        console.print(f"  [red]Must be at least 1 hour[/red]")
                        continue
                    break
                except ValueError:
                    console.print(f"  [red]Enter a number[/red]")
        except (EOFError, KeyboardInterrupt):
            hours = default_hours
            hours = default_hours
        console.print(f"[dim]Using lookback: {hours} hours[/dim]\n")
        return {'lookback_hours': hours}

def trigger_orchestrator_agent(abbreviation=None, config_file=None, working_dir=None, mcp_config=None, claude_settings=None, input_file=None, vault_path=None, lookback_hours=None):
    """Trigger an orchestrator agent or poller interactively.

    Args:
        abbreviation: Optional agent abbreviation or poller name to skip selection UX
        config_file: Optional path to orchestrator config file
        working_dir: Optional working directory for agent subprocess execution (defaults to vault_path)
        mcp_config: Optional tuple of MCP config JSON files or strings
        claude_settings: Optional path or JSON string for Claude --settings flag
        input_file: Optional input file path to pass to the agent
        vault_path: Optional vault root path (defaults to CWD)
        lookback_hours: Optional lookback hours override for Teams agents (TCS/TMS)
    """
    try:
        vault_root = Path(vault_path) if vault_path else Path.cwd()
        config = Config(config_file=config_file, vault_path=vault_root)

        # Reconfigure logger to use the correct vault's log directory
        logger.reconfigure(vault_root)

        # Create orchestrator (but don't start daemon)
        orch = Orchestrator(
            vault_path=vault_root,
            config=config,
            working_dir=Path(working_dir) if working_dir else None,
            mcp_config=mcp_config,
            claude_settings=claude_settings
        )

        agents_list = [agent for agent in orch.agent_registry.agents.values()]
        pollers_list = list(orch.poller_manager.pollers.items())
        
        if not agents_list and not pollers_list:
            logger.error("No agents or pollers found", console=True)
            return

        # If abbreviation/name provided, skip selection
        if abbreviation:
            abbreviation_upper = abbreviation.upper()
            selected_agent = orch.agent_registry.agents.get(abbreviation_upper)
            selected_poller_name = None
            selected_poller = None
            
            if selected_agent:
                # Found as agent
                pass
            else:
                # Try as poller name (case-insensitive)
                for poller_name, poller in pollers_list:
                    if poller_name.lower() == abbreviation.lower():
                        selected_poller_name = poller_name
                        selected_poller = poller
                        break
                
                if not selected_poller:
                    logger.error(f"Agent or poller '{abbreviation}' not found", console=True)
                    available_items = []
                    if agents_list:
                        available_items.extend([f"Agent: {abbr}" for abbr in sorted(orch.agent_registry.agents.keys())])
                    if pollers_list:
                        available_items.extend([f"Poller: {name}" for name in sorted([p[0] for p in pollers_list])])
                    logger.info(f"[dim]Available: {', '.join(available_items)}[/dim]")
                    return
        else:
            # Build unified list for selection
            items = []
            item_types = []  # 'agent' or 'poller'
            
            # Add agents
            agents_list.sort(key=lambda a: a.abbreviation)
            for agent in agents_list:
                items.append(agent)
                item_types.append('agent')
            
            # Add pollers
            pollers_list.sort(key=lambda p: p[0])  # Sort by name
            for poller_name, poller in pollers_list:
                items.append((poller_name, poller))
                item_types.append('poller')
            
            if not items:
                logger.error("No agents or pollers available", console=True)
                return

            # Interactive arrow-key selector
            from .vault import _interactive_select

            menu_items = []
            for agent in agents_list:
                cron_info = f" (cron: {agent.cron})" if agent.cron else ""
                menu_items.append({
                    "name": f"{agent.name} ({agent.abbreviation})",
                    "path": f"{agent.category}{cron_info}",
                })
            for poller_name, poller in pollers_list:
                target_dir_rel = poller.poller_config.get('target_dir', str(poller.target_dir))
                menu_items.append({
                    "name": poller_name,
                    "path": f"Poller → {target_dir_rel}",
                })

            logger.info("\n[bold blue]Select agent or poller to trigger[/bold blue] (↑/↓ navigate, Enter select, q quit)\n")
            idx = _interactive_select(menu_items)
            if idx is None:
                logger.info("Trigger cancelled.")
                return

            # Determine if selected item is agent or poller
            selected_item = items[idx]
            item_type = item_types[idx]
            
            if item_type == 'agent':
                selected_agent = selected_item
                selected_poller = None
                selected_poller_name = None
            else:
                selected_poller_name, selected_poller = selected_item
                selected_agent = None
        
        # Execute selected item
        start_time = time.time()

        # For Teams agents (TCS/TMS), prompt for lookback vs watermark
        agent_params_override = None
        if selected_agent and selected_agent.abbreviation in ('TCS', 'TMS'):
            if lookback_hours is not None:
                # Explicit --lookback flag: skip interactive prompt
                agent_params_override = {'lookback_hours': lookback_hours, 'ignore_watermark': True}
            else:
                default_hours = selected_agent.agent_params.get('lookback_hours', 1 if selected_agent.abbreviation == 'TCS' else 24)
                last_synced = _read_watermark(vault_root, selected_agent.abbreviation)
                console = Console()
                agent_params_override = _prompt_lookback_or_watermark(
                    selected_agent.abbreviation, default_hours, last_synced, console
                )

        try:
            if selected_agent:
                # Trigger agent
                logger.info(f"Triggering agent: {selected_agent.abbreviation}")
                ctx = orch.trigger_agent_once(selected_agent.abbreviation, input_file=input_file, agent_params_override=agent_params_override)

                end_time = time.time()
                execution_time = end_time - start_time

                if ctx and ctx.success:
                    logger.info(
                        f"✓ Agent completed successfully ({execution_time:.1f}s)"
                    )
                    logger.info(f"\n[green]✓ Agent completed successfully[/green]")
                    logger.info(
                        f"[dim]Execution time: {execution_time:.2f}s[/dim]"
                    )
                    if ctx.task_file:
                        logger.info(f"[dim]Task file: {ctx.task_file.name}[/dim]")
                else:
                    error_msg = ctx.error_message if ctx else "Unknown error"
                    logger.error(f"✗ Agent failed: {error_msg}")
                    logger.info(f"\n[red]✗ Agent failed: {error_msg}[/red]")
            
            elif selected_poller:
                # Run poller once
                logger.info(f"Running poller: {selected_poller_name}")
                success = selected_poller.run_once()

                end_time = time.time()
                execution_time = end_time - start_time

                if success:
                    logger.info(
                        f"✓ Poller completed successfully ({execution_time:.1f}s)"
                    )
                    logger.info(f"\n[green]✓ Poller completed successfully[/green]")
                    logger.info(
                        f"[dim]Execution time: {execution_time:.2f}s[/dim]"
                    )
                else:
                    logger.error(f"✗ Poller failed")
                    logger.info(f"\n[red]✗ Poller failed after {execution_time:.2f}s[/red]")

        except Exception as e:
            end_time = time.time()
            execution_time = end_time - start_time
            item_type_str = "agent" if selected_agent else "poller"
            logger.error(f"✗ {item_type_str.capitalize()} error ({execution_time:.1f}s): {e}")
            logger.info(
                f"\n[red]✗ {item_type_str.capitalize()} error after {execution_time:.2f}s: {e}[/red]"
            )

    except Exception as e:
        logger.error(f"Error initializing orchestrator: {e}")
        logger.info(f"[red]✗ Error: {e}[/red]")

