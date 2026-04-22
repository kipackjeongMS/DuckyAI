"""
Orchestrator core - main event loop and coordination.

Ties together file monitoring, agent matching, and execution management.
"""
import threading
import time
from pathlib import Path
from typing import Dict, Optional
from queue import Empty

from .file_monitor import FileSystemMonitor
from .agent_registry import AgentRegistry
from .execution_manager import ExecutionManager
from .models import TriggerEvent, ExecutionContext, AgentDefinition, WorkerConfig
from ..logger import Logger

logger = Logger()


class Orchestrator:
    """
    Main orchestrator for DuckyAI system.

    Coordinates file monitoring, agent matching, and task execution.
    """

    def __init__(
        self,
        vault_path: Path,
        working_dir: Optional[Path] = None,
        agents_dir: Optional[Path] = None,
        max_concurrent: Optional[int] = None,
        poll_interval: Optional[float] = None,
        config: Optional['Config'] = None,
        mcp_config: Optional[tuple] = None,
        claude_settings: Optional[str] = None,
    ):
        """
        Initialize orchestrator.

        Args:
            vault_path: Path to vault root
            working_dir: Working directory for agent subprocess execution (defaults to vault_path)
            agents_dir: Directory containing agent definitions (defaults to config orchestrator.prompts_dir)
            max_concurrent: Maximum concurrent task executions (defaults to config)
            poll_interval: Seconds between event queue polls (defaults to config)
            config: Config instance (will create default if None)
            mcp_config: Optional tuple of MCP config JSON files or strings
            claude_settings: Optional path or JSON string for Claude --settings flag
        """
        from ..config import Config
        from datetime import datetime

        self.vault_path = Path(vault_path)

        # Backward compatibility: older call sites passed agents_dir as the
        # second positional argument before working_dir existed.
        if agents_dir is None and working_dir is not None:
            legacy_agents_dir = Path(working_dir)
            if legacy_agents_dir.is_dir() and legacy_agents_dir.name.lower() in {"agents", "prompts-agent"}:
                agents_dir = legacy_agents_dir
                working_dir = None

        self.config = config or Config(vault_path=self.vault_path)
        self.mcp_config = mcp_config
        self.claude_settings = claude_settings

        # Use config values if not explicitly provided
        if agents_dir is None:
            prompts_dir = self.config.get_orchestrator_prompts_dir()
            # Resolve from playbook (system) first, fallback to vault-relative
            playbook_path = self.config.get_playbook_dir() / 'prompts-agent'
            if playbook_path.exists():
                self.agents_dir = playbook_path
            else:
                self.agents_dir = self.vault_path / prompts_dir
        else:
            self.agents_dir = agents_dir

        self.max_concurrent = max_concurrent or self.config.get_orchestrator_max_concurrent()
        self.poll_interval = poll_interval or self.config.get_orchestrator_poll_interval()

        # Ensure required directories exist
        self._ensure_directories()

        # Initialize components
        self.agent_registry = AgentRegistry(self.agents_dir, self.vault_path, self.config)
        self.execution_manager = ExecutionManager(
            self.vault_path,
            self.max_concurrent,
            self.config,
            orchestrator_settings=self.agent_registry.orchestrator_settings,
            working_dir=working_dir,
            mcp_config=mcp_config,
            claude_settings=claude_settings
        )
        # Wire up slot-freed callback so queued tasks drain immediately
        self.execution_manager._on_slot_freed = self._process_queued_tasks
        # Get file_extensions from orchestrator_settings (default to ['.md'] if not specified)
        file_extensions = self.agent_registry.orchestrator_settings.get('file_extensions', ['.md'])
        self.file_monitor = FileSystemMonitor(self.vault_path, self.agent_registry, file_extensions=file_extensions)

        # Initialize cron scheduler
        from .cron_scheduler import CronScheduler
        self.cron_scheduler = CronScheduler(
            self.agent_registry,
            self.file_monitor.event_queue,
            config=self.config
        )

        # Initialize poller manager
        from .poller_manager import PollerManager
        self.poller_manager = PollerManager(
            vault_path=self.vault_path,
            config=self.config
        )

        # Control state
        self._running = False
        self._event_thread: Optional[threading.Thread] = None

        # Hot-reload state management
        self._reload_lock = threading.Lock()
        self._reload_thread: Optional[threading.Thread] = None
        self._pending_reload_during_reload = False  # Flag to track if reload needed after current reload completes
        self._swap_lock = threading.Lock()
        self._swap_in_progress = False
        self._reload_in_progress = False  # Flag to prevent concurrent reload starts
        self._reload_start_lock = threading.Lock()  # Lock for atomic reload start check

        # Guard _process_queued_tasks against concurrent invocations
        # (event loop + slot-freed callback can race)
        self._queue_processing_lock = threading.Lock()

        # Cooldown to prevent duplicate dependent dispatch within 60s.
        self._dependent_cooldown: Dict[str, float] = {}  # agent_abbr → last_dispatch_timestamp
        self._dependent_cooldown_lock = threading.Lock()

        # Track parent output for require_parent_output.
        # Key: dependent_abbr → {parent_abbr: bool (had output)}
        self._parent_output_tracker: Dict[str, Dict[str, bool]] = {}

        logger.info(f"Orchestrator initialized for vault: {self.vault_path}")
        logger.info(f"Loaded {len(self.agent_registry.agents)} agents")
        logger.info(f"Loaded {len(self.poller_manager.pollers)} poller(s)")

    def _ensure_directories(self):
        """Create runtime directories if they don't exist."""
        # Only create runtime dirs and user-facing skills dir
        # System dirs (prompts-agent, bases) live in the package .playbook/
        directories = [
            self.config.get_orchestrator_tasks_dir(),
            self.config.get_orchestrator_logs_dir(),
            self.config.get('orchestrator.skills_dir', '.github/skills'),
        ]

        created = []
        # Create each directory
        for dir_path in directories:
            full_path = self.vault_path / dir_path
            if not full_path.exists():
                full_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created directory: {dir_path}")
                created.append(dir_path)

        if created:
            dir_word = "directory" if len(created) == 1 else "directories"
            logger.info(f"Created {len(created)} missing {dir_word}: {', '.join(created)}")

    def start(self):
        """Start the orchestrator event loop."""
        if self._running:
            logger.warning("Orchestrator already running")
            return

        # Log the resolved runtime root for easier debugging
        from ..config import get_global_runtime_dir
        vault_id = self.config.get("id", "default")
        runtime_root = get_global_runtime_dir(vault_id, vault_path=self.vault_path)
        logger.info(f"Runtime root: {runtime_root}")

        logger.info("Starting orchestrator...")

        # Start file monitor
        self.file_monitor.start()

        # Start cron scheduler
        self.cron_scheduler.start()

        # Start pollers
        self.poller_manager.start_all()

        # Start event processing thread
        self._running = True
        self._event_thread = threading.Thread(target=self._event_loop, daemon=True)
        self._event_thread.start()

        logger.info("Orchestrator started successfully")

        # Process any existing QUEUED tasks in the background so we don't
        # block the calling thread (which may be a Flask request handler).
        threading.Thread(
            target=self._load_queued_tasks_on_startup,
            name="queued-task-loader",
            daemon=True,
        ).start()

    def _load_queued_tasks_on_startup(self):
        """
        Load and process existing QUEUED tasks on startup.

        Also cleans up stale IN_PROGRESS entries from previous runs that
        never completed (e.g. process crash, daemon thread death).

        Uses v2 daily log API to find QUEUED entries.
        """
        # ── Phase 1: Mark stale IN_PROGRESS entries as FAILED ──
        try:
            self._cleanup_stale_tasks()
        except Exception as e:
            logger.error(f"Error cleaning up stale tasks on startup: {e}", exc_info=True)

        # ── Phase 2: Re-dispatch QUEUED entries ──
        try:
            queued_count = self.execution_manager.task_manager.count_queued()

            if queued_count > 0:
                logger.info(f"Found {queued_count} QUEUED task(s) from previous run")
                for _ in range(queued_count):
                    self._process_queued_tasks()
        except Exception as e:
            logger.error(f"Error loading queued tasks on startup: {e}", exc_info=True)

    def _cleanup_stale_tasks(self):
        """
        Mark stale IN_PROGRESS entries as FAILED on startup.

        Builds a per-agent timeout map from agent definitions and delegates
        to ``TaskFileManagerV2.mark_stale_as_failed``.
        """
        agent_timeouts = {
            agent.abbreviation: agent.timeout_minutes
            for agent in self.agent_registry.agents.values()
        }

        count = self.execution_manager.task_manager.mark_stale_as_failed(
            default_timeout_minutes=30,
            agent_timeouts=agent_timeouts,
        )

        if count:
            logger.info(f"♻️ Cleaned up {count} stale IN_PROGRESS task(s) from previous run", console=True)

    def stop(self):
        """Stop the orchestrator event loop."""
        if not self._running:
            logger.warning("Orchestrator not running")
            return

        logger.info("Stopping orchestrator...")

        # Stop event processing
        self._running = False

        # Stop pollers
        self.poller_manager.stop_all()

        # Stop cron scheduler
        self.cron_scheduler.stop()

        # Stop file monitor
        self.file_monitor.stop()

        # Wait for reload thread to finish (if in progress)
        if self._reload_thread and self._reload_thread.is_alive():
            logger.info("Waiting for configuration reload to complete...")
            self._reload_thread.join(timeout=10.0)

        # Wait for event thread to finish
        if self._event_thread and self._event_thread.is_alive():
            self._event_thread.join(timeout=5.0)

        logger.info("Orchestrator stopped")

    def _trigger_reload(self):
        """Trigger configuration reload immediately."""
        # Use lock to atomically check and set reload start flag
        with self._reload_start_lock:
            # Double-check after acquiring lock (prevent race condition)
            if self._reload_in_progress:
                return
            
            # Check if reload thread is already running
            if self._reload_thread is not None and self._reload_thread.is_alive():
                return
            
            # Set flag and start reload in background thread (atomic)
            self._reload_in_progress = True
            self._reload_thread = threading.Thread(
                target=self._reload_configuration,
                daemon=True
            )
            self._reload_thread.start()
            logger.info("Starting configuration reload...")

    def _reload_configuration(self):
        """
        Two-phase reload: build new config in parallel, then atomically swap.
        
        Phase 1: Build new config (non-blocking)
        Phase 2: Wait for old executions, then atomically swap
        """
        # Acquire reload lock to prevent concurrent reloads
        if not self._reload_lock.acquire(blocking=False):
            logger.warning("Reload already in progress, skipping")
            self._reload_in_progress = False  # Reset flag if we couldn't acquire lock
            return

        try:
            logger.info("=" * 60)
            logger.info("🔄 Starting configuration hot-reload", console=True)
            logger.info("=" * 60)

            # Phase 1: Build New Config (Non-blocking)
            logger.info("Phase 1: Building new configuration...")
            
            # Reload config from disk
            if not self.config.reload():
                logger.error("Failed to reload config, aborting reload")
                return
            
            # Create new AgentRegistry instance (doesn't affect running system)
            new_agent_registry = AgentRegistry(
                self.agents_dir,
                self.vault_path,
                self.config
            )
            
            # Get new orchestrator settings
            new_orchestrator_settings = new_agent_registry.orchestrator_settings
            new_max_concurrent = new_orchestrator_settings.get(
                'max_concurrent',
                self.config.get_orchestrator_max_concurrent()
            )
            
            logger.info("Phase 1 complete: New configuration built")
            logger.info(f"  - Agents loaded: {len(new_agent_registry.agents)}")
            logger.info(f"  - Max concurrent: {new_max_concurrent}")

            # Phase 2: Atomic Swap (Blocking)
            logger.info("Phase 2: Waiting for running executions to complete...")
            
            # Pause event processing during entire Phase 2 (prevents new executions from starting)
            self._swap_in_progress = True
            logger.info("Event processing paused - new events will be queued until reload completes")
            
            # Wait for all running executions to complete
            timeout_seconds = 300  # 5 minutes
            start_wait_time = time.time()
            last_log_time = start_wait_time
            
            while True:
                running_executions = self.execution_manager.get_running_executions()
                
                if not running_executions:
                    logger.info("All running executions completed")
                    break
                
                # Check timeout
                elapsed = time.time() - start_wait_time
                if elapsed > timeout_seconds:
                    logger.warning(
                        f"Timeout waiting for {len(running_executions)} execution(s) to complete. "
                        "Proceeding with reload anyway."
                    )
                    break
                
                # Log progress every 10 seconds
                if time.time() - last_log_time >= 10:
                    logger.info(f"Waiting for {len(running_executions)} execution(s) to complete...")
                    last_log_time = time.time()
                
                time.sleep(0.5)
            
            # Atomic swap
            logger.info("Performing atomic configuration swap...")
            
            try:
                with self._swap_lock:
                    # Swap agent registry
                    old_agent_registry = self.agent_registry
                    self.agent_registry = new_agent_registry
                    
                    # Update execution manager settings (including MCP config refresh)
                    self.execution_manager.update_settings(new_max_concurrent, refresh_mcp=True)
                    
                    # Update max_concurrent for orchestrator
                    self.max_concurrent = new_max_concurrent
                    
                    # Reload pollers
                    self.poller_manager.reload()
                    
                    # Update cron scheduler with new agent registry
                    self.cron_scheduler.update_agent_registry(new_agent_registry)
                    
                    logger.info("Atomic swap complete")
            
            finally:
                self._swap_in_progress = False
            
            logger.info("=" * 60)
            logger.info("🎉 Configuration hot-reload completed successfully", console=True)
            logger.info("=" * 60)
            
            # Process any pending QUEUED tasks with new registry
            logger.info("Processing pending QUEUED tasks with new configuration...")
            self._process_queued_tasks()

        except Exception as e:
            logger.error(f"Error during configuration reload: {e}", exc_info=True)
            logger.error("Keeping existing configuration active")
        finally:
            self._reload_lock.release()
            self._reload_in_progress = False  # Reset flag when reload completes
            
            # Check if another reload was requested during this reload
            if self._pending_reload_during_reload:
                logger.info("Another duckyai.yml change detected during reload, triggering follow-up reload...")
                self._pending_reload_during_reload = False
                self._trigger_reload()

    def _event_loop(self):
        """
        Main event processing loop.

        Polls file monitor queue and processes events.
        """
        logger.info("Event loop started")

        while self._running:
            try:
                # Check if reload is in progress (pause event processing during reload wait phase)
                if self._swap_in_progress:
                    time.sleep(0.1)
                    continue  # Skip event processing - events will queue up and process after reload

                # Poll event queue with timeout
                try:
                    trigger_event = self.file_monitor.event_queue.get(timeout=self.poll_interval)
                except Empty:
                    # No events, continue polling
                    continue

                # Handle config reload events specially
                if trigger_event.event_type == 'config_reload':
                    logger.info("Detected duckyai.yml change")
                    # If reload is already in progress, mark that we need another reload after this one completes
                    if self._reload_in_progress:
                        logger.debug("Reload already in progress, will trigger another reload after current one completes")
                        self._pending_reload_during_reload = True
                    else:
                        # Trigger reload immediately (no debounce)
                        self._trigger_reload()
                    continue  # Don't process as regular event

                # Process event
                self._process_event(trigger_event)

                # Check for queued tasks after processing event
                self._process_queued_tasks()

            except Exception as e:
                logger.error(f"Error in event loop: {e}", exc_info=True)
                time.sleep(self.poll_interval)

        logger.info("Event loop stopped")

    def _process_event(self, trigger_event: TriggerEvent):
        """
        Process a single trigger event.

        Args:
            trigger_event: Trigger event to process (file or scheduled)
        """
        logger.debug(f"Processing event: {trigger_event.event_type} {trigger_event.path}")

        # 1. Handle Task Files
        # Task files are special: they control execution flow and shouldn't trigger other agents
        if self._is_task_file(trigger_event.path):
            try:
                # Always read from file to get the latest status
                from ..markdown_utils import read_frontmatter
                frontmatter = read_frontmatter(self.vault_path / trigger_event.path)
                status = frontmatter.get('status', '').upper()
                
                if status == 'QUEUED':
                    logger.debug(f"Detected QUEUED task file: {trigger_event.path}")
                    self._enrich_queued_task(trigger_event)
                else:
                    logger.debug(f"Ignoring task file update (status={status}): {trigger_event.path}")
            except Exception as e:
                logger.error(f"Error processing task file {trigger_event.path}: {e}")
            
            return  # Stop processing for task files (don't trigger agents)

        # 2. Regular File Processing
        # Convert TriggerEvent to event_data dict
        event_data = {
            'path': trigger_event.path,
            'event_type': trigger_event.event_type,
            'is_directory': trigger_event.is_directory,
            'timestamp': trigger_event.timestamp,
            'frontmatter': trigger_event.frontmatter
        }

        # Find matching agents
        matching_agents = self.agent_registry.find_matching_agents(event_data)

        # If the event targets a specific agent, filter to only that agent
        if trigger_event.target_agent:
            matching_agents = [a for a in matching_agents if a.abbreviation == trigger_event.target_agent]

        if not matching_agents:
            logger.debug(f"No agents match event: {trigger_event.path}")
            return

        logger.debug(f"Found {len(matching_agents)} matching agent(s) for {trigger_event.path}")

        # Execute each matching agent
        for agent in matching_agents:
            # Check if this is a multi-worker agent
            if agent.workers:
                # Dispatch to ALL workers in parallel
                self._dispatch_multi_worker(agent, event_data, trigger_event)
            else:
                # Single-worker execution (existing logic)
                self._dispatch_single_worker(agent, event_data, trigger_event)

    def _dispatch_single_worker(self, agent: AgentDefinition, event_data: dict, trigger_event: TriggerEvent):
        """
        Dispatch a single-worker agent execution.

        Args:
            agent: Agent definition to execute
            event_data: Event data dictionary
            trigger_event: Original trigger event
        """
        # Backward compatibility: older tests patch can_execute() directly.
        if not self.execution_manager.can_execute(agent):
            self._create_queued_task(agent, event_data)
            logger.info(f"Queued {agent.abbreviation}: concurrency limit reached")
            return

        # Try to reserve a slot atomically (prevents race conditions)
        if not self.execution_manager.reserve_slot(agent):
            # Create QUEUED task instead of dropping
            self._create_queued_task(agent, event_data)
            logger.info(f"Queued {agent.abbreviation}: concurrency limit reached")
            return

        # Persist a QUEUED task file BEFORE starting the thread so that if the
        # process crashes between now and the point where execute() creates
        # the task, the work is recoverable on next startup.
        queued_task_path = self._create_queued_task(agent, event_data)
        if queued_task_path:
            event_data = {**event_data, '_existing_task_file': str(queued_task_path)}

        # Log agent trigger at INFO level for visibility
        input_filename = Path(trigger_event.path).name if trigger_event.path else "scheduled"
        logger.info(f"🚀 Triggering {trigger_event.event_type} agent: {agent.abbreviation} ({input_filename})", console=True)
        logger.debug(f"Starting {agent.abbreviation}: {trigger_event.path}")

        if not self._running:
            logger.debug(
                f"Running {agent.abbreviation} synchronously because orchestrator is not running"
            )
            self._execute_agent(agent, event_data, True)
            return

        # Execute in background thread (slot already reserved)
        execution_thread = threading.Thread(
            target=self._execute_agent,
            args=(agent, event_data, True),  # slot_reserved=True
            daemon=True
        )
        execution_thread.start()

    def _dispatch_multi_worker(self, agent: AgentDefinition, event_data: dict, trigger_event: TriggerEvent):
        """
        Dispatch a multi-worker agent to all configured workers in parallel.

        Args:
            agent: Base agent definition with workers list
            event_data: Event data dictionary
            trigger_event: Original trigger event
        """
        input_filename = Path(trigger_event.path).name if trigger_event.path else "scheduled"
        logger.info(f"🚀 Triggering multi-worker agent: {agent.abbreviation} ({input_filename}) with {len(agent.workers)} workers", console=True)

        for worker in agent.workers:
            # Create worker-specific agent variant
            worker_agent = self._create_worker_agent_variant(agent, worker)

            # Backward compatibility: older tests patch can_execute() directly.
            if not self.execution_manager.can_execute(worker_agent):
                self._create_queued_task(worker_agent, event_data)
                logger.info(f"Queued {worker_agent.abbreviation}: concurrency limit reached")
                continue

            # Try to reserve a slot for this worker
            if not self.execution_manager.reserve_slot(worker_agent):
                # Create QUEUED task for this worker
                self._create_queued_task(worker_agent, event_data)
                logger.info(f"Queued {worker_agent.abbreviation}: concurrency limit reached")
                continue

            logger.debug(f"Starting worker {worker_agent.abbreviation}: {trigger_event.path}")

            if not self._running:
                logger.debug(
                    f"Running worker {worker_agent.abbreviation} synchronously because orchestrator is not running"
                )
                self._execute_agent(worker_agent, event_data, True)
                continue

            # Execute in background thread (slot already reserved)
            execution_thread = threading.Thread(
                target=self._execute_agent,
                args=(worker_agent, event_data, True),  # slot_reserved=True
                daemon=True
            )
            execution_thread.start()

    def _create_queued_task(self, agent: AgentDefinition, event_data: dict):
        """
        Create a QUEUED execution entry for an agent that couldn't get a slot.

        Args:
            agent: Agent definition (may be a worker variant)
            event_data: Event data dictionary

        Returns:
            Execution ID string, or None on failure
        """
        import json
        from datetime import datetime, date

        # Convert all date/datetime objects to strings for JSON serialization
        def make_json_serializable(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: make_json_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_json_serializable(item) for item in obj]
            else:
                return obj

        event_data_serializable = make_json_serializable(event_data)
        trigger_data_json = json.dumps(event_data_serializable, ensure_ascii=False)

        ctx = ExecutionContext(
            agent=agent,
            trigger_data=event_data,
            start_time=self.config.user_now()
        )

        exec_id = self.execution_manager.task_manager.create_task_file(
            ctx, agent,
            initial_status="QUEUED",
            trigger_data_json=trigger_data_json
        )
        return exec_id

    def _execute_agent(self, agent, event_data, slot_reserved=False):
        """
        Execute an agent task.

        Args:
            agent: AgentDefinition to execute
            event_data: Event data dictionary (may contain 'session_id' key or in 'frontmatter')
            slot_reserved: Whether slot was already reserved

        Returns:
            ExecutionContext if execution completed, None on error
        """
        try:
            # Extract session_id from event_data
            session_id = event_data.get('session_id')
            if not session_id and 'frontmatter' in event_data:
                session_id = event_data['frontmatter'].get('session_id')
            
            ctx = self.execution_manager.execute(
                agent, event_data, 
                slot_reserved=slot_reserved, 
                session_id=session_id,
                resume_session=False  # Auto-detect in _execute_claude_code
            )

            if ctx.success:
                logger.info(f"{agent.abbreviation} completed ({ctx.duration:.1f}s)")
                # Post-execution hooks
                self._run_post_execution(agent, ctx, event_data)
                # Dispatch dependent agents (trigger_wait_for)
                # Skip for dequeued tasks — the original cron run handles dependents
                if not event_data.get('_from_queue'):
                    self._dispatch_dependents(agent, ctx)
            else:
                duration_str = f"{ctx.duration:.1f}s" if ctx.duration else "unknown"
                error_msg = f"{agent.abbreviation} failed: {ctx.status} ({duration_str})"
                if ctx.error_message:
                    error_msg += f" - {ctx.error_message}"
                logger.error(error_msg)

            return ctx

        except Exception as e:
            logger.error(f"{agent.abbreviation} error: {e}", exc_info=True)
            return None

    def _run_post_execution(self, agent: AgentDefinition, ctx: ExecutionContext, event_data: dict):
        """Run post-execution hooks after a successful agent run."""
        try:
            # PR agent: check off the reviewed PR in today's daily note
            if agent.abbreviation == 'PR' and event_data.get('path'):
                self._checkoff_pr_in_daily_note(event_data['path'])
        except Exception as e:
            logger.warning(f"Post-execution hook failed for {agent.abbreviation}: {e}")

    def _checkoff_pr_in_daily_note(self, pr_file_path: str):
        """Mark a PR review as completed in today's daily note.

        Finds the matching `- [ ]` line in the `## PRs & Code Reviews` section
        that links to the PR file and changes it to `- [x]`.
        """
        import re
        from datetime import date

        today_str = date.today().strftime('%Y-%m-%d')
        daily_note = self.vault_path / '04-Periodic' / 'Daily' / f'{today_str}.md'
        if not daily_note.exists():
            logger.debug(f"No daily note for {today_str}, skipping PR checkoff")
            return

        content = daily_note.read_text(encoding='utf-8')

        # Extract the PR filename (without extension) to match against wiki links
        pr_filename = Path(pr_file_path).stem

        # Find the ## PRs & Code Reviews section
        section_match = re.search(r'^## PRs & Code Reviews\n(.*?)(?=^## |\Z)', content, re.MULTILINE | re.DOTALL)
        if not section_match:
            logger.debug("No '## PRs & Code Reviews' section found in daily note")
            return

        section_start = section_match.start(1)
        section_text = section_match.group(1)

        # Find unchecked line that references this PR file
        # Matches: - [ ] ...PR filename... (wiki link or plain text)
        updated_section = []
        found = False
        for line in section_text.splitlines(keepends=True):
            if not found and '- [ ]' in line and pr_filename in line:
                line = line.replace('- [ ]', '- [x]', 1)
                found = True
            updated_section.append(line)

        if found:
            new_section = ''.join(updated_section)
            new_content = content[:section_start] + new_section + content[section_start + len(section_text):]
            daily_note.write_text(new_content, encoding='utf-8')
            logger.info(f"✅ Checked off PR in daily note: {pr_filename}", console=True)
        else:
            logger.debug(f"No unchecked PR entry found for {pr_filename} in daily note")

    def _dispatch_dependents(self, completed_agent: AgentDefinition, ctx: ExecutionContext,
                              _chain_depth: int = 0):
        """
        After a successful execution, dispatch any agents that depend on the completed agent
        via `trigger_wait_for`.

        Dispatch logic: when a parent completes, check whether any *other* listed
        parents are still running (via ExecutionManager slot counts).  If none are
        running, dispatch the dependent immediately.  If siblings are still active,
        do nothing — their own completions will re-evaluate and eventually trigger
        the dependent once the last one finishes.

        This is resilient to any combination of parents running or not:
        - Only TCS runs → TCS completes → TMS not running → dispatch TM
        - Both run     → first completes → sibling still running → skip;
                         second completes → no siblings running → dispatch TM

        A small grace period (3s) is applied before dispatch to ensure file writes
        from the last parent are fully flushed to disk.

        Args:
            completed_agent: The agent that just completed successfully
            ctx: The execution context of the completed agent
            _chain_depth: Internal counter to prevent infinite circular chains
        """
        if _chain_depth > 10:
            logger.warning(
                f"Dependency chain depth exceeded (>{10}) after {completed_agent.abbreviation}, "
                "possible circular dependency — aborting"
            )
            return

        completed_abbr = completed_agent.abbreviation
        now = time.time()

        for dep_agent in list(self.agent_registry.agents.values()):
            # Skip if this agent doesn't depend on the completed one
            if completed_abbr not in dep_agent.trigger_wait_for:
                continue

            # Guard: skip self-referential dependencies
            if dep_agent.abbreviation == completed_abbr:
                logger.warning(
                    f"Self-referential trigger_wait_for in {dep_agent.abbreviation}, skipping"
                )
                continue

            dep_key = dep_agent.abbreviation

            with self._dependent_cooldown_lock:
                # Cooldown: prevent duplicate dispatch
                last_dispatch = self._dependent_cooldown.get(dep_key, 0.0)
                if now - last_dispatch < 60:
                    logger.info(
                        f"⛓️ {completed_abbr} → {dep_key} skipped (cooldown, "
                        f"dispatched {now - last_dispatch:.0f}s ago)"
                    )
                    continue

                # Record parent output status for require_parent_output check
                if dep_key not in self._parent_output_tracker:
                    self._parent_output_tracker[dep_key] = {}
                self._parent_output_tracker[dep_key][completed_abbr] = ctx.output_produced

                # Check if any sibling parents are still running
                siblings_running = []
                for parent_abbr in dep_agent.trigger_wait_for:
                    if parent_abbr == completed_abbr:
                        continue  # just finished
                    if self.execution_manager.get_agent_running_count(parent_abbr) > 0:
                        siblings_running.append(parent_abbr)

                if siblings_running:
                    logger.info(
                        f"⛓️ {completed_abbr} ✓ for {dep_key}, "
                        f"waiting on running: {', '.join(sorted(siblings_running))}",
                        console=True
                    )
                    continue

                # All parents done — check require_parent_output
                if dep_agent.require_parent_output:
                    tracker = self._parent_output_tracker.get(dep_key, {})
                    any_output = any(tracker.values())
                    if not any_output:
                        logger.info(
                            f"⛓️ {dep_key} skipped — require_parent_output is set "
                            f"but no parent produced output: {tracker}",
                            console=True
                        )
                        # Clean up tracker for next cycle
                        self._parent_output_tracker.pop(dep_key, None)
                        continue

                # Clean up tracker after decision
                self._parent_output_tracker.pop(dep_key, None)

                # No siblings running — dispatch
                self._dependent_cooldown[dep_key] = now

            try:
                logger.info(
                    f"⛓️ All parents complete → dispatching {dep_agent.abbreviation}",
                    console=True
                )

                # Grace period: let file writes from parent agents flush to disk
                time.sleep(3)

                # Build a synthetic trigger event carrying the parent's context
                dep_event_data = {
                    'path': '',
                    'event_type': 'dependent',
                    'is_directory': False,
                    'timestamp': ctx.end_time or ctx.start_time,
                    'frontmatter': {},
                    'triggered_by': completed_abbr,
                }

                if self._running:
                    # Daemon mode: dispatch via normal path (background thread,
                    # respects concurrency limits, queuing)
                    self._dispatch_single_worker(dep_agent, dep_event_data, TriggerEvent(
                        path='',
                        event_type='dependent',
                        is_directory=False,
                        timestamp=ctx.end_time or ctx.start_time,
                        frontmatter={},
                    ))
                else:
                    # Synchronous mode (trigger_agent_once / onboarding):
                    # no event loop running, so execute inline to prevent
                    # orphaned daemon threads that die with the process.
                    logger.info(
                        f"🚀 Running dependent {dep_agent.abbreviation} synchronously",
                        console=True,
                    )
                    dep_ctx = self._execute_agent(dep_agent, dep_event_data, slot_reserved=False)
                    if dep_ctx and dep_ctx.success:
                        logger.info(
                            f"{dep_agent.abbreviation} completed ({dep_ctx.duration:.1f}s)"
                        )
            except Exception as e:
                logger.error(
                    f"Failed to dispatch dependent {dep_agent.abbreviation} "
                    f"after {completed_abbr}: {e}",
                    exc_info=True
                )

    def _process_queued_tasks(self):
        """
        Process any QUEUED tasks if capacity is available.

        Checks task files for QUEUED status and executes them when slots free up.
        Only processes one task per iteration to avoid thundering herd.

        Thread-safe: guarded by _queue_processing_lock so concurrent calls
        from the event loop and slot-freed callbacks don't race.
        """
        if not self._queue_processing_lock.acquire(blocking=False):
            return  # Another thread is already draining the queue

        try:
            self._process_queued_tasks_inner()
        finally:
            self._queue_processing_lock.release()

    def _process_queued_tasks_inner(self):
        """Inner implementation of queue processing (caller holds lock).

        Uses TaskFileManagerV2.find_queued_entries() to read QUEUED entries
        from the v2 daily log format (entries array inside YYYY-MM-DD.md).
        """
        import json

        try:
            queued = self.execution_manager.task_manager.find_queued_entries()
            if not queued:
                return

            # Sort by created time (FIFO)
            queued.sort(key=lambda e: e.get('created', ''))

            for entry in queued:
                exec_id = entry.get('id', '')
                agent_abbr = entry.get('task_type') or entry.get('agent', '')
                worker_label = entry.get('worker_label', '')
                worker_executor = entry.get('worker')
                trigger_data_json = entry.get('trigger_data_json', '')

                if not agent_abbr:
                    logger.warning(f"Malformed QUEUED entry: missing task_type (id={exec_id})")
                    continue

                if not trigger_data_json:
                    logger.warning(f"QUEUED entry missing trigger_data_json (id={exec_id})")
                    continue

                # Look up base agent definition
                base_agent = self.agent_registry.agents.get(agent_abbr)
                if not base_agent:
                    logger.warning(
                        f"Agent '{agent_abbr}' not found for QUEUED entry [{exec_id}]. "
                        "Agent may have been removed in configuration reload."
                    )
                    self.execution_manager.task_manager.update_task_status(
                        exec_id,
                        "FAILED",
                        error_message=f"Agent '{agent_abbr}' not found after configuration reload"
                    )
                    continue

                # Reconstruct worker agent variant if this was a multi-worker task
                if worker_label and base_agent.workers:
                    worker_config = None
                    for w in base_agent.workers:
                        if w.label == worker_label:
                            worker_config = w
                            break

                    if worker_config:
                        agent = self._create_worker_agent_variant(base_agent, worker_config)
                    elif worker_executor:
                        from dataclasses import replace
                        logger.info(f"Worker '{worker_label}' not in current config, using stored executor '{worker_executor}'")
                        agent = replace(
                            base_agent,
                            abbreviation=f"{agent_abbr}-{worker_label}",
                            executor=worker_executor
                        )
                    else:
                        logger.warning(f"Worker '{worker_label}' not found in agent '{agent_abbr}', using base agent")
                        agent = base_agent
                else:
                    agent = base_agent

                # Apply agent_params overrides from the entry
                task_agent_params = entry.get('agent_params')
                if task_agent_params:
                    if isinstance(task_agent_params, str):
                        try:
                            task_agent_params = json.loads(task_agent_params)
                        except json.JSONDecodeError:
                            task_agent_params = None
                    if isinstance(task_agent_params, dict):
                        import copy
                        agent = copy.copy(agent)
                        agent.agent_params = {**agent.agent_params, **task_agent_params}

                # Try to reserve a slot atomically
                if not self.execution_manager.reserve_slot(agent):
                    break  # Still no capacity, wait for next iteration

                # Reconstruct trigger data from JSON string
                try:
                    event_data = json.loads(trigger_data_json)
                except json.JSONDecodeError:
                    try:
                        event_data = json.loads(trigger_data_json.replace('\\"', '"'))
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse trigger_data_json for [{exec_id}]: {e}")
                        # Release the reserved slot
                        with self.execution_manager._count_lock:
                            self.execution_manager._running_count -= 1
                        with self.execution_manager._agent_lock:
                            self.execution_manager._agent_counts[agent.abbreviation] -= 1
                        continue

                event_path = event_data.get('path', '')
                logger.debug(f"Starting queued {agent.abbreviation} [{exec_id}]: {event_path}")

                # Inject existing execution id so execute() reuses the entry
                event_data['_existing_task_id'] = exec_id
                # Mark as dequeued so _execute_agent skips dependent dispatch
                # (the original run already dispatched dependents)
                event_data['_from_queue'] = True

                execution_thread = threading.Thread(
                    target=self._execute_agent,
                    args=(agent, event_data, True),  # slot_reserved=True
                    daemon=True
                )
                execution_thread.start()

                # Only start one task per iteration
                break

        except Exception as e:
            logger.error(f"Error processing queued tasks: {e}", exc_info=True)

    def _is_task_file(self, file_path: str) -> bool:
        """
        Check if the file is in the tasks directory.
        
        Args:
            file_path: Relative path to check
            
        Returns:
            True if file is in tasks directory and is a markdown file
        """
        try:
            tasks_dir = self.execution_manager.task_manager.tasks_dir
            file_full_path = self.vault_path / file_path
            
            try:
                file_full_path.relative_to(tasks_dir)
                return file_path.endswith('.md')
            except ValueError:
                return False
        except Exception:
            return False

    def _extract_input_path_from_task_body(self, task_body: str) -> Optional[str]:
        """
        Extract input file path from task body content.

        Looks for wiki links in the "## Input" section.

        Args:
            task_body: Task file body content (after frontmatter)

        Returns:
            Extracted input path or None if not found
        """
        import re
        
        # Look for "## Input" section
        input_section_match = re.search(r'##\s+Input\s*\n(.*?)(?=\n##|\Z)', task_body, re.DOTALL | re.IGNORECASE)
        if not input_section_match:
            return None
        
        input_section = input_section_match.group(1)
        
        # Look for markdown links [text](path/to/file.md) first
        md_link_pattern = r'\[[^\]]*\]\(([^)]+)\)'
        md_matches = re.findall(md_link_pattern, input_section)
        if md_matches:
            from urllib.parse import unquote
            return unquote(md_matches[0])
        
        # Fall back to wiki links [[path/to/file]] or `[[path/to/file]]`
        wiki_link_pattern = r'(?:`)?\[\[([^\]]+)\]\](?:`)?'
        matches = re.findall(wiki_link_pattern, input_section)
        
        if matches:
            return matches[0]
        
        # Look for file paths in backticks
        backtick_pattern = r'`([^`]+\.md)`'
        matches = re.findall(backtick_pattern, input_section)
        
        if matches:
            return matches[0]
        
        return None

    def _enrich_queued_task(self, trigger_event: TriggerEvent):
        """
        Enrich a QUEUED task file by adding trigger_data_json if missing.

        Reads the task file, extracts agent type and input path,
        creates synthetic trigger event data, and adds trigger_data_json.

        Args:
            trigger_event: Trigger event for the QUEUED task file
        """
        from ..markdown_utils import read_frontmatter, extract_body

        try:
            # Get full path to task file
            task_file_path = self.vault_path / trigger_event.path
            
            if not task_file_path.exists():
                logger.warning(f"QUEUED task file not found: {trigger_event.path}")
                return

            # Read task file
            frontmatter = read_frontmatter(task_file_path)
            
            # Check if status is actually QUEUED and missing trigger_data_json
            current_status = frontmatter.get('status', '').upper()
            if current_status != 'QUEUED':
                logger.debug(f"Task file {trigger_event.path} is not QUEUED (status: {current_status}), skipping")
                return

            # Skip if trigger_data_json already exists
            if frontmatter.get('trigger_data_json'):
                logger.debug(f"QUEUED task already has trigger_data_json: {trigger_event.path}")
                return

            # Enrich with trigger data
            trigger_data_json = self._enrich_queued_task_with_trigger_data(task_file_path, frontmatter)
            if trigger_data_json:
                logger.info(f"🔄 Enriched QUEUED task with trigger data: {task_file_path.name}", console=True)

        except Exception as e:
            logger.error(f"Error enriching QUEUED task {trigger_event.path}: {e}", exc_info=True)

    def _enrich_queued_task_with_trigger_data(self, task_file_path: Path, frontmatter: dict) -> Optional[str]:
        """
        Enrich a QUEUED task with trigger_data_json by extracting input path and creating synthetic event.

        Args:
            task_file_path: Path to task file
            frontmatter: Task file frontmatter

        Returns:
            JSON string of trigger data, or None if enrichment failed
        """
        from ..markdown_utils import extract_body
        import json
        from datetime import datetime, date

        try:
            # Extract agent abbreviation
            agent_abbr = frontmatter.get('task_type')
            if not agent_abbr:
                logger.warning(f"QUEUED task file missing task_type: {task_file_path}")
                self.execution_manager.task_manager.update_task_status(
                    task_file_path,
                    "FAILED",
                    error_message="Missing task_type in frontmatter"
                )
                return None

            # Look up agent definition
            agent = self.agent_registry.agents.get(agent_abbr)
            if not agent:
                logger.warning(
                    f"Agent '{agent_abbr}' not found for QUEUED task: {task_file_path}. "
                    "Agent may have been removed in configuration reload."
                )
                self.execution_manager.task_manager.update_task_status(
                    task_file_path,
                    "FAILED",
                    error_message=f"Agent '{agent_abbr}' not found"
                )
                return None

            # Read task body to extract input path
            task_content = task_file_path.read_text(encoding='utf-8')
            task_body = extract_body(task_content)

            # Extract input file path from task body
            input_path = self._extract_input_path_from_task_body(task_body)
            
            # If no input path found, try to infer from task filename
            if not input_path:
                # Task filename format: YYYY-MM-DD {ABBR} - {input_filename}.md
                # Extract input filename from task filename
                task_filename = task_file_path.stem
                parts = task_filename.split(' - ', 1)
                if len(parts) > 1:
                    # Try to find a file matching the input filename
                    input_filename = parts[1]
                    # Search in common input directories
                    for input_dir in agent.input_path:
                        search_path = self.vault_path / input_dir
                        if search_path.exists():
                            # Look for matching file
                            for ext in ['.md', '.txt']:
                                candidate = search_path / f"{input_filename}{ext}"
                                if candidate.exists():
                                    input_path = str(candidate.relative_to(self.vault_path))
                                    break
                            if input_path:
                                break

            # Use task file path as fallback if no input found
            if not input_path:
                input_path = str(task_file_path.relative_to(self.vault_path))

            # Create synthetic trigger event data
            def make_json_serializable(obj):
                """Recursively convert date/datetime objects to ISO strings."""
                if isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: make_json_serializable(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [make_json_serializable(item) for item in obj]
                else:
                    return obj

            event_data = {
                'path': input_path,
                'event_type': 'manual_reprocess',
                'is_directory': False,
                'timestamp': self.config.user_now(),
                'frontmatter': {}
            }

            event_data_serializable = make_json_serializable(event_data)

            # Serialize trigger data (keep as JSON string, will be properly escaped in task_manager)
            trigger_data_json = json.dumps(event_data_serializable, ensure_ascii=False)

            # Add trigger_data_json to task file
            self.execution_manager.task_manager.update_task_status_with_trigger_data(
                task_file_path,
                "QUEUED",  # Keep status as QUEUED
                trigger_data_json
            )

            return trigger_data_json

        except Exception as e:
            logger.error(f"Error enriching QUEUED task with trigger data: {e}", exc_info=True)
            return None

    def _create_worker_agent_variant(self, base_agent: AgentDefinition, worker: WorkerConfig) -> AgentDefinition:
        """
        Create an agent variant with worker-specific settings.

        Args:
            base_agent: Base agent definition to copy
            worker: Worker configuration with executor and label

        Returns:
            New AgentDefinition with worker-specific settings
        """
        from dataclasses import replace

        # Create a copy with worker-specific overrides
        worker_abbr = f"{base_agent.abbreviation}-{worker.label}"

        # Merge agent_params: base agent params + worker-specific params
        merged_params = {**base_agent.agent_params, **worker.agent_params}

        # Modify output_naming to include worker label
        output_naming = base_agent.output_naming
        if '{agent}' in output_naming:
            # Replace {agent} pattern to include worker label
            output_naming = output_naming.replace('{agent}', f'{{agent}}-{worker.label}')
        else:
            # Append worker label to filename
            if output_naming.endswith('.md'):
                output_naming = output_naming[:-3] + f' - {worker.label}.md'
            else:
                output_naming = output_naming + f' - {worker.label}'

        return replace(
            base_agent,
            abbreviation=worker_abbr,
            executor=worker.executor,
            agent_params=merged_params,
            output_path=worker.output_path or base_agent.output_path,
            output_naming=output_naming,
            log_pattern='{timestamp}-{agent}.log',  # Agent abbr includes worker label
            workers=[]  # Clear workers list to prevent recursion
        )

    def get_status(self) -> dict:
        """
        Get current orchestrator status.

        Returns:
            Dictionary with status information
        """
        return {
            'running': self._running,
            'vault_path': str(self.vault_path),
            'agents_loaded': len(self.agent_registry.agents),
            'pollers_loaded': len(self.poller_manager.pollers),
            'running_executions': self.execution_manager.get_running_count(),
            'max_concurrent': self.max_concurrent,
            'agent_list': [
                {
                    'abbreviation': agent.abbreviation,
                    'name': agent.name,
                    'category': agent.category,
                    'running': self.execution_manager.get_agent_running_count(agent.abbreviation)
                }
                for agent in self.agent_registry.agents.values()
            ]
        }

    def trigger_agent_once(self, agent_abbreviation: str, session_id: Optional[str] = None, input_file: Optional[str] = None, agent_params_override: Optional[Dict] = None) -> Optional[ExecutionContext]:
        """
        Manually trigger an agent once (synchronously).

        Args:
            agent_abbreviation: Agent abbreviation (e.g., "GDR", "EIC")
            session_id: Optional session ID for tracking related executions
            input_file: Optional input file path to pass to the agent
            agent_params_override: Optional dict of agent_params to override (e.g., {'lookback_hours': 24})

        Returns:
            ExecutionContext if agent was found and executed, None otherwise
        """
        from datetime import datetime

        # Look up agent
        agent = self.agent_registry.agents.get(agent_abbreviation)
        if not agent:
            logger.error(f"Agent '{agent_abbreviation}' not found")
            return None

        # Apply runtime agent_params overrides (without mutating the registry copy)
        if agent_params_override:
            import copy
            agent = copy.copy(agent)
            agent.agent_params = {**agent.agent_params, **agent_params_override}

        logger.info(f"Manually triggering agent: {agent.abbreviation} ({agent.name})")

        # If no input_file given but agent has input_path, scan for matching files
        logger.debug(f"Scan guard: input_file={input_file!r}, input_path={agent.input_path!r}, requires_input_file={agent.requires_input_file!r}")
        if not input_file and agent.input_path and agent.requires_input_file:
            logger.info(f"Scanning {agent.input_path} for files matching {agent.abbreviation} criteria", console=True)
            return self._scan_and_trigger(agent, session_id=session_id)

        # Create TriggerEvent - use input_file if provided, otherwise manual trigger
        if input_file:
            from ..markdown_utils import read_frontmatter
            file_path = Path(input_file)
            # Resolve to absolute path if relative
            if not file_path.is_absolute():
                file_path = self.vault_path / file_path
            # Get relative path from vault root
            try:
                relative_path = str(file_path.relative_to(self.vault_path))
            except ValueError:
                relative_path = str(file_path)
            fm = read_frontmatter(file_path) if file_path.exists() else {}
            trigger_event = TriggerEvent(
                path=relative_path,
                event_type="created",
                is_directory=False,
                timestamp=self.config.user_now(),
                frontmatter=fm
            )
        else:
            trigger_event = TriggerEvent(
                path="",  # No file path for manual triggers
                event_type="manual",
                is_directory=False,
                timestamp=self.config.user_now(),
                frontmatter={}
            )

        # Convert to event data dict
        event_data = {
            'path': trigger_event.path,
            'event_type': trigger_event.event_type,
            'is_directory': trigger_event.is_directory,
            'timestamp': trigger_event.timestamp,
            'frontmatter': trigger_event.frontmatter,
            'session_id': session_id  # Add session_id to event_data
        }

        # Execute synchronously
        try:
            if agent.workers:
                # Multi-worker: execute each worker sequentially
                input_filename = Path(trigger_event.path).name if trigger_event.path else "manual"
                logger.info(f"Multi-worker agent: {agent.abbreviation} ({input_filename}) with {len(agent.workers)} workers", console=True)
                last_ctx = None
                all_success = True
                for worker in agent.workers:
                    worker_agent = self._create_worker_agent_variant(agent, worker)
                    logger.info(f"Running worker: {worker_agent.abbreviation}", console=True)
                    ctx = self._execute_agent(worker_agent, event_data, slot_reserved=False)
                    if ctx:
                        last_ctx = ctx
                        if not ctx.success:
                            all_success = False
                            logger.error(f"Worker {worker_agent.abbreviation} failed: {ctx.error_message}", console=True)
                    else:
                        all_success = False
                if last_ctx and all_success:
                    last_ctx.success = True
                return last_ctx
            else:
                ctx = self._execute_agent(agent, event_data, slot_reserved=False)
                return ctx
        except Exception as e:
            logger.error(f"Error executing agent {agent_abbreviation}: {e}", exc_info=True)
            # Surface the error message to the caller instead of silently returning None
            from .models import ExecutionContext
            err_ctx = ExecutionContext(agent=agent, trigger_data=event_data)
            err_ctx.status = 'failed'
            err_ctx.error_message = str(e)
            return err_ctx

    def _scan_and_trigger(self, agent: AgentDefinition, session_id: Optional[str] = None) -> Optional[ExecutionContext]:
        """
        Scan an agent's input directories for files matching its trigger criteria
        and trigger the agent for each matching file sequentially.

        Args:
            agent: Agent definition with input_path and optional trigger_content_pattern
            session_id: Optional session ID for tracking

        Returns:
            Last ExecutionContext from the batch, or None if no files matched
        """
        import re
        import fnmatch
        from ..markdown_utils import read_frontmatter

        matching_files: list[Path] = []
        input_pattern = agent.trigger_pattern or "*.md"
        patterns = [p.strip() for p in input_pattern.split('|')]

        for input_dir in agent.input_path:
            scan_dir = self.vault_path / input_dir
            if not scan_dir.exists():
                logger.debug(f"Scan directory does not exist: {scan_dir}")
                continue

            for file_path in sorted(scan_dir.glob("*.md")):
                if not file_path.is_file():
                    continue

                # Check filename pattern
                rel_path = str(file_path.relative_to(self.vault_path))
                if not any(fnmatch.fnmatch(rel_path, p) for p in patterns):
                    continue

                # Check exclusion pattern
                if agent.trigger_exclude_pattern:
                    exclude_patterns = [p.strip() for p in agent.trigger_exclude_pattern.split('|')]
                    if any(fnmatch.fnmatch(rel_path, p) for p in exclude_patterns):
                        continue

                # Check content pattern (e.g., status: todo)
                if agent.trigger_content_pattern:
                    try:
                        content = file_path.read_text(encoding='utf-8')
                        if not re.search(agent.trigger_content_pattern, content, re.IGNORECASE | re.MULTILINE):
                            continue
                    except Exception as e:
                        logger.debug(f"Error reading {file_path}: {e}")
                        continue

                matching_files.append(file_path)

        if not matching_files:
            logger.info(f"No matching files found for {agent.abbreviation} scan", console=True)
            return None

        logger.info(
            f"Found {len(matching_files)} file(s) matching {agent.abbreviation} criteria",
            console=True,
        )

        last_ctx = None
        for file_path in matching_files:
            rel_path = str(file_path.relative_to(self.vault_path))
            fm = read_frontmatter(file_path) if file_path.exists() else {}
            logger.info(f"  → Triggering {agent.abbreviation} for: {file_path.name}", console=True)

            event_data = {
                'path': rel_path,
                'event_type': 'created',
                'is_directory': False,
                'timestamp': self.config.user_now(),
                'frontmatter': fm,
                'session_id': session_id,
            }

            try:
                ctx = self._execute_agent(agent, event_data, slot_reserved=False)
                if ctx:
                    last_ctx = ctx
                    if not ctx.success:
                        logger.error(f"  ✗ {agent.abbreviation} failed for {file_path.name}: {ctx.error_message}", console=True)
                    else:
                        logger.info(f"  ✓ {agent.abbreviation} completed for {file_path.name}", console=True)
            except Exception as e:
                logger.error(f"  ✗ Error executing {agent.abbreviation} for {file_path.name}: {e}", console=True)

        return last_ctx

    def execute_prompt_with_session(self, prompt: str, system_prompt: str = None, system_prompt_file: Optional[Path] = None, append_system_prompt: str = None, append_system_prompt_file: Optional[Path] = None, session_id: Optional[str] = None) -> Optional[ExecutionContext]:
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

        Returns:
            ExecutionContext if execution succeeded, None otherwise
        """
        from datetime import datetime
        from .models import AgentDefinition

        # Create a temporary agent definition with the configured executor
        agent = AgentDefinition(
            name="One-time prompt",
            system_prompt=system_prompt,
            system_prompt_file=system_prompt_file,
            append_system_prompt=append_system_prompt,
            append_system_prompt_file=append_system_prompt_file,
            abbreviation="ONETIME",
            category="adhoc",
            trigger_pattern="",
            trigger_event="manual",
            prompt_body=prompt,
            executor=self.config.get("defaults.executor", "copilot_cli"),
            max_parallel=1,
            timeout_minutes=30,
            output_path="",
            output_type="new_file",
            task_create=False  # Don't create task files for one-time prompts
        )

        logger.info(f"Executing one-time prompt (session_id: {session_id or 'none'}, auto resume/create)")

        # Create event data with session_id
        event_data = {
            'path': "",
            'event_type': 'onetime_prompt',
            'is_directory': False,
            'timestamp': self.config.user_now(),
            'frontmatter': {},
            'session_id': session_id  # Add session_id to event_data
        }

        # Execute via _execute_agent (which will extract session_id and pass to execute)
        try:
            # Reserve slot first
            if not self.execution_manager.reserve_slot(agent):
                logger.error("Cannot execute: concurrency limit reached")
                return None

            # Execute via _execute_agent (which returns ctx)
            ctx = self._execute_agent(agent, event_data, slot_reserved=True)
            return ctx
        except Exception as e:
            logger.error(f"Error executing one-time prompt: {e}", exc_info=True)
            return None

    def run_forever(self):
        """
        Start orchestrator and run forever (until interrupted).

        Blocks until KeyboardInterrupt or stop() is called.
        """
        self.start()

        try:
            logger.info("Orchestrator running. Press Ctrl+C to stop.")
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()
