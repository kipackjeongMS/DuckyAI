"""Orchestrator daemon and prompt execution functions."""

import os
import sys
import signal
from pathlib import Path
from rich.panel import Panel

from ..orchestrator.core import Orchestrator
from ..logger import Logger

logger = Logger(console_output=True)


def run_orchestrator_daemon(vault_path: Path = None, debug: bool = False, working_dir: str = None, config_file: Path = None, mcp_config: tuple = None, claude_settings: str = None):
    """
    Run orchestrator in daemon mode.

    Args:
        vault_path: Path to vault root (defaults to CWD)
        debug: Enable debug logging to console
        working_dir: Working directory for agent subprocess execution (defaults to vault_path)
        config_file: Path to orchestrator config file (defaults to orchestrator.yaml in working directory)
        mcp_config: Optional tuple of MCP config JSON files or strings
    """
    from ..config import Config

    config = Config(config_file=str(config_file) if config_file else None)

    # Use CWD as vault (requires config file in CWD)
    vault_path = vault_path or Path.cwd()
    pid_file = vault_path / ".orchestrator.pid"

    # Write PID file
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    max_concurrent = config.get_orchestrator_max_concurrent()

    debug_mode = "[yellow](DEBUG)[/yellow]" if debug else ""
    logger.info(Panel.fit(
        f"[bold cyan]DuckyAI Orchestrator[/bold cyan] {debug_mode}\n"
        f"Vault: {vault_path}\n"
        f"Max concurrent: {max_concurrent}\n"
        f"PID: {os.getpid()}",
        title="Starting"
    ))

    # Create orchestrator (it will load paths from config)
    orch = Orchestrator(
        vault_path=vault_path,
        max_concurrent=max_concurrent,
        config=config,
        working_dir=Path(working_dir) if working_dir else None,
        mcp_config=mcp_config,
        claude_settings=claude_settings
    )

    # Setup signal handlers — clean up PID file on exit
    def signal_handler(sig, frame):
        logger.info("\n[yellow]Received interrupt signal, shutting down...[/yellow]")
        pid_file.unlink(missing_ok=True)
        if orch:
            orch.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Show loaded agents
    status = orch.get_status()
    logger.info(f"\n[green]✓[/green] Loaded {status['agents_loaded']} agent(s):")
    for agent_info in status['agent_list']:
        logger.info(
            f"  • [{agent_info['abbreviation']}] {agent_info['name']} "
            f"({agent_info['category']})"
        )

    # Show loaded pollers
    pollers_list = list(orch.poller_manager.pollers.items())
    if pollers_list:
        logger.info(f"\n[green]✓[/green] Loaded {len(pollers_list)} poller(s):")
        for poller_name, poller in sorted(pollers_list, key=lambda p: p[0]):
            # Use relative path from config instead of absolute path
            target_dir_rel = poller.poller_config.get('target_dir', str(poller.target_dir))
            logger.info(
                f"  • {poller_name} → {target_dir_rel} "
                f"(interval: {poller.poll_interval}s)"
            )

    # Start orchestrator
    logger.info("\n[cyan]Starting orchestrator...[/cyan]")

    # Prompt user to sync Teams chat on startup
    tcs_agent = orch.agent_registry.agents.get("TCS")
    if tcs_agent and tcs_agent.cron:
        try:
            response = input("\n🔄 Sync Teams chats now? (y/n): ").strip().lower()
            if response in ("y", "yes"):
                logger.info("[cyan]Triggering Teams Chat Summary...[/cyan]")
                import threading
                def _run_tcs_sync():
                    orch.trigger_agent_once("TCS")
                sync_thread = threading.Thread(target=_run_tcs_sync, daemon=True)
                sync_thread.start()
                # Set cooldown so cron doesn't duplicate this run
                orch.cron_scheduler.set_cooldown("TCS")
                logger.info("[green]✓[/green] TCS triggered (running in background)")
        except (EOFError, KeyboardInterrupt):
            pass  # Non-interactive or interrupted — skip prompt

    try:
        orch.run_forever()
    finally:
        pid_file.unlink(missing_ok=True)


def execute_prompt_with_session(
    prompt: str,
    system_prompt: str = None,
    system_prompt_file: Path = None,
    append_system_prompt: str = None,
    append_system_prompt_file: Path = None,
    session_id: str = None,
    vault_path: Path = None,
    working_dir: str = None,
    config_file: Path = None,
    mcp_config: tuple = None,
    claude_settings: str = None
):
    """
    Execute a one-time prompt with Claude agent and optional session ID.
    Automatically resumes session if it exists, creates new if it doesn't.

    Args:
        prompt: The prompt text to execute
        system_prompt: The system prompt to use for the agent
        system_prompt_file: Path to file containing system prompt
        append_system_prompt: Additional system prompt to append
        append_system_prompt_file: Path to file containing additional system prompt to append
        session_id: Optional session ID for tracking related executions (auto resume/create)
        vault_path: Path to vault root (defaults to CWD)
        working_dir: Working directory for agent subprocess execution (defaults to vault_path)
        config_file: Path to orchestrator config file (defaults to orchestrator.yaml in working directory)
        mcp_config: Optional tuple of MCP config JSON files or strings
    """
    from ..config import Config
    import time

    config = Config(config_file=str(config_file) if config_file else None)
    vault_path = vault_path or Path.cwd()

    logger.info(Panel.fit(
        f"[bold cyan]Executing One-Time Prompt[/bold cyan]\n"
        f"Session ID: {session_id or '(none)'}\n"
        f"Mode: auto (resume if exists, create if not)",
        title="Prompt Execution"
    ))
    
    # Create orchestrator
    orch = Orchestrator(
        vault_path=vault_path,
        config=config,
        working_dir=Path(working_dir) if working_dir else None,
        mcp_config=mcp_config,
        claude_settings=claude_settings
    )
    
    # Execute prompt
    start_time = time.time()
    ctx = orch.execute_prompt_with_session(
        prompt=prompt,
        session_id=session_id,
        system_prompt=system_prompt,
        system_prompt_file=system_prompt_file,
        append_system_prompt=append_system_prompt,
        append_system_prompt_file=append_system_prompt_file
    )
    end_time = time.time()
    execution_time = end_time - start_time
    
    if ctx and ctx.success:
        logger.info(f"\n[green]✓ Prompt executed successfully ({execution_time:.1f}s)[/green]")
        if ctx.session_id:
            logger.info(f"[dim]Session ID: {ctx.session_id}[/dim]")
        # Display the response (cleaned for one-time prompts)
        logger.info(f"\n[bold cyan]Response:[/bold cyan]")
        if ctx.response:
            # Clean response: remove [Agent Name] prefixes for cleaner output
            import re
            cleaned_lines = []
            for line in ctx.response.split("\n"):
                cleaned_line = re.sub(r'^\[.*?\]\s*', '', line)
                cleaned_lines.append(cleaned_line)
            cleaned_response = "\n".join(cleaned_lines)
            logger.info(cleaned_response)
    else:
        error_msg = ctx.error_message if ctx else "Unknown error"
        logger.error(f"\n[red]✗ Prompt execution failed[/red]")
        logger.info(f"\n[bold cyan]Response:[/bold cyan]")
        # Clean response: remove [Agent Name] prefixes for cleaner output
        import re
        cleaned_lines = []
        for line in error_msg.split("\n"):
            cleaned_line = re.sub(r'^\[.*?\]\s*', '', line)
            cleaned_lines.append(cleaned_line)
        cleaned_response = "\n".join(cleaned_lines)
        logger.info(cleaned_response)
    
    return ctx

