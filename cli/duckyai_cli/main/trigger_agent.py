"""Handler for --trigger-agent command."""

import time
from pathlib import Path
from rich.console import Console

from ..logger import Logger
from ..config import Config
from ..orchestrator.core import Orchestrator

logger = Logger(console_output=True)

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

        # For Teams agents (TCS/TMS), prompt for lookback hours if not provided
        agent_params_override = None
        if selected_agent and selected_agent.abbreviation in ('TCS', 'TMS'):
            if lookback_hours is None:
                default_hours = selected_agent.agent_params.get('lookback_hours', 1 if selected_agent.abbreviation == 'TCS' else 24)
                console = Console()
                console.print(f"\n[bold blue]Lookback hours[/bold blue] for {selected_agent.abbreviation} first-run/manual trigger")
                console.print(f"[dim]How far back should the agent fetch data? (default: {default_hours}h)[/dim]")
                try:
                    user_input = console.input(f"[bold]Hours [{default_hours}]: [/bold]").strip()
                    lookback_hours = int(user_input) if user_input else default_hours
                except (ValueError, EOFError):
                    lookback_hours = default_hours
                console.print(f"[dim]Using lookback: {lookback_hours} hours[/dim]\n")
            agent_params_override = {'lookback_hours': lookback_hours}

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

