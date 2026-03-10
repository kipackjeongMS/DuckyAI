"""Configuration management for DuckyAI CLI (orchestrator.yaml)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from .logger import Logger

logger = Logger()


def get_global_runtime_dir(vault_id: Optional[str] = None) -> Path:
    """Return the global runtime directory for a vault: ~/.duckyai/vaults/{vault_id}/.

    If *vault_id* is ``None``, falls back to ``"default"``.
    Creates the directory tree on first access.
    """
    base = Path.home() / ".duckyai" / "vaults" / (vault_id or "default")
    base.mkdir(parents=True, exist_ok=True)
    return base


class Config:
    """Read orchestrator configuration sourced from orchestrator.yaml."""

    def __init__(
        self,
        config_file: Optional[str] = None,
        vault_path: Optional[Path] = None,
    ):
        """
        Initialize configuration loader.

        Args:
            config_file: Explicit path to orchestrator.yaml (overrides vault_path)
            vault_path: Vault directory containing orchestrator.yaml
        """
        if config_file:
            self.config_path = Path(config_file)
        else:
            base_path = Path(vault_path) if vault_path else Path.cwd()
            self.config_path = base_path / "orchestrator.yaml"

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
        """Load orchestrator.yaml and merge with secrets.yaml if present."""
        config_data: Dict[str, Any] = {}

        if self.config_path.exists():
            try:
                with self.config_path.open("r", encoding="utf-8") as fh:
                    loaded = yaml.safe_load(fh) or {}
                    if not isinstance(loaded, dict):
                        logger.warning(
                            "orchestrator.yaml did not contain a mapping; falling back to defaults"
                        )
                    else:
                        config_data = loaded
            except yaml.YAMLError as exc:
                logger.error(f"Failed to parse orchestrator.yaml: {exc}")
            except OSError as exc:
                logger.error(f"Failed to read orchestrator.yaml: {exc}")
        else:
            logger.warning(f"orchestrator.yaml not found at {self.config_path}")

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
        Reload orchestrator.yaml and secrets.yaml from disk.
        
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

        Defaults to ``~/.duckyai/vaults/{vault_id}/tasks``.
        """
        configured = self.get("orchestrator.tasks_dir")
        if configured:
            return configured
        vault_id = self.get("id", "default")
        return str(get_global_runtime_dir(vault_id) / "tasks")

    def get_orchestrator_logs_dir(self) -> str:
        """Directory where orchestrator writes execution logs.

        Defaults to ``~/.duckyai/vaults/{vault_id}/logs``.
        """
        configured = self.get("orchestrator.logs_dir")
        if configured:
            return configured
        vault_id = self.get("id", "default")
        return str(get_global_runtime_dir(vault_id) / "logs")

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


class WorkspaceConfig:
    """Read user-facing workspace configuration from duckyai.yaml."""

    DEFAULTS: Dict[str, Any] = {
        "orchestrator": {
            "auto_start": True,
        },
    }

    def __init__(self, vault_path: Optional[Path] = None):
        base_path = Path(vault_path) if vault_path else Path.cwd()
        self.config_path = base_path / "duckyai.yaml"
        self.config: Dict[str, Any] = self._load()

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _load(self) -> Dict[str, Any]:
        config_data: Dict[str, Any] = {}
        if self.config_path.exists():
            try:
                with self.config_path.open("r", encoding="utf-8") as fh:
                    loaded = yaml.safe_load(fh) or {}
                    if isinstance(loaded, dict):
                        config_data = loaded
            except (yaml.YAMLError, OSError):
                pass
        return self._deep_merge(self.DEFAULTS, config_data)

    def get(self, key: str, default: Any = None) -> Any:
        value: Any = self.config
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    @property
    def orchestrator_auto_start(self) -> bool:
        return bool(self.get("orchestrator.auto_start", True))