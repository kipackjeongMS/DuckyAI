"""
Daily execution log manager for orchestrator (v2).

Replaces per-execution task files with a single daily log file:
  .duckyai/tasks/YYYY-MM-DD.md

Each execution is a row in a YAML array (frontmatter) + markdown table (body).
"""
import json
import threading
from pathlib import Path
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from .models import AgentDefinition, ExecutionContext
from ..logger import Logger

logger = Logger()


class ExecutionRecord:
    """A single execution entry in the daily log."""

    __slots__ = (
        'id', 'agent', 'worker', 'worker_label', 'task_type',
        'status', 'priority', 'trigger_type', 'input_path',
        'output', 'error', 'log_path', 'created', 'updated',
        'trigger_data_json', 'agent_params', 'archived',
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot, ''))

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__ if getattr(self, s, '')}

    @classmethod
    def from_dict(cls, d: dict) -> 'ExecutionRecord':
        return cls(**{k: v for k, v in d.items() if k in cls.__slots__})


class DailyExecutionLog:
    """
    Manages a single daily log file.

    File format:
    ```
    ---
    date: 2026-04-03
    entries:
      - id: "abc123"
        agent: "EIC"
        status: "completed"
        ...
    ---
    # Execution Log — 2026-04-03

    | Time | Agent | Status | Input | Duration | Output |
    |------|-------|--------|-------|----------|--------|
    | 09:15 | EIC | completed | article.md | 12.3s | ... |
    ```
    """

    def __init__(self, file_path: Path, config=None):
        self.file_path = file_path
        self.config = config
        self._lock = threading.Lock()

    def _read_entries(self) -> List[dict]:
        """Read all entries from the daily log file."""
        if not self.file_path.exists():
            return []

        from ..markdown_utils import read_frontmatter
        fm = read_frontmatter(self.file_path)
        entries = fm.get('entries', [])
        return entries if isinstance(entries, list) else []

    def _write(self, entries: List[dict], date_str: str):
        """Write the full daily log file atomically."""
        import os
        from ruamel.yaml import YAML
        from io import StringIO

        yaml_parser = YAML()
        yaml_parser.default_flow_style = False
        yaml_parser.width = 4096

        fm_data = {
            'date': date_str,
            'entries': entries,
        }

        stream = StringIO()
        yaml_parser.dump(fm_data, stream)
        frontmatter = stream.getvalue()

        # Build markdown table
        table_rows = []
        for e in entries:
            time_str = ''
            created = e.get('created', '')
            if created:
                try:
                    dt = datetime.fromisoformat(str(created))
                    time_str = dt.strftime('%H:%M')
                except (ValueError, TypeError):
                    time_str = str(created)[:5]

            status = e.get('status', '')
            agent = e.get('agent', '')
            input_path = e.get('input_path', '')
            if input_path:
                input_path = Path(input_path).name if input_path != '' else ''
            output = e.get('output', '')
            error = e.get('error', '')

            # Duration: calculate from created/updated if both available
            duration = ''
            updated = e.get('updated', '')
            if updated and created and status in ('completed', 'failed', 'timeout'):
                try:
                    t0 = datetime.fromisoformat(str(created))
                    t1 = datetime.fromisoformat(str(updated))
                    secs = (t1 - t0).total_seconds()
                    duration = f"{secs:.1f}s" if secs < 120 else f"{secs/60:.1f}m"
                except (ValueError, TypeError):
                    pass

            status_display = status
            if error:
                status_display = f"{status}: {error[:40]}"

            table_rows.append(
                f"| {time_str} | {agent} | {status_display} | {input_path} | {duration} | {output} |"
            )

        table_header = (
            "| Time | Agent | Status | Input | Duration | Output |\n"
            "|------|-------|--------|-------|----------|--------|\n"
        )
        table_body = '\n'.join(table_rows) if table_rows else '| — | — | — | — | — | — |'

        content = (
            f"---\n{frontmatter}---\n\n"
            f"# Execution Log — {date_str}\n\n"
            f"{table_header}{table_body}\n"
        )

        # Atomic write
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

    def add_entry(self, record: ExecutionRecord, date_str: str) -> None:
        """Add a new execution entry to the daily log."""
        with self._lock:
            entries = self._read_entries()
            entries.append(record.to_dict())
            self._write(entries, date_str)

    def update_entry(self, execution_id: str, updates: dict, date_str: str) -> bool:
        """Update an existing entry by execution_id."""
        with self._lock:
            entries = self._read_entries()
            for entry in entries:
                if entry.get('id') == execution_id:
                    entry.update(updates)
                    self._write(entries, date_str)
                    return True
            return False

    def find_entries(self, **filters) -> List[dict]:
        """Find entries matching all given field=value filters."""
        entries = self._read_entries()
        results = []
        for entry in entries:
            if all(entry.get(k) == v for k, v in filters.items()):
                results.append(entry)
        return results


class TaskFileManagerV2:
    """
    Daily execution log manager.

    Replaces per-execution task files with one file per day.
    """

    def __init__(self, vault_path: Path, config=None, orchestrator_settings=None):
        from ..config import Config

        self.vault_path = Path(vault_path)
        self.config = config or Config()
        self.orchestrator_settings = orchestrator_settings or {}

        # Get tasks directory (same location as before)
        if orchestrator_settings and 'tasks_dir' in orchestrator_settings:
            tasks_dir = orchestrator_settings['tasks_dir']
        else:
            tasks_dir = self.config.get_orchestrator_tasks_dir()

        tasks_path = Path(tasks_dir)
        self.tasks_dir = tasks_path if tasks_path.is_absolute() else self.vault_path / tasks_dir
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        # Cache of DailyExecutionLog instances
        self._logs: Dict[str, DailyExecutionLog] = {}
        self._logs_lock = threading.Lock()

    def _get_daily_log(self, date_str: str) -> DailyExecutionLog:
        """Get or create a DailyExecutionLog for a given date."""
        with self._logs_lock:
            if date_str not in self._logs:
                log_path = self.tasks_dir / f"{date_str}.md"
                self._logs[date_str] = DailyExecutionLog(log_path, self.config)
            return self._logs[date_str]

    def _now_date_str(self) -> str:
        return self.config.user_now().strftime('%Y-%m-%d')

    def create_task_file(
        self,
        ctx: ExecutionContext,
        agent: AgentDefinition,
        initial_status: str = "IN_PROGRESS",
        trigger_data_json: Optional[str] = None,
    ) -> Optional[str]:
        """
        Add an execution entry to today's daily log.

        Returns:
            The execution_id string (used as handle for updates), or None if disabled.
        """
        if not agent.task_create:
            logger.debug(f"Task file creation disabled for agent {agent.abbreviation}")
            return None

        try:
            date_str = self._now_date_str()
            now = self.config.user_now()

            # Extract task_type and worker_label
            if '-' in agent.abbreviation:
                parts = agent.abbreviation.rsplit('-', 1)
                task_type = parts[0]
                worker_label = parts[1]
            else:
                task_type = agent.abbreviation
                worker_label = ''

            # Input path
            input_path = ctx.trigger_data.get('path', '')

            # Log path
            log_path = ''
            if ctx.log_file:
                try:
                    log_path = str(ctx.log_file.relative_to(self.vault_path))
                except ValueError:
                    log_path = str(ctx.log_file)

            # Execution ID — use ctx.execution_id if available, else generate
            exec_id = getattr(ctx, 'execution_id', None) or str(__import__('uuid').uuid4())[:8]

            record = ExecutionRecord(
                id=exec_id,
                agent=agent.abbreviation,
                worker=agent.executor,
                worker_label=worker_label,
                task_type=task_type,
                status=initial_status,
                priority=agent.task_priority,
                trigger_type=ctx.trigger_data.get('event_type', 'unknown'),
                input_path=input_path,
                output='',
                error='',
                log_path=log_path,
                created=now.isoformat(),
                updated=now.isoformat(),
                trigger_data_json=trigger_data_json or '',
                agent_params=json.dumps(agent.agent_params) if agent.agent_params else '',
                archived=str(agent.task_archived).lower(),
            )

            daily_log = self._get_daily_log(date_str)
            daily_log.add_entry(record, date_str)
            logger.info(f"📝 Logged execution: {agent.abbreviation} [{exec_id}]", console=True)

            return exec_id

        except Exception as e:
            logger.error(f"Failed to log execution: {e}")
            return None

    def update_task_status(
        self,
        task_handle,
        status: str,
        output: Optional[str] = None,
        output_link: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """
        Update an execution entry's status.

        Args:
            task_handle: The execution_id string.
            status: New status.
            output: Optional output link.
            output_link: Alias for output.
            error_message: Optional error message.
        """
        exec_id = str(task_handle)
        updates = {
            'status': status,
            'updated': self.config.user_now().isoformat(),
        }
        if output or output_link:
            updates['output'] = output or output_link
        if error_message:
            updates['error'] = error_message

        # Search today's log first, then recent days
        for days_back in range(7):
            from datetime import timedelta
            d = self.config.user_now() - timedelta(days=days_back)
            date_str = d.strftime('%Y-%m-%d')
            daily_log = self._get_daily_log(date_str)
            if daily_log.update_entry(exec_id, updates, date_str):
                logger.info(f"🔄 Updated [{exec_id}] → {status}", console=True)
                return

        logger.warning(f"Execution {exec_id} not found in recent daily logs")

    def update_task_status_with_trigger_data(
        self,
        task_handle,
        status: str,
        trigger_data_json: str,
    ):
        """Update status and add trigger data to an entry."""
        exec_id = str(task_handle)
        updates = {
            'status': status,
            'trigger_data_json': trigger_data_json,
            'updated': self.config.user_now().isoformat(),
        }

        for days_back in range(7):
            from datetime import timedelta
            d = self.config.user_now() - timedelta(days=days_back)
            date_str = d.strftime('%Y-%m-%d')
            daily_log = self._get_daily_log(date_str)
            if daily_log.update_entry(exec_id, updates, date_str):
                return

    def find_queued_entries(self) -> List[Dict[str, Any]]:
        """
        Find all QUEUED entries across recent daily logs.

        Returns list of dicts with entry data + '_date_str' key.
        """
        results = []
        for days_back in range(7):
            from datetime import timedelta
            d = self.config.user_now() - timedelta(days=days_back)
            date_str = d.strftime('%Y-%m-%d')
            daily_log = self._get_daily_log(date_str)
            for entry in daily_log.find_entries(status='QUEUED'):
                entry['_date_str'] = date_str
                results.append(entry)
        return results

    def count_queued(self) -> int:
        """Count QUEUED entries across recent daily logs."""
        return len(self.find_queued_entries())


