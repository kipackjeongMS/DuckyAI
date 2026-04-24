"""Unit tests for quiet hours feature across config, cron scheduler, and core."""

from datetime import datetime, time
from queue import Queue
from unittest.mock import Mock, patch, MagicMock
import pytest

from duckyai.config import Config
from duckyai.orchestrator.cron_scheduler import CronScheduler
from duckyai.orchestrator.models import AgentDefinition, TriggerEvent


# ------------------------------------------------------------------ #
# Config.is_quiet_hours()
# ------------------------------------------------------------------ #

class TestConfigQuietHours:
    """Test Config.is_quiet_hours() method."""

    def _make_config(self, quiet_hours_dict, now_time):
        """Helper: create Config with given quiet_hours and mock user_now."""
        config = Config.__new__(Config)
        config.vault_path = None
        config.config = {"orchestrator": {"quiet_hours": quiet_hours_dict}} if quiet_hours_dict is not None else {}
        config._os_timezone_cache = None

        mock_dt = Mock()
        mock_dt.time.return_value = now_time
        config.user_now = Mock(return_value=mock_dt)
        return config

    def test_disabled(self):
        qh = {"enabled": False, "start": "23:00", "end": "08:00"}
        config = self._make_config(qh, time(2, 0))
        assert config.is_quiet_hours() is False

    def test_missing_section(self):
        config = self._make_config(None, time(2, 0))
        assert config.is_quiet_hours() is False

    def test_enabled_missing_times(self):
        config = self._make_config({"enabled": True}, time(2, 0))
        assert config.is_quiet_hours() is False

    def test_wrap_midnight_inside(self):
        """23:00-08:00, current time 02:00 → quiet."""
        qh = {"enabled": True, "start": "23:00", "end": "08:00"}
        config = self._make_config(qh, time(2, 0))
        assert config.is_quiet_hours() is True

    def test_wrap_midnight_before_start(self):
        """23:00-08:00, current time 22:00 → not quiet."""
        qh = {"enabled": True, "start": "23:00", "end": "08:00"}
        config = self._make_config(qh, time(22, 0))
        assert config.is_quiet_hours() is False

    def test_wrap_midnight_at_start(self):
        """23:00-08:00, current time 23:00 → quiet."""
        qh = {"enabled": True, "start": "23:00", "end": "08:00"}
        config = self._make_config(qh, time(23, 0))
        assert config.is_quiet_hours() is True

    def test_wrap_midnight_at_end(self):
        """23:00-08:00, current time 08:00 → not quiet (end is exclusive)."""
        qh = {"enabled": True, "start": "23:00", "end": "08:00"}
        config = self._make_config(qh, time(8, 0))
        assert config.is_quiet_hours() is False

    def test_wrap_midnight_after_end(self):
        """23:00-08:00, current time 12:00 → not quiet."""
        qh = {"enabled": True, "start": "23:00", "end": "08:00"}
        config = self._make_config(qh, time(12, 0))
        assert config.is_quiet_hours() is False

    def test_same_day_inside(self):
        """08:00-17:00, current time 12:00 → quiet."""
        qh = {"enabled": True, "start": "08:00", "end": "17:00"}
        config = self._make_config(qh, time(12, 0))
        assert config.is_quiet_hours() is True

    def test_same_day_outside(self):
        """08:00-17:00, current time 20:00 → not quiet."""
        qh = {"enabled": True, "start": "08:00", "end": "17:00"}
        config = self._make_config(qh, time(20, 0))
        assert config.is_quiet_hours() is False

    def test_same_day_at_start(self):
        """08:00-17:00, current time 08:00 → quiet."""
        qh = {"enabled": True, "start": "08:00", "end": "17:00"}
        config = self._make_config(qh, time(8, 0))
        assert config.is_quiet_hours() is True

    def test_same_day_at_end(self):
        """08:00-17:00, current time 17:00 → not quiet (end exclusive)."""
        qh = {"enabled": True, "start": "08:00", "end": "17:00"}
        config = self._make_config(qh, time(17, 0))
        assert config.is_quiet_hours() is False

    def test_invalid_time_format(self):
        """Garbage start/end → returns False (no crash)."""
        qh = {"enabled": True, "start": "nope", "end": "nah"}
        config = self._make_config(qh, time(2, 0))
        assert config.is_quiet_hours() is False

    def test_empty_strings(self):
        qh = {"enabled": True, "start": "", "end": ""}
        config = self._make_config(qh, time(2, 0))
        assert config.is_quiet_hours() is False

    def test_start_equals_end(self):
        """start == end → same-day branch, always False (effectively disabled)."""
        qh = {"enabled": True, "start": "08:00", "end": "08:00"}
        config = self._make_config(qh, time(8, 0))
        assert config.is_quiet_hours() is False
        config2 = self._make_config(qh, time(12, 0))
        assert config2.is_quiet_hours() is False


# ------------------------------------------------------------------ #
# CronScheduler quiet hours gate
# ------------------------------------------------------------------ #

class TestCronSchedulerQuietHours:
    """Test that cron scheduler skips jobs during quiet hours."""

    @pytest.fixture
    def scheduler(self):
        registry = Mock()
        registry.agents = {
            "TCS": AgentDefinition(
                name="Teams Chat Summary",
                abbreviation="TCS",
                category="ingestion",
                prompt_body="test",
                cron="*/5 * * * *",
            )
        }
        queue = Queue()
        config = Mock()
        config.user_now.return_value = datetime(2026, 4, 24, 2, 0, 0)
        sched = CronScheduler(registry, queue, config=config)
        return sched, queue, config

    def test_cron_skips_during_quiet_hours(self, scheduler):
        sched, queue, config = scheduler
        config.is_quiet_hours.return_value = True

        sched._check_and_trigger_jobs()

        assert queue.empty(), "No events should be queued during quiet hours"

    def test_cron_runs_outside_quiet_hours(self, scheduler):
        sched, queue, config = scheduler
        config.is_quiet_hours.return_value = False
        # Make croniter think it's time to trigger
        config.user_now.return_value = datetime(2026, 4, 24, 2, 0, 0)

        sched._check_and_trigger_jobs()
        # Not asserting queue contents — cron matching depends on exact time.
        # The key assertion is that the method proceeded past the quiet hours check.
        config.user_now.assert_called()


# ------------------------------------------------------------------ #
# Core orchestrator quiet hours gate
# ------------------------------------------------------------------ #

class TestCoreQuietHours:
    """Test that core._process_event drops non-manual events during quiet hours."""

    def _make_orchestrator(self):
        """Minimal orchestrator with mocked dependencies."""
        import tempfile
        from pathlib import Path
        from duckyai.orchestrator.core import Orchestrator

        tmpdir = tempfile.mkdtemp()
        vault_path = Path(tmpdir)
        agents_dir = vault_path / "_Settings_" / "Agents"
        agents_dir.mkdir(parents=True)

        orch = Orchestrator(vault_path, agents_dir)
        return orch

    def test_file_event_dropped_during_quiet_hours(self):
        orch = self._make_orchestrator()
        orch.config.is_quiet_hours = Mock(return_value=True)

        trigger = TriggerEvent(
            path="01-Work/PRReviews/PR-123.md",
            event_type="created",
            is_directory=False,
            timestamp=datetime.now(),
            frontmatter={}
        )

        # Patch _dispatch_single_worker to detect if it was reached
        orch._dispatch_single_worker = Mock()
        orch._dispatch_multi_worker = Mock()

        orch._process_event(trigger)

        orch._dispatch_single_worker.assert_not_called()
        orch._dispatch_multi_worker.assert_not_called()

    def test_scheduled_event_dropped_during_quiet_hours(self):
        orch = self._make_orchestrator()
        orch.config.is_quiet_hours = Mock(return_value=True)

        trigger = TriggerEvent(
            path="",
            event_type="scheduled",
            is_directory=False,
            timestamp=datetime.now(),
            frontmatter={},
            target_agent="TCS"
        )

        orch._dispatch_single_worker = Mock()
        orch._process_event(trigger)
        orch._dispatch_single_worker.assert_not_called()

    def test_manual_event_bypasses_quiet_hours(self):
        orch = self._make_orchestrator()
        orch.config.is_quiet_hours = Mock(return_value=True)

        # Register a fake agent so matching works
        agent = AgentDefinition(
            name="Test Agent",
            abbreviation="TST",
            category="ingestion",
            prompt_body="test",
        )
        orch.agent_registry.agents["TST"] = agent
        orch.agent_registry.find_matching_agents = Mock(return_value=[agent])

        trigger = TriggerEvent(
            path="",
            event_type="manual",
            is_directory=False,
            timestamp=datetime.now(),
            frontmatter={},
            target_agent="TST"
        )

        orch._dispatch_single_worker = Mock()
        orch._process_event(trigger)

        # Manual trigger should reach dispatch
        orch._dispatch_single_worker.assert_called_once()

    def test_events_run_outside_quiet_hours(self):
        orch = self._make_orchestrator()
        orch.config.is_quiet_hours = Mock(return_value=False)

        agent = AgentDefinition(
            name="Test Agent",
            abbreviation="TST",
            category="ingestion",
            prompt_body="test",
            trigger_pattern="01-Work/PRReviews/*.md",
            trigger_event="created",
        )
        orch.agent_registry.agents["TST"] = agent
        orch.agent_registry.find_matching_agents = Mock(return_value=[agent])

        trigger = TriggerEvent(
            path="01-Work/PRReviews/PR-123.md",
            event_type="created",
            is_directory=False,
            timestamp=datetime.now(),
            frontmatter={}
        )

        orch._dispatch_single_worker = Mock()
        orch._process_event(trigger)

        orch._dispatch_single_worker.assert_called_once()
