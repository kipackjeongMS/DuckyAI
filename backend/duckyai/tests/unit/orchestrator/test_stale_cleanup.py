"""Tests for stale IN_PROGRESS task cleanup."""

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import pytest

from duckyai.orchestrator.task_manager import TaskFileManagerV2, DailyExecutionLog, ExecutionRecord
from duckyai.orchestrator.core import Orchestrator
from duckyai.orchestrator.models import AgentDefinition, TriggerEvent


# ── Helpers ──────────────────────────────────────────────────────────

def _make_config(now: datetime):
    """Create a mock Config that returns a fixed 'now'."""
    config = Mock()
    config.user_now.return_value = now
    config.get_orchestrator_tasks_dir.return_value = ".duckyai/tasks"
    config.config = {}
    config.get.return_value = None
    return config


def _make_task_manager(vault: Path, now: datetime):
    """Build a TaskFileManagerV2 with a mock config pinned to `now`."""
    config = _make_config(now)
    return TaskFileManagerV2(vault, config=config, orchestrator_settings={})


def _seed_entry(daily_log: DailyExecutionLog, date_str: str, **overrides):
    """Write a single execution entry to a daily log."""
    defaults = dict(
        id="test-id",
        agent="TST",
        worker="copilot_sdk",
        worker_label="",
        task_type="TST",
        status="IN_PROGRESS",
        priority="normal",
        trigger_type="scheduled",
        input_path="",
        output="",
        error="",
        log_path="",
        created=datetime.now().isoformat(),
        updated=datetime.now().isoformat(),
        trigger_data_json="",
        agent_params="",
        archived="false",
    )
    defaults.update(overrides)
    rec = ExecutionRecord(**defaults)
    daily_log.add_entry(rec, date_str)


# ── TaskFileManagerV2.find_stale_in_progress ─────────────────────────

class TestFindStaleInProgress:
    """Tests for finding stale IN_PROGRESS entries."""

    @pytest.fixture
    def vault(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_no_entries_returns_empty(self, vault):
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)
        assert tm.find_stale_in_progress() == []

    def test_completed_entries_not_returned(self, vault):
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="done-1", status="PROCESSED",
                     created=(now - timedelta(hours=2)).isoformat())

        assert tm.find_stale_in_progress() == []

    def test_recent_in_progress_not_stale(self, vault):
        """IN_PROGRESS entry created 5 minutes ago should NOT be stale (default timeout 30m)."""
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="fresh-1", status="IN_PROGRESS",
                     created=(now - timedelta(minutes=5)).isoformat())

        assert tm.find_stale_in_progress(default_timeout_minutes=30) == []

    def test_old_in_progress_is_stale(self, vault):
        """IN_PROGRESS entry created 45 minutes ago should be stale (default timeout 30m)."""
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="stale-1", agent="TCS", status="IN_PROGRESS",
                     created=(now - timedelta(minutes=45)).isoformat())

        results = tm.find_stale_in_progress(default_timeout_minutes=30)
        assert len(results) == 1
        assert results[0]['id'] == 'stale-1'

    def test_custom_timeout_per_agent(self, vault):
        """Agent with longer timeout should not be marked stale prematurely."""
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        # 45 min old, but agent has 60-min timeout → not stale
        _seed_entry(log, "2026-04-22",
                     id="long-timeout",
                     agent="PRS",
                     status="IN_PROGRESS",
                     created=(now - timedelta(minutes=45)).isoformat())

        agent_timeouts = {"PRS": 60}
        results = tm.find_stale_in_progress(
            default_timeout_minutes=30,
            agent_timeouts=agent_timeouts,
        )
        assert len(results) == 0

    def test_custom_timeout_per_agent_expired(self, vault):
        """Agent whose custom timeout IS exceeded should be stale."""
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="expired-prs",
                     agent="PRS",
                     status="IN_PROGRESS",
                     created=(now - timedelta(minutes=65)).isoformat())

        agent_timeouts = {"PRS": 60}
        results = tm.find_stale_in_progress(
            default_timeout_minutes=30,
            agent_timeouts=agent_timeouts,
        )
        assert len(results) == 1
        assert results[0]['id'] == 'expired-prs'

    def test_multiple_stale_across_days(self, vault):
        """Stale entries from yesterday and today are both found."""
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        # Yesterday's stale entry
        log_yesterday = tm._get_daily_log("2026-04-21")
        _seed_entry(log_yesterday, "2026-04-21",
                     id="stale-yesterday",
                     status="IN_PROGRESS",
                     created=(now - timedelta(hours=20)).isoformat())

        # Today's stale entry
        log_today = tm._get_daily_log("2026-04-22")
        _seed_entry(log_today, "2026-04-22",
                     id="stale-today",
                     status="IN_PROGRESS",
                     created=(now - timedelta(minutes=45)).isoformat())

        results = tm.find_stale_in_progress(default_timeout_minutes=30)
        ids = {r['id'] for r in results}
        assert ids == {'stale-yesterday', 'stale-today'}

    def test_malformed_created_timestamp_skipped(self, vault):
        """Entries with unparseable created timestamp are silently skipped."""
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="bad-ts",
                     status="IN_PROGRESS",
                     created="not-a-date")

        # Should not raise, should return empty
        assert tm.find_stale_in_progress() == []

    def test_empty_created_timestamp_skipped(self, vault):
        """Entries with empty created timestamp are silently skipped."""
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="empty-ts",
                     status="IN_PROGRESS",
                     created="")

        assert tm.find_stale_in_progress() == []

    def test_queued_entries_not_returned(self, vault):
        """Only IN_PROGRESS is considered, not QUEUED or other statuses."""
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="queued-1", status="QUEUED",
                     created=(now - timedelta(hours=2)).isoformat())
        _seed_entry(log, "2026-04-22",
                     id="failed-1", status="FAILED",
                     created=(now - timedelta(hours=2)).isoformat())

        assert tm.find_stale_in_progress() == []

    def test_boundary_exactly_at_timeout(self, vault):
        """Entry exactly at the timeout boundary should be stale (>= comparison)."""
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="boundary",
                     status="IN_PROGRESS",
                     created=(now - timedelta(minutes=30)).isoformat())

        # At exactly 30 min with 30-min timeout → stale (we use > timeout, not >=)
        # This should be stale to cover process crashes at the timeout boundary
        results = tm.find_stale_in_progress(default_timeout_minutes=30)
        assert len(results) == 1


# ── TaskFileManagerV2.mark_stale_as_failed ───────────────────────────

class TestMarkStaleAsFailed:
    """Tests for transitioning stale IN_PROGRESS entries to FAILED."""

    @pytest.fixture
    def vault(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_marks_stale_entry_failed(self, vault):
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="stale-1", agent="TCS", status="IN_PROGRESS",
                     created=(now - timedelta(minutes=45)).isoformat())

        count = tm.mark_stale_as_failed(default_timeout_minutes=30)
        assert count == 1

        # Verify the entry was updated
        entries = log.find_entries(id="stale-1")
        assert len(entries) == 1
        assert entries[0]['status'] == 'FAILED'
        assert 'stale' in entries[0].get('error', '').lower()

    def test_no_stale_entries_returns_zero(self, vault):
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)
        assert tm.mark_stale_as_failed() == 0

    def test_marks_multiple_stale_entries(self, vault):
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="stale-a", agent="TCS", status="IN_PROGRESS",
                     created=(now - timedelta(minutes=45)).isoformat())
        _seed_entry(log, "2026-04-22",
                     id="stale-b", agent="TMS", status="IN_PROGRESS",
                     created=(now - timedelta(minutes=60)).isoformat())

        count = tm.mark_stale_as_failed(default_timeout_minutes=30)
        assert count == 2

    def test_respects_agent_timeouts(self, vault):
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        # 45 min old, PRS has 60-min timeout → NOT stale
        _seed_entry(log, "2026-04-22",
                     id="prs-ok", agent="PRS", status="IN_PROGRESS",
                     created=(now - timedelta(minutes=45)).isoformat())
        # 45 min old, TCS uses default 30-min timeout → stale
        _seed_entry(log, "2026-04-22",
                     id="tcs-stale", agent="TCS", status="IN_PROGRESS",
                     created=(now - timedelta(minutes=45)).isoformat())

        count = tm.mark_stale_as_failed(
            default_timeout_minutes=30,
            agent_timeouts={"PRS": 60},
        )
        assert count == 1

        # PRS should still be IN_PROGRESS
        prs = log.find_entries(id="prs-ok")
        assert prs[0]['status'] == 'IN_PROGRESS'

        # TCS should be FAILED
        tcs = log.find_entries(id="tcs-stale")
        assert tcs[0]['status'] == 'FAILED'

    def test_leaves_fresh_in_progress_alone(self, vault):
        now = datetime(2026, 4, 22, 12, 0, 0)
        tm = _make_task_manager(vault, now)

        log = tm._get_daily_log("2026-04-22")
        _seed_entry(log, "2026-04-22",
                     id="fresh-1", status="IN_PROGRESS",
                     created=(now - timedelta(minutes=5)).isoformat())

        count = tm.mark_stale_as_failed(default_timeout_minutes=30)
        assert count == 0

        entries = log.find_entries(id="fresh-1")
        assert entries[0]['status'] == 'IN_PROGRESS'


# ── Orchestrator startup integration ─────────────────────────────────

class TestOrchestratorStaleCleanup:
    """Tests for stale cleanup during orchestrator startup."""

    @pytest.fixture
    def temp_vault(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            agents_dir = vault_path / "_Settings_" / "Agents"
            agents_dir.mkdir(parents=True)
            yield vault_path, agents_dir

    def test_startup_cleans_stale_tasks(self, temp_vault):
        """Orchestrator.start() should mark stale IN_PROGRESS as FAILED."""
        vault_path, agents_dir = temp_vault

        orch = Orchestrator(vault_path, agents_dir)
        tm = orch.execution_manager.task_manager

        now = orch.config.user_now()
        date_str = now.strftime('%Y-%m-%d')
        log = tm._get_daily_log(date_str)

        # Seed a stale entry (2 hours old)
        _seed_entry(log, date_str,
                     id="stale-startup",
                     agent="TCS",
                     status="IN_PROGRESS",
                     created=(now - timedelta(hours=2)).isoformat())

        # Start and stop orchestrator
        orch.start()
        # Give background thread time to run
        time.sleep(0.5)
        orch.stop()

        # Verify entry was marked FAILED
        entries = log.find_entries(id="stale-startup")
        assert len(entries) == 1
        assert entries[0]['status'] == 'FAILED'

    def test_startup_preserves_fresh_in_progress(self, temp_vault):
        """Orchestrator.start() should NOT touch fresh IN_PROGRESS entries."""
        vault_path, agents_dir = temp_vault

        orch = Orchestrator(vault_path, agents_dir)
        tm = orch.execution_manager.task_manager

        now = orch.config.user_now()
        date_str = now.strftime('%Y-%m-%d')
        log = tm._get_daily_log(date_str)

        # Seed a fresh entry (1 minute old)
        _seed_entry(log, date_str,
                     id="fresh-startup",
                     status="IN_PROGRESS",
                     created=(now - timedelta(minutes=1)).isoformat())

        orch.start()
        time.sleep(0.5)
        orch.stop()

        entries = log.find_entries(id="fresh-startup")
        assert entries[0]['status'] == 'IN_PROGRESS'

    def test_startup_uses_agent_timeouts(self, temp_vault):
        """Cleanup should use per-agent timeout_minutes from agent definitions."""
        vault_path, agents_dir = temp_vault

        # Create an agent with 60-min timeout
        agent_content = """---
title: "Long Runner"
abbreviation: "LNG"
category: "processing"
trigger_pattern: "Ingest/LNG/*.md"
trigger_event: "created"
timeout_minutes: 60
---
Long running agent prompt
"""
        (agents_dir / "Long Runner.md").write_text(agent_content, encoding='utf-8')

        orch = Orchestrator(vault_path, agents_dir)
        tm = orch.execution_manager.task_manager

        now = orch.config.user_now()
        date_str = now.strftime('%Y-%m-%d')
        log = tm._get_daily_log(date_str)

        # 45 min old — within LNG's 60-min timeout → should stay IN_PROGRESS
        _seed_entry(log, date_str,
                     id="lng-ok",
                     agent="LNG",
                     status="IN_PROGRESS",
                     created=(now - timedelta(minutes=45)).isoformat())

        orch.start()
        time.sleep(0.5)
        orch.stop()

        entries = log.find_entries(id="lng-ok")
        assert entries[0]['status'] == 'IN_PROGRESS'

    def test_cleanup_errors_dont_block_startup(self, temp_vault):
        """If cleanup fails, orchestrator should still start normally."""
        vault_path, agents_dir = temp_vault

        orch = Orchestrator(vault_path, agents_dir)

        with patch.object(orch.execution_manager.task_manager, 'mark_stale_as_failed',
                          side_effect=Exception("disk error")):
            # Should not raise
            orch.start()
            time.sleep(0.3)
            assert orch._running is True
            orch.stop()
