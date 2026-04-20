"""
Execution manager for orchestrator.

Manages concurrent execution of agent tasks without global semaphores.
Uses simple instance-level counter with threading lock.
"""
import threading
import subprocess
import time
import os
import shutil
import shlex
import platform
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

from .models import AgentDefinition, ExecutionContext
from ..logger import Logger

if TYPE_CHECKING:
    from ..config import Config

logger = Logger()
CLAUDE_CLI_PATH = shutil.which('claude') or 'claude'

class ExecutionManager:
    """
    Manages concurrent execution of agent tasks.

    Uses simple instance-level counter instead of global semaphores.
    Each agent can specify max_parallel limit.
    """

    def __init__(self, vault_path: Path, max_concurrent: int = 3, config: Optional['Config'] = None, orchestrator_settings: Optional[dict] = None, working_dir: Optional[Path] = None, mcp_config: Optional[tuple] = None, claude_settings: Optional[str] = None):
        """
        Initialize execution manager.

        Args:
            vault_path: Path to vault root
            max_concurrent: Maximum concurrent executions across all agents
            config: Config instance (will create default if None)
            orchestrator_settings: Orchestrator settings from YAML (optional)
            working_dir: Working directory for agent subprocess execution (defaults to vault_path)
            mcp_config: Optional tuple of MCP config JSON files or strings
            claude_settings: Optional path or JSON string for Claude --settings flag
        """
        from ..config import Config

        self.vault_path = Path(vault_path)
        self.working_dir = Path(working_dir) if working_dir else self.vault_path
        self.max_concurrent = max_concurrent
        self.config = config or Config(vault_path=self.vault_path)
        self.orchestrator_settings = orchestrator_settings or {}
        self.mcp_config = mcp_config
        self.claude_settings = claude_settings

        # Container isolation settings
        self._use_container_global = self.orchestrator_settings.get('use_container', False)
        self._container_config = self.orchestrator_settings.get('container', {})

        # Auto-discover MCP config if none provided
        if not self.mcp_config:
            self.mcp_config = self._auto_discover_mcp_config()

        # Instance-level state (no global state)
        self._running_count = 0
        self._count_lock = threading.Lock()

        # Track running executions
        self._running_executions: Dict[str, ExecutionContext] = {}
        self._executions_lock = threading.Lock()

        # Track per-agent running counts
        self._agent_counts: Dict[str, int] = {}
        self._agent_lock = threading.Lock()

        # Callback invoked (in a daemon thread) after an execution slot is freed.
        # Orchestrator registers _process_queued_tasks here so queued tasks
        # are drained immediately when capacity becomes available — not only
        # when the next file-system or cron event arrives.
        self._on_slot_freed: Optional[callable] = None

        # Task file manager (v2: daily execution logs)
        from .task_manager_v2 import TaskFileManagerV2
        self.task_manager = TaskFileManagerV2(vault_path, config=self.config, orchestrator_settings=orchestrator_settings)

    def _should_use_container(self, agent: AgentDefinition) -> bool:
        """Resolve whether this agent should run in a container.

        Per-agent `use_container` overrides the global setting.
        """
        if agent.use_container is not None:
            return agent.use_container
        return self._use_container_global

    def _auto_discover_mcp_config(self) -> Optional[tuple]:
        """Auto-discover MCP config from CLI's get_mcp_config and vault's .github/copilot/mcp.json."""
        from ..main.cli import get_mcp_config

        auto_mcp = get_mcp_config(self.vault_path)
        if auto_mcp:
            return (auto_mcp,)
        return None

    def can_execute(self, agent: AgentDefinition) -> bool:
        """
        Check if agent can execute given current load.

        Args:
            agent: Agent definition

        Returns:
            True if execution is allowed
        """
        with self._count_lock:
            # Check global limit
            if self._running_count >= self.max_concurrent:
                return False

        with self._agent_lock:
            # Check per-agent limit
            agent_count = self._agent_counts.get(agent.abbreviation, 0)
            if agent_count >= agent.max_parallel:
                return False

        return True

    def reserve_slot(self, agent: AgentDefinition) -> bool:
        """
        Atomically check if can execute and reserve a slot.

        This prevents race conditions where multiple threads check can_execute()
        before any of them increment the counters.

        Args:
            agent: Agent definition

        Returns:
            True if slot was reserved, False if at capacity
        """
        with self._count_lock:
            # Check global limit
            if self._running_count >= self.max_concurrent:
                return False

            # Reserve global slot immediately
            self._running_count += 1

        with self._agent_lock:
            # Check per-agent limit
            agent_count = self._agent_counts.get(agent.abbreviation, 0)
            if agent_count >= agent.max_parallel:
                # Release global slot since we can't reserve agent slot
                with self._count_lock:
                    self._running_count -= 1
                return False

            # Reserve agent slot immediately
            self._agent_counts[agent.abbreviation] = agent_count + 1

        return True

    def execute(self, agent: AgentDefinition, trigger_data: Dict, slot_reserved: bool = False, session_id: Optional[str] = None, resume_session: bool = False) -> ExecutionContext:
        """
        Execute an agent task.

        Args:
            agent: Agent definition to execute
            trigger_data: Data about the triggering event
            slot_reserved: If True, slot was already reserved by reserve_slot()
            session_id: Optional session ID for tracking related executions
            resume_session: If True, resume existing session; if False, create new session

        Returns:
            ExecutionContext with execution results
        """
        # Cross-process lock — prevents same agent running from multiple terminals
        from .agent_lock import acquire_agent_lock, release_agent_lock
        if not acquire_agent_lock(self.vault_path, agent.abbreviation):
            # Release pre-reserved slot if one was held by the caller
            if slot_reserved:
                with self._count_lock:
                    self._running_count -= 1
                with self._agent_lock:
                    self._agent_counts[agent.abbreviation] = max(0, self._agent_counts.get(agent.abbreviation, 1) - 1)

            ctx = ExecutionContext(
                agent=agent,
                trigger_data=trigger_data,
                start_time=self.config.user_now(),
                session_id=session_id,
                resume_session=resume_session,
            )
            ctx.status = 'skipped'
            ctx.error_message = f"Agent {agent.abbreviation} is already running in another process"
            logger.warning(ctx.error_message, console=True)
            return ctx

        ctx = ExecutionContext(
            agent=agent,
            trigger_data=trigger_data,
            start_time=self.config.user_now(),
            session_id=session_id,
            resume_session=resume_session,
            system_prompt=agent.system_prompt,
            system_prompt_file=agent.system_prompt_file,
            append_system_prompt=agent.append_system_prompt,
            append_system_prompt_file=agent.append_system_prompt_file
        )

        # Increment counters only if not already reserved
        if not slot_reserved:
            with self._count_lock:
                self._running_count += 1

            with self._agent_lock:
                self._agent_counts[agent.abbreviation] = self._agent_counts.get(agent.abbreviation, 0) + 1

        with self._executions_lock:
            self._running_executions[ctx.execution_id] = ctx

        # Prepare log file path BEFORE execution (needed for task file)
        log_path = self._prepare_log_path(agent, ctx)
        ctx.log_file = log_path

        existing_task_id = trigger_data.get('_existing_task_id')
        existing_task_path = trigger_data.get('_existing_task_file')
        if existing_task_id:
            # V2: reuse existing execution entry
            ctx.task_file = existing_task_id
            self.task_manager.update_task_status(existing_task_id, "IN_PROGRESS")
            logger.info(f"Using existing execution entry: [{existing_task_id}]", console=True)
        elif existing_task_path:
            # Legacy: reuse existing task file (Path)
            task_file = Path(existing_task_path)
            ctx.task_file = task_file
            self.task_manager.update_task_status(task_file, "IN_PROGRESS")
            logger.info(f"Using existing task file: {task_file.name}", console=True)
        else:
            # Create new execution entry
            task_handle = self.task_manager.create_task_file(ctx, agent)
            ctx.task_file = task_handle

        try:
            logger.debug(f"Starting execution: {agent.abbreviation} (ID: {ctx.execution_id})")

            # Execute based on executor type
            if agent.executor == 'copilot_cli':
                self._execute_copilot_cli(agent, ctx, trigger_data)
            elif agent.executor == 'claude_code':
                self._execute_claude_code(agent, ctx, trigger_data)
            elif agent.executor == 'copilot_sdk':
                self._execute_copilot_sdk(agent, ctx, trigger_data)
            else:
                raise ValueError(f"Unknown executor: {agent.executor}")

            ctx.status = 'completed'
            logger.info(f"Completed execution: {agent.abbreviation} (ID: {ctx.execution_id})")

        except subprocess.TimeoutExpired:
            ctx.status = 'timeout'
            ctx.error_message = f"{agent.abbreviation} timed out after {agent.timeout_minutes} minute(s)"
            logger.error(f"Timeout: {agent.abbreviation} (ID: {ctx.execution_id})")

        except Exception as e:
            ctx.status = 'failed'
            if not ctx.error_message:
                ctx.error_message = str(e)
            logger.error(f"Failed execution: {agent.abbreviation} (ID: {ctx.execution_id}): {e}")

        finally:
            ctx.end_time = self.config.user_now()

            # Log token usage summary to console
            if ctx.token_usage:
                total_in = sum(u.get('input_tokens', 0) for u in ctx.token_usage.values() if isinstance(u, dict))
                total_out = sum(u.get('output_tokens', 0) for u in ctx.token_usage.values() if isinstance(u, dict))
                if total_in or total_out:
                    logger.info(f"[{agent.abbreviation}] tokens: {total_in:,} in / {total_out:,} out ({total_in + total_out:,} total)")

            # Update execution log with final status
            if ctx.task_file:
                # Determine final status
                final_status = ctx.status
                output_link = None
                validation_error = None

                if ctx.status == 'completed' and 'path' in trigger_data:
                    # Use heuristic discovery for output validation
                    output_valid, output_link, validation_error = self._validate_output(
                        agent, trigger_data, ctx
                    )

                    if not output_valid:
                        final_status = 'failed'
                        ctx.error_message = validation_error
                    elif output_valid and output_link is None and agent.output_optional:
                        final_status = 'ignored'

                self.task_manager.update_task_status(
                    task_handle=ctx.task_file,
                    status="IGNORE" if final_status == 'ignored' else
                           "PROCESSED" if final_status == 'completed' else "FAILED",
                    output=output_link,
                    error_message=ctx.error_message
                )

            # Post-processing actions (e.g., remove trigger content)
            if ctx.status == 'completed' and agent.post_process_action:
                self._apply_post_processing(agent, trigger_data)

            # CRITICAL: Decrement counters FIRST — must always run even if logging fails.
            # This was the root cause of agents getting stuck as "running" forever:
            # if log writing crashed (e.g. ctx.task_file.name on a str), counters
            # were never decremented.
            try:
                with self._count_lock:
                    self._running_count = max(0, self._running_count - 1)

                with self._agent_lock:
                    if agent.abbreviation in self._agent_counts:
                        self._agent_counts[agent.abbreviation] = max(0, self._agent_counts[agent.abbreviation] - 1)

                with self._executions_lock:
                    self._running_executions.pop(ctx.execution_id, None)
            except Exception as cleanup_err:
                logger.error(f"Failed to release execution slot: {cleanup_err}")

            # Release cross-process lock
            release_agent_lock(self.vault_path, agent.abbreviation)

            # Detect WorkIQ permission errors and set flag for interactive re-auth
            # Use specific phrases to avoid false positives from agents just mentioning "workiq"
            agent_output = getattr(ctx, 'output', None) or ''
            if agent_output:
                output_lower = agent_output.lower()
                workiq_auth_phrases = [
                    'workiq auth expired',
                    'workiq-auth-expired',
                    'accept the eula',
                    'accept_eula',
                    'workiq re-authentication',
                    'workiq permission denied',
                    'workiq authentication required',
                    'eula url should be',
                ]
                if any(phrase in output_lower for phrase in workiq_auth_phrases):
                    self._set_workiq_auth_flag()

            # Log result to file (structured format: JSON metadata + raw output)
            # This runs AFTER counter cleanup so a logging crash can't leak slots.
            try:
                if ctx.log_file:
                    import json as _json
                    trigger_path = trigger_data.get('path', '')
                    input_file = Path(trigger_path).name if trigger_path else None
                    trigger_type = trigger_data.get('event_type', 'unknown')

                    metadata = {
                        "agent": agent.abbreviation,
                        "agent_name": agent.name,
                        "execution_id": ctx.execution_id,
                        "session_id": ctx.session_id,
                        "status": ctx.status,
                        "trigger_type": trigger_type,
                        "input_file": input_file,
                        "input_path": trigger_path,
                        "output_path": agent.output_path or None,
                        "executor": agent.executor,
                        "start_time": ctx.start_time.isoformat() if ctx.start_time else None,
                        "end_time": ctx.end_time.isoformat() if ctx.end_time else None,
                        "duration_seconds": round(ctx.duration, 1) if ctx.duration else None,
                        "error": ctx.error_message if ctx.error_message else None,
                        "task_file": str(ctx.task_file) if ctx.task_file else None,
                        "token_usage": ctx.token_usage if ctx.token_usage else None,
                    }

                    with open(ctx.log_file, 'w', encoding='utf-8') as f:
                        f.write("---\n")
                        f.write(_json.dumps(metadata, indent=2, default=str))
                        f.write("\n---\n\n")
                        f.write(f"# Execution Log: {agent.abbreviation}\n\n")
                        f.write("## Prompt Context\n\n")
                        f.write(f"- Agent prompt: `{agent.file_path.name if agent.file_path else agent.abbreviation}`\n")
                        prompt_text = ctx.prompt or ''
                        trigger_marker = '\n# Trigger Context\n'
                        trigger_idx = prompt_text.find(trigger_marker)
                        if trigger_idx >= 0:
                            f.write(f"\n```\n{prompt_text[trigger_idx:]}\n```\n\n")
                        else:
                            f.write("\n(no trigger context)\n\n")

                        # Token usage summary
                        if ctx.token_usage:
                            f.write("## Token Usage\n\n")
                            for model_id, usage in ctx.token_usage.items():
                                if model_id.startswith('_'):
                                    f.write(f"- {model_id[1:]}: {usage}\n")
                                elif isinstance(usage, dict):
                                    inp = usage.get('input_tokens', 0)
                                    out = usage.get('output_tokens', 0)
                                    cache_r = usage.get('cache_read_tokens', 0)
                                    reqs = usage.get('requests', 0)
                                    f.write(f"- **{model_id}**: {inp:,} in / {out:,} out")
                                    if cache_r:
                                        f.write(f" / {cache_r:,} cache-read")
                                    if reqs:
                                        f.write(f" ({reqs} requests)")
                                    f.write("\n")
                            f.write("\n")

                        f.write(f"## Response\n\n{ctx.response or '(no output)'}\n\n")
                        if ctx.error_message:
                            f.write(f"## Error\n\n```\n{ctx.error_message}\n```\n")

                    # Backfill log_path and token_usage in the task entry
                    if ctx.task_file:
                        try:
                            log_rel = str(ctx.log_file.relative_to(self.vault_path))
                        except ValueError:
                            log_rel = str(ctx.log_file)
                        updates = {'log_path': log_rel}
                        if ctx.token_usage:
                            # Flatten to a compact summary for the task entry
                            total_in = 0
                            total_out = 0
                            total_cache_read = 0
                            total_requests = 0
                            for k, v in ctx.token_usage.items():
                                if isinstance(v, dict):
                                    total_in += v.get('input_tokens', 0)
                                    total_out += v.get('output_tokens', 0)
                                    total_cache_read += v.get('cache_read_tokens', 0)
                                    total_requests += v.get('requests', 0)
                            updates['token_usage'] = {
                                'input_tokens': total_in,
                                'output_tokens': total_out,
                                'cache_read_tokens': total_cache_read,
                                'total_tokens': total_in + total_out,
                                'requests': total_requests,
                            }
                        self.task_manager.update_task_log_path(ctx.task_file, updates)
            except Exception as log_err:
                logger.error(f"Failed to write execution log: {log_err}")

            # Notify orchestrator that a slot freed up so queued tasks
            # can be drained immediately (runs in a short-lived daemon
            # thread to avoid blocking this execution thread).
            if self._on_slot_freed:
                try:
                    threading.Thread(
                        target=self._on_slot_freed,
                        daemon=True,
                        name=f"drain-queue-{agent.abbreviation}",
                    ).start()
                except Exception:
                    pass  # Best-effort; event loop will also drain on next tick

        return ctx

    def _set_workiq_auth_flag(self):
        """Set a flag indicating WorkIQ needs re-authentication."""
        from ..config import get_global_runtime_dir
        vault_id = self.config.get("id", "default")
        flag_dir = get_global_runtime_dir(vault_id, vault_path=self.vault_path) / "state"
        flag_dir.mkdir(parents=True, exist_ok=True)
        flag_file = flag_dir / "workiq-auth-expired"
        flag_file.write_text("WorkIQ permission denied detected. Re-accept EULA in interactive session.", encoding='utf-8')
        logger.warning("⚠️ WorkIQ auth expired — run `duckyai` interactively to re-authenticate", console=True)

    @staticmethod
    def check_workiq_auth_flag(vault_id: str = "default", vault_path: Path = None) -> bool:
        """Check if the WorkIQ auth expired flag is set."""
        from ..config import get_global_runtime_dir
        flag_file = get_global_runtime_dir(vault_id, vault_path=vault_path) / "state" / "workiq-auth-expired"
        return flag_file.exists()

    @staticmethod
    def clear_workiq_auth_flag(vault_id: str = "default", vault_path: Path = None):
        """Clear the WorkIQ auth expired flag after re-authentication."""
        from ..config import get_global_runtime_dir
        flag_file = get_global_runtime_dir(vault_id, vault_path=vault_path) / "state" / "workiq-auth-expired"
        flag_file.unlink(missing_ok=True)

    def _execute_claude_code(self, agent: AgentDefinition, ctx: ExecutionContext, trigger_data: Dict):
        """
        Execute agent using Claude Code CLI.

        Args:
            agent: Agent definition
            ctx: Execution context
            trigger_data: Trigger event data
        """
        # For one-time prompts, use just the prompt body without any context
        if trigger_data.get('event_type') == 'onetime_prompt':
            ctx.prompt = agent.prompt_body
        else:
            # Build prompt from agent definition with full context
            ctx.prompt = self._build_prompt(agent, trigger_data, ctx)
        
        # Build command with optional session ID (prompt will be passed via stdin)
        cmd = [CLAUDE_CLI_PATH, '--permission-mode', 'bypassPermissions', '--print']
        
        if ctx.system_prompt_file:
            cmd.extend(['--system-prompt-file', str(ctx.system_prompt_file)])
        
        # Add system prompt if provided
        if ctx.system_prompt:
            cmd.extend(['--system-prompt', ctx.system_prompt])
        
        # Add append system prompt file if provided
        if ctx.append_system_prompt_file:
            cmd.extend(['--append-system-prompt-file', str(ctx.append_system_prompt_file)])
        
        # Add append system prompt if provided
        if ctx.append_system_prompt:
            cmd.extend(['--append-system-prompt', ctx.append_system_prompt])
        
        # Add MCP config(s) if provided
        if self.mcp_config:
            for config in self.mcp_config:
                cmd.extend(['--mcp-config', config])

        # Add Claude settings if provided
        if self.claude_settings:
            cmd.extend(['--settings', self.claude_settings])

        # Add session ID handling: try to create new first, resume if already exists
        if ctx.session_id:
            # First try to create new session with --session-id
            # If it fails because session exists, we'll catch and retry with --resume
            cmd.extend(['--session-id', ctx.session_id])
        
        use_container = self._should_use_container(agent)

        try:
            self._execute_subprocess(ctx, 'Claude CLI', cmd, agent.timeout_minutes * 60, stdin_input=ctx.prompt, use_container=use_container, agent=agent)
        except RuntimeError as e:
            # Check if error is about session already existing
            error_msg = str(e)
            # Check both the error message and ctx.error_message (set by _execute_subprocess)
            full_error = f"{error_msg} {ctx.error_message or ''}"
            if ctx.session_id and ("already in use" in full_error.lower() or "already exists" in full_error.lower()):
                # Session exists, retry with --resume
                logger.info(f"Session {ctx.session_id} already exists, resuming...")
                # Clear previous error
                ctx.error_message = None
                cmd_resume = [CLAUDE_CLI_PATH, '--permission-mode', 'bypassPermissions', '--print', '--resume', ctx.session_id]
                if ctx.system_prompt_file:
                    cmd_resume.extend(['--system-prompt-file', str(ctx.system_prompt_file)])
                # Add system prompt to resume command
                if ctx.system_prompt:
                    cmd_resume.extend(['--system-prompt', ctx.system_prompt])
                # Add append system prompt file to resume command
                if ctx.append_system_prompt_file:
                    cmd_resume.extend(['--append-system-prompt-file', str(ctx.append_system_prompt_file)])
                # Add append system prompt to resume command
                if ctx.append_system_prompt:
                    cmd_resume.extend(['--append-system-prompt', ctx.append_system_prompt])
                # Add MCP config(s) to resume command
                if self.mcp_config:
                    for config in self.mcp_config:
                        cmd_resume.extend(['--mcp-config', config])
                # Add Claude settings to resume command
                if self.claude_settings:
                    cmd_resume.extend(['--settings', self.claude_settings])
                self._execute_subprocess(ctx, 'Claude CLI', cmd_resume, agent.timeout_minutes * 60, stdin_input=ctx.prompt, use_container=use_container, agent=agent)
            else:
                # Re-raise if it's a different error
                raise

    def _execute_copilot_sdk(self, agent: AgentDefinition, ctx: ExecutionContext, trigger_data: Dict):
        """
        Execute agent using the GitHub Copilot SDK (Python).

        Uses a runner script (scripts/copilot_sdk_runner.py) on Python 3.10+
        that invokes the Copilot SDK programmatically via JSON-RPC.
        """
        if trigger_data.get('event_type') == 'onetime_prompt':
            ctx.prompt = agent.prompt_body
        else:
            ctx.prompt = self._build_prompt(agent, trigger_data, ctx)

        # Find the runner script — check CLI package first, then vault
        cli_runner = Path(__file__).parent.parent / 'scripts' / 'copilot_sdk_runner.py'
        vault_runner = self.vault_path / 'scripts' / 'copilot_sdk_runner.py'
        runner_script = cli_runner if cli_runner.exists() else vault_runner
        if not runner_script.exists():
            raise FileNotFoundError(f"Copilot SDK runner not found: {runner_script}")

        use_container = self._should_use_container(agent)

        if use_container:
            # In container mode, use a shell wrapper to resolve the runner path
            # since the Docker image may use either /app/duckyai/ (new) or
            # /app/duckyai_cli/ (legacy pre-rename).
            cwd_path = self._container_config.get('vault_mount', '/vault')
            runner_resolve = (
                'RUNNER=/app/duckyai/scripts/copilot_sdk_runner.py; '
                '[ -f "$RUNNER" ] || RUNNER=/app/duckyai_cli/scripts/copilot_sdk_runner.py; '
            )
            # Build the inner python command args
            inner_args = ['python3', '"$RUNNER"', '--prompt', shlex.quote(ctx.prompt), '--cwd', cwd_path]

            if agent.agent_params and agent.agent_params.get('model'):
                inner_args.extend(['--model', agent.agent_params['model']])

            if self.mcp_config:
                for config in self.mcp_config:
                    config = self._adapt_mcp_config_for_container(config)
                    inner_args.extend(['--mcp-config', shlex.quote(config)])

            shell_cmd = runner_resolve + ' '.join(inner_args)
            cmd = ['sh', '-c', shell_cmd]
            self._execute_subprocess(ctx, 'Copilot SDK', cmd, agent.timeout_minutes * 60, use_container=use_container, agent=agent)
            return
        else:
            # Find Python 3.10+ for the SDK (requires union type syntax)
            sdk_python = self._find_sdk_python()
            runner_path = str(runner_script)
            cwd_path = str(self.working_dir)

        cmd = [sdk_python, runner_path, '--prompt', ctx.prompt, '--cwd', cwd_path]

        # Model selection
        if agent.agent_params and agent.agent_params.get('model'):
            cmd.extend(['--model', agent.agent_params['model']])

        # MCP config
        if self.mcp_config:
            for config in self.mcp_config:
                cmd.extend(['--mcp-config', config])

        self._execute_subprocess(ctx, 'Copilot SDK', cmd, agent.timeout_minutes * 60, use_container=use_container, agent=agent)

    def _adapt_mcp_config_for_container(self, config_json: str) -> str:
        """Translate MCP config for container execution.

        Replaces host vault paths with container mount paths in env vars
        and command arguments so MCP servers resolve correctly inside
        the container.
        """
        import json as _json
        try:
            config = _json.loads(config_json)
        except (_json.JSONDecodeError, TypeError):
            return config_json

        vault_mount = self._container_config.get('vault_mount', '/vault')
        vault_str = str(self.vault_path)
        vault_str_fwd = vault_str.replace('\\', '/')

        servers = config.get('mcpServers', {})
        for name, server in list(servers.items()):
            # Translate env vars that contain host vault paths
            env = server.get('env', {})
            for key, val in env.items():
                if isinstance(val, str):
                    val = val.replace(vault_str, vault_mount)
                    if vault_str_fwd != vault_str:
                        val = val.replace(vault_str_fwd, vault_mount)
                    env[key] = val

            # Translate args that contain host vault paths
            args = server.get('args', [])
            for i, arg in enumerate(args):
                if isinstance(arg, str):
                    arg = arg.replace(vault_str, vault_mount)
                    if vault_str_fwd != vault_str:
                        arg = arg.replace(vault_str_fwd, vault_mount)
                    args[i] = arg

        return _json.dumps(config)

    @staticmethod
    def _find_sdk_python() -> str:
        """Find a Python 3.10+ interpreter for the Copilot SDK."""
        from ..main.install_health import find_copilot_sdk_python

        return find_copilot_sdk_python()

    @staticmethod
    def _resolve_copilot_node_cmd():
        """
        Resolve the Copilot CLI as a direct Node.js invocation, bypassing copilot.exe.

        Returns ['node', '--no-warnings', '<path>/index.js'] or falls back to ['copilot'].
        """
        pkg_dir = Path.home() / ".copilot" / "pkg" / "universal"
        if pkg_dir.exists():
            versions = sorted(pkg_dir.iterdir(), key=lambda p: p.name, reverse=True)
            for v in versions:
                entry = v / "index.js"
                if entry.exists():
                    node = shutil.which("node")
                    if node:
                        return [node, '--no-warnings', str(entry)]
        # Fallback to copilot.exe
        return ['copilot']

    def _execute_copilot_cli(self, agent: AgentDefinition, ctx: ExecutionContext, trigger_data: Dict):
        """
        Execute agent using GitHub Copilot CLI.

        Invokes Node.js directly with --no-warnings to bypass copilot.exe's
        intermittent arg-routing bug. Falls back to copilot.exe if needed.
        """
        if trigger_data.get('event_type') == 'onetime_prompt':
            ctx.prompt = agent.prompt_body
        else:
            ctx.prompt = self._build_prompt(agent, trigger_data, ctx)

        base_cmd = self._resolve_copilot_node_cmd()
        cmd = base_cmd + ['--prompt', ctx.prompt, '--allow-all-tools', '--output-format', 'text']

        # Model selection from agent_params
        if agent.agent_params and agent.agent_params.get('model'):
            cmd.extend(['--model', agent.agent_params['model']])

        # MCP configs
        if self.mcp_config:
            for config in self.mcp_config:
                cmd.extend(['--additional-mcp-config', config])

        # Session handling
        if ctx.session_id:
            cmd.extend(['--session-id', ctx.session_id])

        use_container = self._should_use_container(agent)

        try:
            self._execute_subprocess(ctx, 'GitHub Copilot CLI', cmd, agent.timeout_minutes * 60, use_container=use_container, agent=agent)
        except RuntimeError as e:
            error_msg = str(e)
            full_error = f"{error_msg} {ctx.error_message or ''}"
            if ctx.session_id and "already" in full_error.lower():
                logger.info(f"Session {ctx.session_id} exists, resuming...")
                ctx.error_message = None
                cmd_resume = base_cmd + ['--resume', ctx.session_id, '--prompt', ctx.prompt,
                              '--allow-all-tools', '--output-format', 'text']
                if agent.agent_params and agent.agent_params.get('model'):
                    cmd_resume.extend(['--model', agent.agent_params['model']])
                if self.mcp_config:
                    for config in self.mcp_config:
                        cmd_resume.extend(['--additional-mcp-config', config])
                self._execute_subprocess(ctx, 'GitHub Copilot CLI', cmd_resume, agent.timeout_minutes * 60, use_container=use_container, agent=agent)
            else:
                raise

    @staticmethod
    def _get_copilot_token() -> Optional[str]:
        """Extract the Copilot CLI OAuth token from the platform credential store."""
        # Check environment first
        token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
        if token:
            return token

        if platform.system() != 'Windows':
            return None

        try:
            import ctypes
            import ctypes.wintypes as w

            advapi32 = ctypes.windll.advapi32
            fields = [
                ('Flags', w.DWORD), ('Type', w.DWORD), ('TargetName', w.LPWSTR),
                ('Comment', w.LPWSTR), ('LastWritten', w.FILETIME),
                ('CredentialBlobSize', w.DWORD), ('CredentialBlob', ctypes.POINTER(ctypes.c_byte)),
                ('Persist', w.DWORD), ('AttributeCount', w.DWORD), ('Attributes', ctypes.c_void_p),
                ('TargetAlias', w.LPWSTR), ('UserName', w.LPWSTR),
            ]
            CREDENTIAL = type('CREDENTIAL', (ctypes.Structure,), {'_fields_': fields})

            # Read copilot-cli config to find the logged-in user
            config_path = Path.home() / '.copilot' / 'config.json'
            target_suffix = ''
            if config_path.exists():
                import json
                cfg = json.loads(config_path.read_text(encoding='utf-8'))
                user_info = cfg.get('last_logged_in_user', {})
                host = user_info.get('host', 'https://github.com')
                login = user_info.get('login', '')
                if login:
                    target_suffix = f'{host}:{login}'

            # Try specific user target first, then generic
            targets = []
            if target_suffix:
                targets.append(f'copilot-cli/{target_suffix}')
            targets.append('copilot-cli/https://github.com')

            for target in targets:
                pcred = ctypes.POINTER(CREDENTIAL)()
                if advapi32.CredReadW(target, 1, 0, ctypes.byref(pcred)):
                    cred = pcred.contents
                    blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
                    advapi32.CredFree(pcred)
                    return blob.decode('utf-8', errors='replace')

        except Exception as e:
            logger.debug(f"Could not read Copilot credential: {e}")

        return None

    @staticmethod
    def _get_azure_access_token() -> Optional[str]:
        """Extract an Azure DevOps access token from the host's Azure CLI.

        On Windows the MSAL token cache is DPAPI-encrypted and cannot be
        decrypted inside a Linux container.  This method calls
        ``az account get-access-token`` on the **host** to obtain a fresh
        token which is then forwarded to the container via env var.
        """
        # Check environment first
        token = os.environ.get('AZURE_DEVOPS_EXT_PAT')
        if token:
            return token

        az_bin = shutil.which('az')
        if not az_bin:
            # Common Azure CLI install location on Windows
            candidate = Path(os.environ.get('ProgramFiles', '')) / 'Microsoft SDKs' / 'Azure' / 'CLI2' / 'wbin' / 'az.cmd'
            if candidate.exists():
                az_bin = str(candidate)
        if not az_bin:
            return None

        try:
            # Azure DevOps resource ID
            result = subprocess.run(
                [az_bin, 'account', 'get-access-token',
                 '--resource', '499b84ac-1321-427f-aa17-267ca6975798',
                 '--query', 'accessToken', '-o', 'tsv'],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Could not get Azure DevOps token: {e}")

        return None

    def _build_docker_cmd(self, cmd: List[str], env: Optional[Dict] = None, agent: Optional['AgentDefinition'] = None) -> List[str]:
        """
        Wrap a command in `docker run` for container-isolated execution.

        Maps host vault path to /vault inside the container, mounts auth
        directories read-only, and translates any host vault paths in the
        command arguments to their container equivalents.

        Args:
            cmd: Original command list (e.g., ['claude', '--print', ...])
            env: Optional environment variables to pass via -e flags
            agent: Optional agent definition for per-agent extra_mounts

        Returns:
            Wrapped command: ['docker', 'run', '--rm', '-i', '-v', ..., 'image', ...]
        """
        image = self._container_config.get('image', 'duckyai-agent:latest')
        vault_mount = self._container_config.get('vault_mount', '/vault')
        extra_mounts = list(self._container_config.get('extra_mounts', []))

        # Merge per-agent extra_mounts
        if agent and hasattr(agent, 'extra_mounts') and agent.extra_mounts:
            extra_mounts.extend(agent.extra_mounts)

        # Resolve ${services_path} and ${repo_cache} placeholders in mount sources
        if extra_mounts:
            try:
                from ..services import get_services_path
                services_path_str = str(get_services_path(self.vault_path))
            except Exception:
                services_path_str = None

            repo_cache_path = self.vault_path / '.duckyai' / 'repo-cache'
            repo_cache_path.mkdir(parents=True, exist_ok=True)
            repo_cache_str = str(repo_cache_path)

            for mount in extra_mounts:
                src = mount.get('source', '')
                if '${services_path}' in src:
                    if services_path_str:
                        mount['source'] = src.replace('${services_path}', services_path_str)
                    else:
                        logger.warning(f"Cannot resolve ${{services_path}} for mount: {mount}")
                        mount['source'] = ''  # Will be skipped below
                if '${repo_cache}' in src:
                    mount['source'] = src.replace('${repo_cache}', repo_cache_str)

        # Resolve docker CLI path (may not be in PATH on Windows)
        docker_bin = shutil.which('docker')
        if not docker_bin:
            # Common Docker Desktop install locations
            for candidate in [
                Path(os.environ.get('ProgramFiles', '')) / 'Docker' / 'Docker' / 'resources' / 'bin' / 'docker.exe',
                Path.home() / '.docker' / 'bin' / 'docker',
            ]:
                if candidate.exists():
                    docker_bin = str(candidate)
                    break
        if not docker_bin:
            raise FileNotFoundError(
                "Docker CLI not found. Install Docker Desktop or add docker to PATH. "
                "To run agents locally instead, set orchestrator.use_container: false in duckyai.yml"
            )

        docker_cmd = [
            docker_bin, 'run', '--rm', '-i',
            '-v', f'{self.vault_path}:{vault_mount}',
            '-w', vault_mount,
        ]

        # Auth credential mounts — always included regardless of extra_mounts.
        # .azure is read-only (DPAPI cache can't be decrypted in Linux but
        # az login --identity and service principal auth still work).
        home = Path.home()
        auth_mounts = [
            (home / '.copilot', '/root/.copilot', False),  # SDK needs write for session-store.db
            (home / '.claude', '/root/.claude', True),
            (home / '.azure', '/root/.azure', True),
        ]
        for source, target, readonly in auth_mounts:
            if source.exists():
                mount_spec = f'{source}:{target}:ro' if readonly else f'{source}:{target}'
                docker_cmd.extend(['-v', mount_spec])

        # Extra mounts (per-agent or global)
        if extra_mounts:
            for mount in extra_mounts:
                source = Path(mount['source']).expanduser()
                target = mount['target']
                if source.exists():
                    readonly = mount.get('readonly', False)
                    mount_spec = f'{source}:{target}:ro' if readonly else f'{source}:{target}'
                    docker_cmd.extend(['-v', mount_spec])

        # Pass environment variables
        if env:
            for key, value in env.items():
                docker_cmd.extend(['-e', f'{key}={value}'])

        # Always pass DUCKYAI_VAULT_ROOT pointing to vault mount
        docker_cmd.extend(['-e', f'DUCKYAI_VAULT_ROOT={vault_mount}'])

        # Forward GitHub token for Copilot SDK authentication
        github_token = self._get_copilot_token()
        if github_token:
            docker_cmd.extend(['-e', f'GITHUB_TOKEN={github_token}'])

        # Forward Azure DevOps access token (DPAPI-encrypted cache can't be read in Linux)
        azdo_token = self._get_azure_access_token()
        if azdo_token:
            docker_cmd.extend(['-e', f'AZURE_DEVOPS_EXT_PAT={azdo_token}'])

        docker_cmd.append(image)

        # Translate host vault paths in command arguments to container paths
        vault_str = str(self.vault_path)
        # Normalize both forward and backslash variants
        vault_str_fwd = vault_str.replace('\\', '/')
        translated_cmd = []
        for arg in cmd:
            new_arg = arg.replace(vault_str, vault_mount)
            if vault_str_fwd != vault_str:
                new_arg = new_arg.replace(vault_str_fwd, vault_mount)
            translated_cmd.append(new_arg)

        docker_cmd.extend(translated_cmd)
        return docker_cmd

    def _execute_subprocess(self, ctx: ExecutionContext, agent_name: str, cmd: List[str], timeout_seconds: int, stdin_input: Optional[str] = None, env: Optional[Dict] = None, use_container: Optional[bool] = None, agent: Optional['AgentDefinition'] = None):
        # Resolve container flag: explicit param > global default
        if use_container is None:
            use_container = self._use_container_global

        # Wrap in Docker container if container mode is enabled
        if use_container:
            cmd = self._build_docker_cmd(cmd, env=env, agent=agent)
            env = None  # env vars are passed via -e flags in docker cmd
            logger.info(f"[{agent_name}] Running in container: {self._container_config.get('image', 'duckyai-agent:latest')}")
        elif platform.system() == 'Windows' and cmd:
            # On Windows (local mode), resolve .cmd/.bat files to their full paths
            executable = cmd[0]
            # Try to find the executable (handles .cmd, .bat, .exe)
            resolved = shutil.which(executable)
            if resolved:
                # Use the resolved full path
                cmd = [resolved] + cmd[1:]
            elif not os.path.splitext(executable)[1]:  # No extension
                # Try .cmd extension explicitly
                cmd_cmd = executable + '.cmd'
                resolved_cmd = shutil.which(cmd_cmd)
                if resolved_cmd:
                    cmd = [resolved_cmd] + cmd[1:]

        cwd = None if use_container else str(self.working_dir)
        logger.info(f"[{agent_name}] Executing{' in container' if use_container else f' in cwd={self.working_dir}'}")

        completed = subprocess.run(
            cmd,
            input=stdin_input,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=cwd,
            env=env,
            timeout=timeout_seconds,
        )

        combined_output_parts = []
        if completed.stdout:
            combined_output_parts.append(completed.stdout)
        if completed.stderr:
            combined_output_parts.append(completed.stderr)
        combined_output = "\n".join(part.rstrip() for part in combined_output_parts if part).strip()

        # Auto-start Docker Desktop on connection failure and retry once
        if use_container and completed.returncode != 0 and 'dockerDesktopLinuxEngine' in combined_output:
            logger.info(f"[{agent_name}] Docker not running — starting Docker Desktop and retrying...", console=True)
            if self._ensure_docker_running():
                completed = subprocess.run(
                    cmd,
                    input=stdin_input,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    cwd=cwd,
                    env=env,
                    timeout=timeout_seconds,
                )
                combined_output_parts = []
                if completed.stdout:
                    combined_output_parts.append(completed.stdout)
                if completed.stderr:
                    combined_output_parts.append(completed.stderr)
                combined_output = "\n".join(part.rstrip() for part in combined_output_parts if part).strip()

        logs = [f"[{agent_name}] {line}" for line in combined_output.splitlines() if line.strip()]
        for line in logs:
            logger.info(line)

        if completed.returncode != 0:
            error_detail = "\n".join(logs) if logs else f"Process exited with code {completed.returncode} (no output captured)"
            ctx.error_message = error_detail
            raise RuntimeError(f"{agent_name} execution failed (exit code {completed.returncode}): {error_detail[:500]}")

        ctx.response = combined_output

        # Extract token_usage from __COPILOT_SDK_RESULT__ and strip the marker from response
        sdk_marker = '__COPILOT_SDK_RESULT__'
        if sdk_marker in combined_output:
            try:
                import json as _json
                marker_idx = combined_output.rindex(sdk_marker)
                json_str = combined_output[marker_idx + len(sdk_marker):].strip()
                nl = json_str.find('\n')
                if nl >= 0:
                    json_str = json_str[:nl]
                sdk_result = _json.loads(json_str)
                if 'token_usage' in sdk_result and sdk_result['token_usage']:
                    ctx.token_usage = sdk_result['token_usage']
                # Strip the __COPILOT_SDK_RESULT__ line from the stored response
                ctx.response = combined_output[:marker_idx].rstrip()
            except (ValueError, _json.JSONDecodeError):
                pass  # Best-effort extraction

    def _ensure_docker_running(self, timeout: int = 90) -> bool:
        """Start Docker Desktop and wait until the Docker daemon is responsive.

        Returns True if Docker became reachable within the timeout.
        """
        import time

        # Try to start Docker Desktop (Windows)
        docker_desktop_paths = [
            os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"),
        ]
        started = False
        for path in docker_desktop_paths:
            if os.path.exists(path):
                try:
                    subprocess.Popen(
                        [path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.DETACHED_PROCESS if platform.system() == 'Windows' else 0,
                    )
                    started = True
                    logger.info(f"Launched Docker Desktop: {path}", console=True)
                    break
                except Exception as e:
                    logger.warning(f"Failed to launch Docker Desktop from {path}: {e}")

        if not started:
            logger.error("Could not find Docker Desktop executable")
            return False

        # Poll docker info until it responds
        deadline = time.monotonic() + timeout
        interval = 3
        while time.monotonic() < deadline:
            time.sleep(interval)
            try:
                result = subprocess.run(
                    ["docker", "info"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    logger.info("Docker Desktop is ready", console=True)
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
            remaining = int(deadline - time.monotonic())
            if remaining > 0:
                logger.info(f"Waiting for Docker Desktop... ({remaining}s remaining)")

        logger.error(f"Docker Desktop did not become ready within {timeout}s")
        return False

    def _build_scan_services(self) -> List[Dict]:
        """Build scan_services list for the PRS agent.

        Reads services.entries from duckyai.yml, filters by pr_scan: true.
        Uses metadata (org/project/repositories) when available.
        Falls back to scanning git remotes from disk if no metadata.

        Returns:
            List of dicts: [{"name": "DEPA", "repos": [{"name": "repo", "org": "...", "project": "...", "repo": "..."}]}]
        """
        import re

        services_config = self.config.get("services", {})
        entries = services_config.get("entries", [])
        opted_in = [e for e in entries if e.get("pr_scan", False)]
        if not opted_in:
            return []

        try:
            from ..services import get_services_path
            services_path = get_services_path(self.vault_path)
        except Exception:
            services_path = None

        result = []

        for entry in opted_in:
            svc_name = entry.get("name", "")
            metadata = entry.get("metadata", {})

            # Metadata-first: use org/project/repositories from config
            if metadata.get("type") == "ado" and metadata.get("organization") and metadata.get("project"):
                org = metadata["organization"]
                project = metadata["project"]
                repo_patterns = metadata.get("repositories", ["*"])
                repos = []
                for pattern in repo_patterns:
                    repos.append({
                        "name": pattern,
                        "org": org,
                        "project": project,
                        "repo": pattern,
                    })
                if repos:
                    result.append({"name": svc_name, "repos": repos})
                continue

            # Fallback: scan git remotes from disk
            if not services_path:
                continue
            svc_dir = services_path / svc_name
            if not svc_dir.is_dir():
                continue

            azdo_pattern = re.compile(
                r'https://(?:dev\.azure\.com/([^/]+)/([^/]+)|([^.]+)\.visualstudio\.com/([^/]+))/_git/([^/\s]+)'
            )
            repos = []
            for repo_dir in sorted(svc_dir.iterdir()):
                if not repo_dir.is_dir() or not (repo_dir / '.git').exists():
                    continue
                try:
                    import subprocess as _sp
                    result_proc = _sp.run(
                        ['git', '-C', str(repo_dir), 'remote', 'get-url', 'origin'],
                        capture_output=True, text=True, timeout=5
                    )
                    remote_url = result_proc.stdout.strip()
                    if not remote_url:
                        continue
                    m = azdo_pattern.search(remote_url)
                    if m:
                        org = m.group(1) or m.group(3)
                        project = m.group(2) or m.group(4)
                        repo_name = m.group(5)
                        repos.append({
                            "name": repo_dir.name,
                            "remote_url": remote_url,
                            "org": org,
                            "project": project,
                            "repo": repo_name,
                        })
                except Exception:
                    continue

            if repos:
                result.append({"name": svc_name, "repos": repos})

        return result

    def _prefetch_pr_list(self, scan_services: List[Dict]) -> List[Dict]:
        """Pre-fetch active non-draft PRs assigned to the user on the host.

        Runs ``az repos pr list`` per repo on the host, filters out drafts,
        and returns a flat list of PR dicts. This is deterministic — no LLM
        needed for the fetch + filter step.

        Args:
            scan_services: Output of ``_build_scan_services()``.

        Returns:
            List of PR dicts with keys: pr_id, title, author, org, project,
            repo, source_branch, target_branch, url, is_draft, reviewers.
        """
        import json as _json
        import fnmatch

        az_bin = shutil.which('az')
        if not az_bin:
            candidate = Path(os.environ.get('ProgramFiles', '')) / 'Microsoft SDKs' / 'Azure' / 'CLI2' / 'wbin' / 'az.cmd'
            if candidate.exists():
                az_bin = str(candidate)
        if not az_bin:
            logger.warning("[PRS] az CLI not found on host — skipping prefetch")
            return []

        user_name = self.config.get_user_name()
        all_prs: List[Dict] = []

        for svc in scan_services:
            svc_name = svc.get("name", "")
            for repo_entry in svc.get("repos", []):
                org = repo_entry.get("org", "")
                project = repo_entry.get("project", "")
                repo_pattern = repo_entry.get("repo", "")

                if not org or not project:
                    continue

                # Resolve glob patterns (e.g., "*", "ServiceLinker*") to actual repo names
                if '*' in repo_pattern or '?' in repo_pattern:
                    repos_to_scan = self._resolve_repo_pattern(az_bin, org, project, repo_pattern)
                else:
                    repos_to_scan = [repo_pattern]

                for repo_name in repos_to_scan:
                    prs = self._fetch_prs_for_repo(az_bin, org, project, repo_name, user_name)
                    for pr in prs:
                        pr["_service"] = svc_name
                    all_prs.extend(prs)

        logger.info(f"[PRS] Pre-fetched {len(all_prs)} active non-draft PRs across {sum(len(s.get('repos', [])) for s in scan_services)} repo patterns")
        return all_prs

    def _resolve_repo_pattern(self, az_bin: str, org: str, project: str, pattern: str) -> List[str]:
        """Resolve a glob repo pattern to actual repo names via az repos list."""
        import json as _json
        import fnmatch

        try:
            result = subprocess.run(
                [az_bin, 'repos', 'list',
                 '--org', f'https://dev.azure.com/{org}',
                 '--project', project,
                 '--output', 'json'],
                capture_output=True, text=True, timeout=30,
            )
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.warning(f"[PRS] az repos list failed for {org}/{project}: {e}")
            return []

        if result.returncode != 0:
            logger.warning(f"[PRS] az repos list returned {result.returncode} for {org}/{project}")
            return []

        try:
            repos = _json.loads(result.stdout)
        except _json.JSONDecodeError:
            return []

        return [r["name"] for r in repos if fnmatch.fnmatch(r.get("name", ""), pattern)]

    def _fetch_prs_for_repo(self, az_bin: str, org: str, project: str, repo: str, user_name: str) -> List[Dict]:
        """Fetch active non-draft PRs for a single repo where user is a reviewer."""
        import json as _json

        try:
            result = subprocess.run(
                [az_bin, 'repos', 'pr', 'list',
                 '--repository', repo,
                 '--project', project,
                 '--org', f'https://dev.azure.com/{org}',
                 '--status', 'active',
                 '--output', 'json'],
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"[PRS] az repos pr list timed out for {org}/{project}/{repo}")
            return []
        except Exception as e:
            logger.warning(f"[PRS] az repos pr list failed for {org}/{project}/{repo}: {e}")
            return []

        if result.returncode != 0:
            stderr = result.stderr.strip()[:200]
            logger.warning(f"[PRS] az repos pr list error for {org}/{project}/{repo}: {stderr}")
            return []

        try:
            prs_json = _json.loads(result.stdout)
        except _json.JSONDecodeError:
            return []

        def _strip_refs(ref: str) -> str:
            return ref.replace('refs/heads/', '') if ref else ''

        filtered = []
        for pr in prs_json:
            # Skip drafts
            if pr.get("isDraft", False):
                continue

            # Skip if user is the author
            author_name = pr.get("createdBy", {}).get("displayName", "")
            if user_name and author_name.lower() == user_name.lower():
                continue

            # Check if user is a reviewer
            reviewers = pr.get("reviewers", [])
            is_reviewer = any(
                user_name.lower() in (r.get("displayName", "").lower(), r.get("uniqueName", "").lower())
                for r in reviewers
            )
            if not is_reviewer:
                continue

            pr_id = str(pr.get("pullRequestId", ""))
            filtered.append({
                "pr_id": pr_id,
                "title": pr.get("title", ""),
                "author": author_name,
                "org": org,
                "project": project,
                "repo": repo,
                "source_branch": _strip_refs(pr.get("sourceRefName", "")),
                "target_branch": _strip_refs(pr.get("targetRefName", "")),
                "url": f"https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{pr_id}",
                "is_draft": False,
                "reviewers": [
                    {"name": r.get("displayName", ""), "vote": r.get("vote", 0)}
                    for r in reviewers
                ],
            })

        return filtered

    def _prefetch_pr_metadata(self, trigger_data: Dict) -> Optional[Dict]:
        """Pre-fetch PR metadata from Azure DevOps on the host.

        Parses the trigger file to extract PR URL, then runs
        ``az repos pr show`` on the host so the container/LLM doesn't
        need to run ``az`` at all (avoids quoting, auth, and hang issues).

        Returns:
            Dict with PR metadata, or None if extraction/fetch fails.
        """
        import json as _json
        import re

        trigger_path_str = trigger_data.get('path', '')
        if not trigger_path_str:
            return None

        trigger_file = self.vault_path / trigger_path_str
        if not trigger_file.exists():
            return None

        try:
            content = trigger_file.read_text(encoding='utf-8')
        except Exception:
            return None

        # Extract PR URL: https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{id}
        azdo_pr_pattern = re.compile(
            r'https://dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+)/pullrequest/(\d+)'
        )
        match = azdo_pr_pattern.search(content)
        if not match:
            fn_match = re.search(r'Review PR (\d+)', trigger_file.name)
            if fn_match:
                return {"pr_number": fn_match.group(1), "error": "No PR URL found in file"}
            return None

        org = match.group(1)
        project = match.group(2)
        repo = match.group(3)
        pr_id = match.group(4)

        az_bin = shutil.which('az')
        if not az_bin:
            candidate = Path(os.environ.get('ProgramFiles', '')) / 'Microsoft SDKs' / 'Azure' / 'CLI2' / 'wbin' / 'az.cmd'
            if candidate.exists():
                az_bin = str(candidate)
        if not az_bin:
            return {"pr_number": pr_id, "org": org, "project": project, "repo": repo,
                    "error": "az CLI not found on host"}

        try:
            result = subprocess.run(
                [az_bin, 'repos', 'pr', 'show',
                 '--id', pr_id,
                 '--org', f'https://dev.azure.com/{org}',
                 '--project', project,
                 '--output', 'json'],
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            return {"pr_number": pr_id, "org": org, "project": project, "repo": repo,
                    "error": "az repos pr show timed out (30s)"}
        except Exception as e:
            return {"pr_number": pr_id, "org": org, "project": project, "repo": repo,
                    "error": f"az repos pr show failed: {e}"}

        if result.returncode != 0:
            stderr = result.stderr.strip()[:500]
            return {"pr_number": pr_id, "org": org, "project": project, "repo": repo,
                    "error": f"az repos pr show returned {result.returncode}: {stderr}"}

        try:
            pr_json = _json.loads(result.stdout)
        except _json.JSONDecodeError:
            return {"pr_number": pr_id, "org": org, "project": project, "repo": repo,
                    "error": "az repos pr show returned invalid JSON"}

        def _strip_refs(ref: str) -> str:
            return ref.replace('refs/heads/', '') if ref else ''

        reviewers = []
        for r in pr_json.get('reviewers', []):
            vote_map = {10: 'Approved', 5: 'Approved with suggestions', 0: 'No vote', -5: 'Waiting', -10: 'Rejected'}
            reviewers.append({
                'name': r.get('displayName', r.get('uniqueName', 'Unknown')),
                'vote': vote_map.get(r.get('vote', 0), str(r.get('vote', 0))),
            })

        return {
            "pr_number": pr_id,
            "org": org,
            "project": project,
            "repo": repo,
            "title": pr_json.get('title', ''),
            "description": (pr_json.get('description') or '')[:2000],
            "status": pr_json.get('status', ''),
            "author": pr_json.get('createdBy', {}).get('displayName', ''),
            "creation_date": pr_json.get('creationDate', ''),
            "source_branch": _strip_refs(pr_json.get('sourceRefName', '')),
            "target_branch": _strip_refs(pr_json.get('targetRefName', '')),
            "merge_status": pr_json.get('mergeStatus', ''),
            "reviewers": reviewers,
            "pr_url": match.group(0),
        }

    def _read_teams_watermark(self, agent_abbr: str) -> Optional[str]:
        """Read the lastSynced timestamp from the Teams agent's watermark file.

        Returns ISO timestamp string or None if no watermark exists.
        """
        import json
        from ..config import get_global_runtime_dir
        vault_id = self.config.get("id", "default")
        filename = "tcs-last-sync.json" if agent_abbr == "TCS" else "tms-last-sync.json"
        state_file = get_global_runtime_dir(vault_id, vault_path=self.vault_path) / "state" / filename
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return data.get("lastSynced")
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    def _read_pending_highlight_dates(self, agent_abbr: str) -> list:
        """Read pendingHighlightDates from watermark state for retry."""
        import json
        from ..config import get_global_runtime_dir
        vault_id = self.config.get("id", "default")
        filename = "tcs-last-sync.json" if agent_abbr == "TCS" else "tms-last-sync.json"
        state_file = get_global_runtime_dir(vault_id, vault_path=self.vault_path) / "state" / filename
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return data.get("pendingHighlightDates", [])
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return []

    def _resolve_teams_fetch_window(self, agent: AgentDefinition) -> Dict:
        """Pre-resolve the fetch window for Teams agents (TCS/TMS).

        Computes explicit UTC datetime range(s) chunked into ≤6-hour windows.
        Injects ``fetch_windows`` (list of {start, end} ISO-UTC pairs) so the
        LLM never has to do time math.

        Priority: ignore_watermark+lookback > watermark > lookback fallback
        """
        from datetime import datetime, timedelta, timezone

        import os

        params = dict(agent.agent_params) if agent.agent_params else {}

        # Inject user timezone so the LLM can convert UTC timestamps to local dates
        params['user_timezone'] = self.config.get_user_timezone()

        # Inject today's date in user timezone so the LLM has an explicit anchor
        today = self.config.user_now().strftime('%Y-%m-%d')
        params['today_date'] = today

        # Compute relative path from the daily note to the vault root so the
        # LLM can construct correct markdown links without hardcoded prefixes.
        daily_note_dir = f"04-Periodic/Daily"
        params['vault_root_rel'] = os.path.relpath('.', daily_note_dir).replace('\\', '/') + '/'

        now_utc = datetime.now(timezone.utc)
        # Provide the current UTC time so the LLM can validate meeting end times
        params['current_utc'] = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Determine overall start time (UTC)
        if params.get('ignore_watermark'):
            lookback = int(params.get('lookback_hours', 1))
            range_start = now_utc - timedelta(hours=lookback)
        else:
            watermark = self._read_teams_watermark(agent.abbreviation)
            if watermark:
                try:
                    range_start = datetime.fromisoformat(watermark.replace('Z', '+00:00'))
                    if range_start.tzinfo is None:
                        range_start = range_start.replace(tzinfo=timezone.utc)
                except ValueError:
                    # Malformed watermark — fall back to lookback
                    lookback = int(params.get('lookback_hours', 1))
                    range_start = now_utc - timedelta(hours=lookback)
            else:
                # No watermark — first run
                lookback = int(params.get('lookback_hours', 1))
                range_start = now_utc - timedelta(hours=lookback)

        range_end = now_utc
        # For TMS: shift range_end back so we only query meetings that have
        # fully ended.  Graph API returns events whose time range *overlaps*
        # the query window, so a meeting ending at 3 PM would appear in a
        # query at 2 PM.  A 5-minute buffer avoids picking up in-progress
        # meetings and gives Graph indexing time to settle.
        if agent.abbreviation == "TMS":
            range_end = now_utc - timedelta(minutes=5)
            if range_end <= range_start:
                # Window too narrow — skip this cycle
                range_end = range_start

        # Chunk into ≤6-hour windows (oldest first)
        chunk_hours = 6
        windows = []
        cursor = range_start
        while cursor < range_end:
            chunk_end = min(cursor + timedelta(hours=chunk_hours), range_end)
            windows.append({
                'start': cursor.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'end': chunk_end.strftime('%Y-%m-%dT%H:%M:%SZ'),
            })
            cursor = chunk_end

        # If the range was zero-length (e.g. watermark == now), still provide one window
        if not windows:
            windows.append({
                'start': range_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'end': range_end.strftime('%Y-%m-%dT%H:%M:%SZ'),
            })

        params['fetch_windows'] = windows

        # Clean up legacy keys the LLM no longer needs
        params.pop('fetch_mode', None)
        params.pop('fetch_since', None)
        params.pop('ignore_watermark', None)

        # Inject pending highlight dates from previous failed syncs
        pending = self._read_pending_highlight_dates(agent.abbreviation)
        if pending:
            params['retry_highlight_dates'] = pending

        return params

    def _build_prompt(self, agent: AgentDefinition, trigger_data: Dict, ctx: Optional[ExecutionContext] = None) -> str:
        """
        Build execution prompt from agent definition and trigger data.

        Args:
            agent: Agent definition
            trigger_data: Trigger event data
            ctx: Execution context (optional, needed for task file path)

        Returns:
            Formatted prompt string
        """
        # System prompt (copilot-instructions.md) is NOT prepended here —
        # the Copilot SDK/CLI auto-loads it from .github/copilot-instructions.md
        # in the working directory, so injecting it would duplicate tokens.
        prompt = ""
        
        # Add agent prompt body with template variable substitution
        prompt_body = agent.prompt_body

        # Substitute date template variables ({{YYYY-MM-DD}}, {{YYYY}}, {{MM}}, {{DD}}, etc.)
        # Uses user's configured timezone from duckyai.yml (not system UTC)
        from datetime import timedelta
        now = self.config.user_now()
        yesterday = now - timedelta(days=1)
        date_replacements = {
            '{{YYYY-MM-DD}}': now.strftime('%Y-%m-%d'),
            '{{YYYY}}': now.strftime('%Y'),
            '{{MM}}': now.strftime('%m'),
            '{{DD}}': now.strftime('%d'),
            '{{date}}': now.strftime('%Y-%m-%d'),
            '{{today}}': now.strftime('%Y-%m-%d'),
            '{{yesterday}}': yesterday.strftime('%Y-%m-%d'),
            '{{Agent-Name}}': agent.abbreviation,
            '{{agent}}': agent.abbreviation,
        }
        for placeholder, value in date_replacements.items():
            prompt_body = prompt_body.replace(placeholder, value)

        prompt += prompt_body

        # Add trigger context
        prompt += "\n\n# Trigger Context\n"
        prompt += f"- Event: {trigger_data.get('event_type', 'unknown')}\n"
        prompt += f"- Input Path: {trigger_data.get('path', 'unknown')}\n"

        # Add worker context for multi-worker agents
        if '-' in agent.abbreviation:
            parts = agent.abbreviation.split('-', 1)
            worker_label = parts[1]
            prompt += f"- Worker: {worker_label} (multi-worker evaluation mode)\n"
        
        # Add task file path if available
        if ctx and ctx.task_file:
            try:
                if isinstance(ctx.task_file, Path):
                    rel_task = ctx.task_file.relative_to(self.vault_path)
                    task_ref = f"{rel_task.parent}/{rel_task.stem}"
                else:
                    task_ref = str(ctx.task_file)
                prompt += f"- Task File: {task_ref}\n"
                prompt += f"- **Update upon completion**: Set `status:` and `output:` fields\n"
            except ValueError:
                # If relative path fails, use as-is
                prompt += f"- Task File: {ctx.task_file}\n"
                prompt += f"- **Update upon completion**: Set `status:` and `output:` fields\n"

        # Add output configuration
        if agent.output_path:
            prompt += f"\n# Output Configuration\n"
            prompt += f"- Output Directory: {agent.output_path}\n"
            prompt += f"- Output Type: {agent.output_type}\n"

            # Add guidance based on output type
            if agent.output_type == "new_file":
                prompt += f"\n**IMPORTANT**: Create a NEW file in the `{agent.output_path}` directory.\n"
                prompt += f"Do NOT modify the input file inline. The output should be a separate file.\n"
                if agent.output_naming:
                    prompt += f"Use naming pattern: {agent.output_naming}\n"
            elif agent.output_type == "update_file":
                prompt += f"\n**IMPORTANT**: Update the input file IN PLACE.\n"
                prompt += f"Do NOT create a new file.\n"

        # Add frontmatter if available
        if 'frontmatter' in trigger_data:
            prompt += "\n# File Metadata\n"
            for key, value in trigger_data['frontmatter'].items():
                prompt += f"- {key}: {value}\n"

        # Add agent parameters if available
        # For Teams agents (TCS/TMS), pre-resolve the fetch window
        # so the LLM doesn't need to decide between watermark vs lookback
        resolved_params = self._resolve_teams_fetch_window(agent) if agent.abbreviation in ('TCS', 'TMS') else agent.agent_params

        # Inject user_name into agent params for all agents so they can identify
        # the user in outputs (e.g., replace own name with "Me" in notes)
        if resolved_params is None:
            resolved_params = {}
        else:
            resolved_params = dict(resolved_params)
        user_name = self.config.get_user_name()
        if user_name:
            resolved_params['user_name'] = user_name

        # Inject scan_services for the PR Scan agent (PRS)
        if agent.abbreviation == 'PRS' and 'scan_services' not in resolved_params:
            scan_services = self._build_scan_services()
            if scan_services:
                resolved_params['scan_services'] = scan_services
                # Pre-fetch PR list on the host — deterministic, no LLM running az
                prefetched = self._prefetch_pr_list(scan_services)
                resolved_params['prefetched_prs'] = prefetched

        # Pre-fetch PR metadata on the host for the PR Review agent (PR)
        # so the LLM never needs to run `az repos pr show` inside the container
        # (avoids shell-quoting, auth, and hang issues).
        pr_metadata = None
        if agent.abbreviation == 'PR':
            pr_metadata = self._prefetch_pr_metadata(trigger_data)
            if pr_metadata:
                resolved_params['pr_metadata'] = pr_metadata
                if pr_metadata.get('error'):
                    logger.warning(f"[PR] Prefetch partial — LLM will see error: {pr_metadata['error']}")
                else:
                    logger.info(f"[PR] Pre-fetched metadata for PR #{pr_metadata.get('pr_number')}: "
                                f"{pr_metadata.get('title', '')[:60]}")

        if resolved_params:
            prompt += "\n# Agent Parameters\n"
            for key, value in resolved_params.items():
                prompt += f"- {key}: {value}\n"

        # Skills are auto-discovered by CLI executors from .github/skills/
        # (built-in playbook skills are symlinked there by ensure_init)

        # Add services context (code repos linked to this vault)
        try:
            from ..services import list_services, get_services_path
            services_path = get_services_path(self.vault_path)
            services_config = self.config.get("services", {})
            service_entries = services_config.get("entries", [])
            services = list_services(self.vault_path)

            if service_entries or services:
                prompt += f"\n# Services (Code Repos)\n"
                prompt += f"- Services directory: {services_path}\n"

                # Include metadata from duckyai.yml entries
                for entry in service_entries:
                    name = entry.get("name", "")
                    metadata = entry.get("metadata", {})
                    if metadata.get("type") == "ado":
                        org = metadata.get("organization", "")
                        project = metadata.get("project", "")
                        repo_patterns = metadata.get("repositories", [])
                        repos_str = ", ".join(repo_patterns) if repo_patterns else "*"
                        prompt += f"- {name}/: ado:{org}/{project} repos=[{repos_str}]"
                        if entry.get("pr_scan"):
                            prompt += " (pr_scan: on)"
                        prompt += "\n"
                    elif services:
                        # Fall back to disk-discovered repos
                        svc = next((s for s in services if s.get("name") == name), None)
                        if svc:
                            repos_str = ", ".join(r["name"] for r in svc.get("repos", []))
                            prompt += f"- {name}/: {repos_str or '(no repos)'}\n"
                        else:
                            prompt += f"- {name}/: (not synced)\n"
                    else:
                        prompt += f"- {name}/: (no metadata)\n"
        except Exception:
            pass  # Services not configured — skip

        return prompt

    def _validate_agent_output(self, agent_output: str, agent: AgentDefinition, trigger_data: Dict, ctx: ExecutionContext) -> tuple:
        """
        Validate that agent-reported output file exists.

        Args:
            agent_output: Output file link reported by agent (wiki link format)
            agent: Agent definition
            trigger_data: Trigger event data
            ctx: Execution context

        Returns:
            Tuple of (is_valid, output_link, error_message)
        """
        # Extract file path from link format: [[path/to/file]] or [text](path/to/file.md)
        import re
        wiki_match = re.search(r'\[\[([^\]]+)\]\]', agent_output)
        md_match = re.search(r'\[[^\]]*\]\(([^)]+)\)', agent_output)
        if wiki_match:
            file_path_str = wiki_match.group(1)
        elif md_match:
            from urllib.parse import unquote
            file_path_str = unquote(md_match.group(1))
        else:
            return False, None, f"Invalid output format: {agent_output}. Expected link format [text](path) or [[path/to/file]]"
        
        file_path_str = file_path_str.split('|')[0] if '|' in file_path_str else file_path_str
        # Handle paths with or without .md extension
        if not file_path_str.endswith('.md'):
            file_path_str += '.md'
        
        # Try to resolve the file path
        output_path = self.vault_path / file_path_str
        if output_path.exists():
            try:
                rel_path = output_path.relative_to(self.vault_path)
                output_link = f"{rel_path.parent}/{rel_path.stem}"
                return True, output_link, None
            except ValueError:
                return True, file_path_str, None
        else:
            return False, None, f"Output file not found: {file_path_str}"

    def _validate_output(self, agent: AgentDefinition, trigger_data: Dict, ctx: ExecutionContext) -> tuple:
        """
        Validate that the expected output was created.

        Args:
            agent: Agent definition
            trigger_data: Trigger event data
            ctx: Execution context

        Returns:
            Tuple of (is_valid, output_link, error_message)
        """
        input_path_str = trigger_data.get('path', '')
        input_path = self.vault_path / input_path_str if input_path_str else None

        # Agents that don't require input files (e.g., TCS, GDR) skip input validation
        if not agent.requires_input_file and not input_path_str:
            # For update_file mode, check if output_path file was modified
            if agent.output_type == "update_file" and agent.output_path:
                output_dir = self.vault_path / agent.output_path
                start_time = ctx.start_time.timestamp() - 5 if ctx.start_time else 0
                # Look for any recently modified files in output dir
                for out_file in output_dir.glob("*.md"):
                    if out_file.stat().st_mtime >= start_time:
                        rel_path = out_file.relative_to(self.vault_path)
                        return True, f"{rel_path.parent}/{rel_path.stem}", None
                if agent.output_optional:
                    return True, None, None
                # Agent completed but we can't verify output — trust the agent's own output field
                return True, None, None
            # For new_file or no output_path, fall through to normal validation
            if not agent.output_path:
                return True, None, None

        # If no output_path configured, assume inline update
        if not agent.output_path:
            # Verify input file still exists
            if input_path and input_path.exists():
                return True, input_path_str, None
            else:
                return False, None, "Input file no longer exists"

        # For update_file: verify input file was modified
        if agent.output_type == "update_file":
            if not input_path or not input_path.exists():
                return False, None, f"Input file not found: {input_path_str}"

            # Check if file was modified during execution
            file_mtime = input_path.stat().st_mtime
            start_time = ctx.start_time.timestamp() - 5 if ctx.start_time else 0

            if file_mtime >= start_time:
                return True, input_path_str, None
            else:
                return False, input_path_str, "Input file was not modified (update_file mode)"

        # For new_file: verify output directory has new files
        if agent.output_type == "new_file":
            output_dir = self.vault_path / agent.output_path
            if not output_dir.exists():
                output_dir.mkdir(parents=True, exist_ok=True)

            # Look for output files created/modified after execution started
            start_time = ctx.start_time.timestamp() - 5 if ctx.start_time else 0
            input_filename = Path(input_path_str).stem if input_path_str else ''

            # Determine expected extensions from output_naming
            output_extensions = ['.md']  # default
            if agent.output_naming:
                ext = Path(agent.output_naming).suffix
                if ext and ext != '.md':
                    output_extensions.append(ext)

            # Also support common non-md output types when no specific naming set
            if not agent.output_naming or '{' in agent.output_naming:
                output_extensions.extend(['.canvas', '.json'])

            recent_files = []
            for ext in set(output_extensions):
                pattern = f"*{ext}"
                for out_file in output_dir.glob(pattern):
                    if out_file.stat().st_mtime >= start_time:
                        # Prioritize files with matching input filename
                        if input_filename and input_filename in out_file.stem:
                            recent_files.insert(0, out_file)
                        else:
                            recent_files.append(out_file)

            if recent_files:
                # Use the most relevant file (first in list)
                output_file = recent_files[0]
                try:
                    rel_path = output_file.relative_to(self.vault_path)
                    output_link = f"{rel_path.parent}/{rel_path.stem}"
                    logger.info(f"Found output file: {rel_path}")
                    return True, output_link, None
                except ValueError:
                    return True, str(output_file), None
            else:
                # No output files found
                if agent.output_optional:
                    # No output is acceptable for agents with optional output
                    logger.info(f"No output found for {agent.abbreviation}, but output is optional")
                    return True, None, None
                else:
                    return False, None, f"No new file found in {agent.output_path} (new_file mode)"

        # Default: no validation
        return True, input_path_str if input_path_str else None, None

    def _prepare_log_path(self, agent: AgentDefinition, ctx: ExecutionContext) -> Path:
        """
        Prepare log file path for execution.

        Logs are organized per-agent in subdirectories:
          <vault>/.duckyai/logs/{AGENT_ABBR}/{timestamp}-{agent}.log

        Args:
            agent: Agent definition
            ctx: Execution context

        Returns:
            Path to log file
        """
        # Format log pattern
        log_name = agent.log_pattern.format(
            timestamp=ctx.start_time.strftime('%Y-%m-%d-%H%M%S'),
            agent=agent.abbreviation,
            execution_id=ctx.execution_id
        )

        # Get logs directory from config. For bare temp vaults without duckyai.yml,
        # keep the legacy test layout under _Settings_/Logs.
        logs_dir = self.config.get_orchestrator_logs_dir()
        has_config = (self.vault_path / '.duckyai' / 'duckyai.yml').exists() or (self.vault_path / 'duckyai.yml').exists()
        if not has_config and logs_dir.replace('\\', '/').endswith('.duckyai/logs'):
            logs_dir = '_Settings_/Logs'

        logs_root = self.vault_path / logs_dir
        if Path(logs_dir).name.lower() == 'logs':
            log_path = logs_root / log_name
        else:
            log_path = logs_root / agent.abbreviation / log_name

        # Try to reuse existing log path from frontmatter
        log_link = ctx.trigger_data.get('_generation_log', '')
        if log_link and (log_link.startswith('[[') or '](' in log_link):
            try:
                # Extract path from [[path]] or [text](path) format
                if log_link.startswith('[['):
                    log_rel_path = log_link[2:-2]
                else:
                    import re as _re
                    _m = _re.search(r'\]\(([^)]+)\)', log_link)
                    log_rel_path = _m.group(1) if _m else log_link
                log_path = self.vault_path / log_rel_path
                logger.info(f"Reusing log file: {log_path.name}", console=True)
            except Exception as e:
                logger.warning(f"Failed to parse existing log path: {e}")
        
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create empty log file if it doesn't exist to ensure wiki links work
        if not log_path.exists():
            log_path.touch()

        return log_path

    def get_running_count(self) -> int:
        """
        Get current number of running executions.

        Returns:
            Number of running executions
        """
        with self._count_lock:
            return self._running_count

    def get_agent_running_count(self, agent_abbr: str) -> int:
        """
        Get current number of running executions for specific agent.

        Args:
            agent_abbr: Agent abbreviation

        Returns:
            Number of running executions for this agent
        """
        with self._agent_lock:
            return self._agent_counts.get(agent_abbr, 0)

    def get_running_executions(self) -> List[ExecutionContext]:
        """
        Get list of currently running executions.

        Returns:
            List of ExecutionContext instances
        """
        with self._executions_lock:
            return list(self._running_executions.values())

    def update_settings(self, max_concurrent: int, refresh_mcp: bool = False) -> None:
        """
        Update execution manager settings.
        
        Updates max_concurrent without affecting running executions.
        Optionally refreshes MCP server configuration.
        
        Args:
            max_concurrent: New maximum concurrent executions
            refresh_mcp: If True, re-discover MCP config from vault
        """
        with self._count_lock:
            old_max = self.max_concurrent
            self.max_concurrent = max_concurrent
            logger.info(f"Updated max_concurrent: {old_max} -> {max_concurrent}")
        
        if refresh_mcp:
            old_mcp = self.mcp_config
            self.mcp_config = self._auto_discover_mcp_config()
            if self.mcp_config != old_mcp:
                logger.info("MCP config refreshed during hot-reload", console=True)
            else:
                logger.debug("MCP config unchanged after refresh")

    def _apply_post_processing(self, agent: AgentDefinition, trigger_data: Dict):
        """
        Apply post-processing actions after successful execution.

        Args:
            agent: Agent definition
            trigger_data: Trigger event data
        """
        if agent.post_process_action == "remove_trigger_content":
            self._remove_trigger_content(agent, trigger_data)
        else:
            logger.warning(f"Unknown post-process action: {agent.post_process_action}")

    def _remove_trigger_content(self, agent: AgentDefinition, trigger_data: Dict):
        """
        Remove trigger content pattern from source file.

        Args:
            agent: Agent definition
            trigger_data: Trigger event data
        """
        if not agent.trigger_content_pattern:
            logger.warning("No trigger_content_pattern defined for remove_trigger_content action")
            return

        try:
            # Get source file path
            event_path = trigger_data.get('path')
            if not event_path:
                logger.warning("No path in trigger_data for post-processing")
                return

            file_path = self.vault_path / event_path

            if not file_path.exists():
                logger.warning(f"Source file not found for post-processing: {file_path}")
                return

            # Read file content
            content = file_path.read_text(encoding='utf-8')

            # Remove trigger pattern
            from ..markdown_utils import remove_pattern_from_content
            updated_content = remove_pattern_from_content(content, agent.trigger_content_pattern)

            # Write back if changed
            if updated_content != content:
                file_path.write_text(updated_content, encoding='utf-8')
                logger.info(f"Removed trigger content from: {event_path}")
            else:
                logger.debug(f"No trigger content found to remove in: {event_path}")

        except Exception as e:
            logger.error(f"Error during post-processing: {e}")
