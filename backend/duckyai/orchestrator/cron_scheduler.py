"""
Cron scheduler for orchestrator.

Handles time-based agent execution using cron expressions.
Re-implements cron logic within orchestrator folder.
"""
import threading
import time
from datetime import datetime
from queue import Queue
from typing import Optional
from croniter import croniter

from .models import TriggerEvent
from .agent_registry import AgentRegistry
from ..logger import Logger

logger = Logger()


class CronScheduler:
    """
    Manages cron-based scheduling for agents with cron expressions.
    
    Checks every minute if any agents should be triggered based on their cron expressions.
    Creates synthetic TriggerEvent objects and queues them for processing.
    """

    COOLDOWN_SECONDS = 600  # 10-minute cooldown to prevent duplicate runs

    def __init__(self, agent_registry: AgentRegistry, event_queue: Queue, config=None):
        """
        Initialize cron scheduler.

        Args:
            agent_registry: AgentRegistry instance to get agents with cron expressions
            event_queue: Queue to put scheduled TriggerEvent objects
            config: Config instance for user timezone
        """
        from ..config import Config
        self.agent_registry = agent_registry
        self.event_queue = event_queue
        self.config = config or Config()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._cooldowns: dict[str, float] = {}  # agent_abbr -> last_run_timestamp

    def start(self):
        """Start the cron scheduler thread."""
        if self._running:
            logger.warning("Cron scheduler already running")
            return

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        logger.info("Cron scheduler started")

    def stop(self):
        """Stop the cron scheduler thread."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        logger.info("Cron scheduler stopped")

    def _scheduler_loop(self):
        """
        Main scheduler loop that checks cron expressions every minute.
        """
        logger.info("Cron scheduler loop started")

        while self._running:
            try:
                self._check_and_trigger_jobs()
                # Sleep for 60 seconds (1 minute)
                if self._stop_event.wait(60):
                    break
            except Exception as e:
                logger.error(f"Error in cron scheduler loop: {e}", exc_info=True)
                if self._stop_event.wait(60):
                    break

        logger.info("Cron scheduler loop stopped")

    def _check_and_trigger_jobs(self):
        """
        Check if any agents with cron expressions should be triggered now.
        """
        # Quiet hours — skip all cron checks
        if self.config.is_quiet_hours():
            logger.debug("Quiet hours active — skipping cron check")
            return

        now = self.config.user_now()

        # Get all agents with cron expressions
        agents_with_cron = [
            agent for agent in self.agent_registry.agents.values()
            if agent.cron is not None
        ]

        if not agents_with_cron:
            return

        for agent in agents_with_cron:
            logger.debug(f"Checking cron job: {agent.name} ({agent.cron})")
            try:
                # Check cooldown — skip if agent was recently triggered manually
                last_run = self._cooldowns.get(agent.abbreviation, 0)
                if (now.timestamp() - last_run) < self.COOLDOWN_SECONDS:
                    remaining = self.COOLDOWN_SECONDS - (now.timestamp() - last_run)
                    logger.debug(f"Skipping {agent.abbreviation}: cooldown active ({remaining:.0f}s remaining)")
                    continue

                # Check if this agent's cron expression should trigger now
                cron = croniter(agent.cron, now)
                prev_run = cron.get_prev(datetime)

                compare_now = now
                if prev_run.tzinfo is None:
                    compare_now = datetime.now()

                # If the previous run time is within the last minute, trigger the job
                time_diff = (compare_now - prev_run).total_seconds()
                if 0 <= time_diff <= 60:
                    logger.info(f"Triggering scheduled agent: {agent.abbreviation} ({agent.name})")
                    self._trigger_agent(agent)
            except Exception as e:
                logger.error(f"Error checking cron for agent {agent.abbreviation}: {e}")
    def _trigger_agent(self, agent):
        """
        Create a synthetic TriggerEvent for a scheduled agent and queue it.

        Args:
            agent: AgentDefinition with cron expression
        """
        # Create synthetic TriggerEvent for scheduled execution
        trigger_event = TriggerEvent(
            path="",  # No file path for scheduled events
            event_type="scheduled",
            is_directory=False,
            timestamp=self.config.user_now(),
            frontmatter={},
            target_agent=agent.abbreviation
        )

        # Queue the event for processing
        self.event_queue.put(trigger_event)
        logger.debug(f"Queued scheduled event for agent: {agent.abbreviation}")

    def set_cooldown(self, agent_abbreviation: str):
        """
        Set a cooldown for an agent to prevent duplicate cron triggers.

        Called after a manual/startup trigger so the next cron tick skips this agent.

        Args:
            agent_abbreviation: Agent abbreviation (e.g., "TCS")
        """
        self._cooldowns[agent_abbreviation] = time.time()
        logger.debug(f"Set cooldown for {agent_abbreviation} ({self.COOLDOWN_SECONDS}s)")

    def update_agent_registry(self, agent_registry: AgentRegistry):
        """
        Update the agent registry reference.
        
        Used during hot-reload to switch to new agent registry without restarting scheduler.
        
        Args:
            agent_registry: New AgentRegistry instance
        """
        self.agent_registry = agent_registry
        logger.debug("Cron scheduler agent registry updated")

