"""Configuration management for DuckyAI CLI (duckyai.yml)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from .logger import Logger

logger = Logger()

CONFIG_FILENAME = "duckyai.yml"
"""Canonical vault configuration filename."""


def get_global_runtime_dir(vault_id: Optional[str] = None, vault_path: Optional[Path] = None) -> Path:
    """Return the runtime directory for a vault: ``<vault_path>/.duckyai/``.

    Callers must provide *vault_path* so runtime state remains vault-local.
    Creates the directory tree on first access.
    """
    if vault_path is None:
        raise ValueError(
            "vault_path is required when resolving the runtime directory. "
            "Legacy ~/.duckyai/vaults fallback has been removed."
        )

    new_dir = Path(vault_path) / ".duckyai"
    new_dir.mkdir(parents=True, exist_ok=True)

    old_dir = Path.home() / ".duckyai" / "vaults" / (vault_id or "default")
    if old_dir.exists():
        logger.warning(
            f"Stale legacy runtime directory still exists: {old_dir}  "
            f"Active runtime root is: {new_dir}  "
            f"Delete the legacy directory manually if no other process uses it."
        )

    return new_dir


class Config:
    """Read vault configuration sourced from duckyai.yml."""

    def __init__(
        self,
        config_file: Optional[str] = None,
        vault_path: Optional[Path] = None,
    ):
        """
        Initialize configuration loader.

        Args:
            config_file: Explicit path to duckyai.yml (overrides vault_path)
            vault_path: Vault directory containing duckyai.yml
        """
        if config_file:
            self.config_path = Path(config_file)
            self.vault_path = self.config_path.parent
        else:
            base_path = Path(vault_path) if vault_path else Path.cwd()
            self.config_path = base_path / CONFIG_FILENAME
            self.vault_path = base_path

        self.config: Dict[str, Any] = self._load_config()

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge override dict into base dict."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _load_config(self) -> Dict[str, Any]:
        """Load duckyai.yml and merge with secrets.yaml if present."""
        config_data: Dict[str, Any] = {}

        if self.config_path.exists():
            try:
                with self.config_path.open("r", encoding="utf-8") as fh:
                    loaded = yaml.safe_load(fh) or {}
                    if not isinstance(loaded, dict):
                        logger.warning(
                            "duckyai.yml did not contain a mapping; falling back to defaults"
                        )
                    else:
                        config_data = loaded
            except yaml.YAMLError as exc:
                logger.error(f"Failed to parse duckyai.yml: {exc}")
            except OSError as exc:
                logger.error(f"Failed to read duckyai.yml: {exc}")
        else:
            logger.warning(f"duckyai.yml not found at {self.config_path}")

        secrets_path = self.config_path.parent / "secrets.yaml"
        if secrets_path.exists():
            try:
                with secrets_path.open("r", encoding="utf-8") as fh:
                    secrets = yaml.safe_load(fh) or {}
                    if isinstance(secrets, dict):
                        config_data = self._deep_merge(config_data, secrets)
                        logger.debug(f"Loaded secrets from {secrets_path}")
                    else:
                        logger.warning(f"secrets.yaml did not contain a mapping")
            except yaml.YAMLError as exc:
                logger.error(f"Failed to parse secrets.yaml: {exc}")
            except OSError as exc:
                logger.error(f"Failed to read secrets.yaml: {exc}")

        return config_data

    def reload(self) -> bool:
        """
        Reload duckyai.yml and secrets.yaml from disk.
        
        Returns:
            True if reload succeeded, False otherwise
        """
        try:
            new_config = self._load_config()
            if new_config:
                self.config = new_config
                logger.info(f"Configuration reloaded from {self.config_path}")
                return True
            else:
                logger.warning("Reload resulted in empty config, keeping existing config")
                return False
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}", exc_info=True)
            return False

    # --------------------------------------------------------------------- #
    # Public accessors
    # --------------------------------------------------------------------- #
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a dotted-path value from configuration."""
        if not key:
            return self.config

        value: Any = self.config
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def get_orchestrator_config(self) -> Dict[str, Any]:
        """Get entire orchestrator runtime configuration section."""
        section = self.get("orchestrator", {})
        return section.copy() if isinstance(section, dict) else {}

    def get_playbook_dir(self) -> Path:
        """Get the CLI package's built-in .playbook directory path."""
        from pathlib import Path
        return Path(__file__).parent / '.playbook'

    def get_orchestrator_prompts_dir(self) -> str:
        """Directory containing agent prompt definitions."""
        return self.get(
            "orchestrator.prompts_dir",
            ".github/prompts-agent",
        )

    def get_orchestrator_tasks_dir(self) -> str:
        """Directory containing task tracking files.

        Defaults to ``<vault_path>/.duckyai/tasks``.
        """
        configured = self.get("orchestrator.tasks_dir")
        if configured:
            return configured
        vault_id = self.get("id", "default")
        return str(get_global_runtime_dir(vault_id, vault_path=self.vault_path) / "tasks")

    def get_orchestrator_logs_dir(self) -> str:
        """Directory where orchestrator writes execution logs.

        Defaults to ``<vault_path>/.duckyai/logs``.
        """
        configured = self.get("orchestrator.logs_dir")
        if configured:
            return configured
        vault_id = self.get("id", "default")
        return str(get_global_runtime_dir(vault_id, vault_path=self.vault_path) / "logs")

    def get_orchestrator_skills_dir(self) -> str:
        """Directory for orchestrator skills library."""
        return self.get(
            "orchestrator.skills_dir",
            ".github/skills",
        )

    def get_orchestrator_bases_dir(self) -> str:
        """Directory for orchestrator knowledge bases."""
        return self.get(
            "orchestrator.bases_dir",
            ".github/bases",
        )

    def get_orchestrator_max_concurrent(self) -> int:
        """Maximum global concurrent executions."""
        return self.get(
            "orchestrator.max_concurrent",
            3,
        )

    def get_orchestrator_poll_interval(self) -> float:
        """Event queue poll interval in seconds."""
        return self.get(
            "orchestrator.poll_interval",
            1.0,
        )

    def get_defaults(self) -> Dict[str, Any]:
        """Global defaults applied to agents."""
        section = self.get("defaults", {})
        return section.copy() if isinstance(section, dict) else {}

    def get_nodes(self) -> Any:
        """Return configured nodes list."""
        nodes = self.get("nodes", [])
        return nodes if isinstance(nodes, list) else []

    def get_pollers_config(self) -> Dict[str, Any]:
        """Get pollers configuration section."""
        section = self.get("pollers", {})
        return section.copy() if isinstance(section, dict) else {}

    # --------------------------------------------------------------------- #
    # User / workspace accessors (previously in WorkspaceConfig)
    # --------------------------------------------------------------------- #
    @property
    def orchestrator_auto_start(self) -> bool:
        """Whether the orchestrator daemon should auto-start."""
        return bool(self.get("orchestrator.auto_start", True))

    def get_user_name(self) -> str:
        return self.get("user.name", "")

    def get_user_primary_language(self) -> str:
        return self.get("user.primaryLanguage", "en")

    # Common Windows → IANA timezone mappings
    _WINDOWS_TZ_MAP = {
        "Pacific Standard Time": "America/Los_Angeles",
        "Mountain Standard Time": "America/Denver",
        "Central Standard Time": "America/Chicago",
        "Eastern Standard Time": "America/New_York",
        "UTC": "UTC",
        "GMT Standard Time": "Europe/London",
        "Central European Standard Time": "Europe/Berlin",
        "China Standard Time": "Asia/Shanghai",
        "Tokyo Standard Time": "Asia/Tokyo",
        "Korea Standard Time": "Asia/Seoul",
        "AUS Eastern Standard Time": "Australia/Sydney",
        "India Standard Time": "Asia/Kolkata",
        "Hawaiian Standard Time": "Pacific/Honolulu",
        "Alaskan Standard Time": "America/Anchorage",
        "Atlantic Standard Time": "America/Halifax",
    }

    def get_user_timezone(self) -> str:
        """Return the user's timezone as an IANA name.

        Priority: duckyai.yml ``user.timezone`` → OS local timezone via tzlocal → ``"UTC"``.
        Automatically converts Windows timezone names to IANA equivalents.
        """
        configured = self.get("user.timezone")
        if configured:
            # Map Windows timezone name to IANA if needed
            return self._WINDOWS_TZ_MAP.get(configured, configured)
        try:
            from tzlocal import get_localzone
            return str(get_localzone())
        except Exception:
            return "UTC"

    def user_now(self) -> 'datetime':
        """Return the current datetime in the user's configured timezone.

        Reads ``user.timezone`` from duckyai.yml (e.g. ``America/Los_Angeles``).
        Falls back to OS local timezone, then UTC.
        """
        from datetime import datetime, timezone
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo

        tz_name = self.get_user_timezone()
        try:
            tz = ZoneInfo(tz_name)
        except (KeyError, Exception):
            # Configured name invalid — try OS local timezone
            try:
                from tzlocal import get_localzone
                tz = ZoneInfo(str(get_localzone()))
            except Exception:
                tz = timezone.utc
        return datetime.now(tz)

    # --------------------------------------------------------------------- #
    # Services accessors
    # --------------------------------------------------------------------- #
    def get_services_path(self) -> str:
        """Absolute path to the services directory for this vault.

        Reads ``services.path`` from config (may be relative to vault root).
        Falls back to ``<VaultParent>/<VaultName>-Services``.
        """
        configured = self.get("services.path")
        if configured:
            p = Path(configured)
            if not p.is_absolute() and self.vault_path:
                p = (self.vault_path / p).resolve()
            return str(p)
        # Default: sibling directory named <VaultDirName>-Services
        if self.vault_path:
            vault_dir = Path(self.vault_path).resolve()
            return str(vault_dir.parent / f"{vault_dir.name}-Services")
        return ""

    def get_services(self) -> list:
        """Return list of service entry dicts from ``services.entries``."""
        entries = self.get("services.entries", [])
        return entries if isinstance(entries, list) else []


# Backward-compatible alias — callers that imported WorkspaceConfig keep working.
WorkspaceConfig = Config
