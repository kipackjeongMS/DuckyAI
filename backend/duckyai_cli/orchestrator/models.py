"""
Data models for orchestrator components.
"""
from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any
import uuid


def _field_default(field_def):
    """Return a dataclass field's default value, honoring default factories."""
    if field_def.default_factory is not MISSING:
        return field_def.default_factory()
    if field_def.default is not MISSING:
        return field_def.default
    return None


@dataclass
class WorkerConfig:
    """Configuration for a single worker in a multi-worker agent."""
    executor: str  # claude_code, gemini_cli, etc.
    label: str     # Human-readable label (e.g., "Claude", "Gemini")
    agent_params: Dict[str, Any] = field(default_factory=dict)
    output_path: Optional[str] = None  # Worker-specific output directory


@dataclass(init=False)
class AgentDefinition:
    """Represents a loaded agent definition."""
    # Basic identity
    name: str = ""
    abbreviation: str = ""
    category: str = ""  # ingestion, publish, research

    # Trigger specification
    trigger_pattern: str = ""
    trigger_event: str = "manual"
    trigger_exclude_pattern: Optional[str] = None
    trigger_content_pattern: Optional[str] = None  # Regex pattern to match in file content
    trigger_schedule: Optional[str] = None
    trigger_wait_for: List[str] = field(default_factory=list)
    require_parent_output: bool = False  # If True, skip dispatch when no parent produced output

    # Input/output
    input_path: List[str] = field(default_factory=list)
    cron: Optional[str] = None  # Cron expression for scheduled triggers
    input_type: str = "new_file"
    output_path: str = ""
    output_type: str = "new_file"
    output_optional: bool = False  # If True, no output is acceptable (auto-inferred from input_path)
    output_naming: str = "{title} - {agent}.md"
    requires_input_file: bool = True  # If False, agent fetches its own data (e.g., TCS, GDR)

    # Execution
    prompt_body: str = ""
    skills: List[str] = field(default_factory=list)
    mcp_servers: List[str] = field(default_factory=list)
    executor: str = "claude_code"
    max_parallel: int = 1
    timeout_minutes: int = 30
    workers: List[WorkerConfig] = field(default_factory=list)  # Multi-worker execution

    # Container isolation override (None = use global setting)
    use_container: Optional[bool] = None

    # Per-agent extra volume mounts for Docker containers
    # List of dicts: [{"source": "path", "target": "/mount", "readonly": true}]
    extra_mounts: List[Dict[str, Any]] = field(default_factory=list)

    # Post-processing
    post_process_action: Optional[str] = None  # e.g., "remove_trigger_content"

    # Logging
    log_prefix: str = ""
    log_pattern: str = "{timestamp}-{agent}.log"

    # Task file configuration
    task_create: bool = True  # Whether to create task tracking files
    task_priority: str = "medium"  # low, medium, high
    task_archived: bool = False  # Default archived status

    # Metadata
    file_path: Optional[Path] = None
    version: str = "1.0"
    last_updated: Optional[datetime] = None

    system_prompt: Optional[str] = None
    system_prompt_file: Optional[Path] = None
    append_system_prompt: Optional[str] = None
    append_system_prompt_file: Optional[Path] = None
    
    # Agent-specific parameters from duckyai.yml
    agent_params: Dict[str, Any] = field(default_factory=dict)

    def __init__(self, name: Optional[str] = None, **kwargs: Any):
        legacy_title = kwargs.pop("title", None)
        resolved_name = name or legacy_title or kwargs.get("abbreviation", "")
        kwargs["name"] = resolved_name

        for field_def in fields(self.__class__):
            if field_def.name in kwargs:
                value = kwargs.pop(field_def.name)
            else:
                value = _field_default(field_def)
            setattr(self, field_def.name, value)

        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise TypeError(f"Unexpected AgentDefinition arguments: {unexpected}")

    @property
    def title(self) -> str:
        """Backward-compatible alias for older tests and call sites."""
        return self.name

    @title.setter
    def title(self, value: str):
        self.name = value


@dataclass(init=False)
class ExecutionContext:
    """Context for a single agent execution."""
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None  # Optional session ID for tracking related executions
    resume_session: bool = False  # If True, resume existing session; if False, create new session
    agent: Optional[AgentDefinition] = None
    trigger_data: Dict[str, Any] = field(default_factory=dict)

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Execution results
    status: str = "pending"  # pending, completed, failed, timeout
    output_produced: bool = False  # Whether the execution produced output (set during validation)
    prompt: Optional[str] = None
    error_message: Optional[str] = None
    response: Optional[str] = None
    token_usage: Optional[Dict[str, Any]] = None  # Per-model token usage from SDK

    # File paths
    log_file: Optional[Path] = None
    task_file: Optional[Path] = None  # Path to task tracking file in <vault>/.duckyai/tasks/

    system_prompt: Optional[str] = None
    system_prompt_file: Optional[Path] = None
    append_system_prompt: Optional[str] = None
    append_system_prompt_file: Optional[Path] = None

    def __init__(self, **kwargs: Any):
        legacy_timestamp = kwargs.pop("timestamp", None)
        legacy_agent_abbreviation = kwargs.pop("agent_abbreviation", None)

        if legacy_timestamp is not None and "start_time" not in kwargs:
            kwargs["start_time"] = legacy_timestamp

        if legacy_agent_abbreviation and "agent" not in kwargs:
            kwargs["agent"] = AgentDefinition(
                name=legacy_agent_abbreviation,
                abbreviation=legacy_agent_abbreviation,
                category="legacy",
            )

        for field_def in fields(self.__class__):
            if field_def.name in kwargs:
                value = kwargs.pop(field_def.name)
            else:
                value = _field_default(field_def)
            setattr(self, field_def.name, value)

        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise TypeError(f"Unexpected ExecutionContext arguments: {unexpected}")

    @property
    def timestamp(self) -> Optional[datetime]:
        """Backward-compatible alias for older tests and call sites."""
        return self.start_time

    @timestamp.setter
    def timestamp(self, value: Optional[datetime]):
        self.start_time = value

    @property
    def agent_abbreviation(self) -> Optional[str]:
        """Backward-compatible alias for older tests and call sites."""
        return self.agent.abbreviation if self.agent else None

    @agent_abbreviation.setter
    def agent_abbreviation(self, value: Optional[str]):
        if value is None:
            self.agent = None
        elif self.agent is None:
            self.agent = AgentDefinition(name=value, abbreviation=value, category="legacy")
        else:
            self.agent.abbreviation = value

    @property
    def duration(self) -> Optional[float]:
        """Execution duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def success(self) -> bool:
        """Whether execution succeeded."""
        return self.status == "completed" and self.error_message is None


@dataclass
class TriggerEvent:
    """Represents a trigger event (file system or scheduled)."""
    path: str
    event_type: str  # created, modified, deleted, scheduled
    is_directory: bool
    timestamp: datetime
    frontmatter: Dict[str, Any] = field(default_factory=dict)
