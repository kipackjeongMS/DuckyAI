"""Logging system with file output and real-time tail display."""

import os
import sys
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta
from threading import Lock
from rich.console import Console
from rich.text import Text

# Numeric level constants (matching stdlib logging for familiarity)
_LEVEL_MAP = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
_DEFAULT_LEVEL = "INFO"
_DEFAULT_RETENTION_DAYS = 30


class Logger:
    """Logger that writes to a daily log file and supports Rich console output."""

    _instances = {}
    _lock = Lock()

    def __new__(cls, log_file=None, console_output=False):
        """Singleton pattern: return same instance for same parameters."""
        key = (log_file, console_output)

        if key not in cls._instances:
            with cls._lock:
                if key not in cls._instances:
                    instance = super().__new__(cls)
                    cls._instances[key] = instance
                    instance._initialized = False
        return cls._instances[key]

    @staticmethod
    def _read_config_from_yml():
        """Read orchestrator config from duckyai.yml without importing Config.

        Returns a dict with ``logs_dir``, ``log_level``, and
        ``log_retention_days`` keys (all with sensible defaults).
        """
        vault_root = Path(os.getcwd())
        default_dir = os.path.join(str(vault_root), ".duckyai", "logs")
        if not (vault_root / ".duckyai").exists():
            default_dir = os.path.join(str(Path.home()), ".duckyai", "logs")

        result = {
            "logs_dir": default_dir,
            "log_level": _DEFAULT_LEVEL,
            "log_retention_days": _DEFAULT_RETENTION_DAYS,
        }
        try:
            import yaml
            config_path = vault_root / ".duckyai" / "duckyai.yml"
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                if isinstance(data, dict):
                    orch = data.get("orchestrator", {})
                    if isinstance(orch, dict):
                        result["logs_dir"] = orch.get("logs_dir", default_dir)
                        result["log_level"] = orch.get("log_level", _DEFAULT_LEVEL)
                        result["log_retention_days"] = orch.get(
                            "log_retention_days", _DEFAULT_RETENTION_DAYS
                        )
        except Exception as exc:
            print(
                f"[Logger] Could not read duckyai.yml: {exc}",
                file=sys.stderr,
            )
        return result

    @staticmethod
    def _resolve_level(yml_level):
        """Return the effective numeric log level.

        Priority: DUCKYAI_LOG_LEVEL env var > yml_level argument.
        """
        raw = os.environ.get("DUCKYAI_LOG_LEVEL", yml_level or _DEFAULT_LEVEL)
        return _LEVEL_MAP.get(raw.upper(), _LEVEL_MAP[_DEFAULT_LEVEL])

    def __init__(self, log_file=None, console_output=False):
        """Initialize logger (only once per instance)."""
        if self._initialized:
            return

        cfg = self._read_config_from_yml()
        self._level = self._resolve_level(cfg["log_level"])
        self._retention_days = int(cfg["log_retention_days"])

        if log_file is None:
            logs_dir = cfg["logs_dir"]
            if not os.path.isabs(logs_dir):
                logs_dir = os.path.join(os.getcwd(), logs_dir)

            os.makedirs(logs_dir, exist_ok=True)

            date_str = datetime.now().strftime("%Y-%m-%d")
            log_file = os.path.join(logs_dir, f"duckyai_{date_str}.log")

        self.log_file = log_file
        self.lock = Lock()
        self.console_output = console_output
        self.console = Console()

        self._ensure_log_file()
        self._cleanup_old_logs()

        self._initialized = True

    def reconfigure(self, vault_path):
        """Re-resolve log directory for a specific vault path.

        Call this after vault resolution to ensure logs go to the correct
        vault's log directory instead of the 'default' fallback.
        """
        try:
            import yaml
            config_path = Path(vault_path) / ".duckyai" / "duckyai.yml"
            if not config_path.exists():
                return

            with config_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                return

            logs_dir = os.path.join(str(vault_path), ".duckyai", "logs")

            orch = data.get("orchestrator", {})
            if isinstance(orch, dict):
                if "logs_dir" in orch:
                    logs_dir = orch["logs_dir"]
                self._level = self._resolve_level(
                    orch.get("log_level", _DEFAULT_LEVEL)
                )
                self._retention_days = int(
                    orch.get("log_retention_days", _DEFAULT_RETENTION_DAYS)
                )

            if not os.path.isabs(logs_dir):
                logs_dir = os.path.join(str(vault_path), logs_dir)

            os.makedirs(logs_dir, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            new_log_file = os.path.join(logs_dir, f"duckyai_{date_str}.log")

            with self.lock:
                self.log_file = new_log_file
            self._ensure_log_file()
            self._cleanup_old_logs()
        except Exception as exc:
            print(
                f"[Logger] reconfigure failed (keeping existing log path): {exc}",
                file=sys.stderr,
            )

    def set_level(self, level_name):
        """Set the log level at runtime (e.g. from --debug flag)."""
        self._level = _LEVEL_MAP.get(level_name.upper(), _LEVEL_MAP[_DEFAULT_LEVEL])

    def _ensure_log_file(self):
        """Ensure log file exists and add header if it's a new file."""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(f"DuckyAI Log - Started at {datetime.now().isoformat()}\n")
                f.write("=" * 60 + "\n")

    def _cleanup_old_logs(self):
        """Delete log files older than retention_days."""
        try:
            logs_dir = os.path.dirname(self.log_file)
            if not os.path.isdir(logs_dir):
                return
            cutoff = datetime.now() - timedelta(days=self._retention_days)
            for entry in os.scandir(logs_dir):
                if not entry.is_file():
                    continue
                # Daily logs: duckyai_YYYY-MM-DD.log
                name = entry.name
                if name.startswith("duckyai_") and name.endswith(".log"):
                    date_part = name[len("duckyai_"):-len(".log")]
                    try:
                        file_date = datetime.strptime(date_part, "%Y-%m-%d")
                        if file_date < cutoff:
                            os.remove(entry.path)
                    except ValueError:
                        pass
            # Agent subdirectory logs
            for subdir in os.scandir(logs_dir):
                if not subdir.is_dir():
                    continue
                for entry in os.scandir(subdir.path):
                    if entry.is_file() and entry.name.endswith(".log"):
                        try:
                            mtime = datetime.fromtimestamp(entry.stat().st_mtime)
                            if mtime < cutoff:
                                os.remove(entry.path)
                        except OSError:
                            pass
        except OSError:
            pass  # Non-critical: best-effort cleanup

    def _write_log(self, level, message, exc_info=False, console=False):
        """Write log entry to file and optionally to console."""
        import traceback

        numeric = _LEVEL_MAP.get(level, 0)
        if numeric < self._level:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        thread_name = threading.current_thread().name
        thread_prefix = f"[{thread_name}] "
        log_entry = f"[{timestamp}] {thread_prefix}{level}: {message}\n"

        if exc_info:
            exc_type, exc_value, exc_tb = sys.exc_info()
            if exc_type is not None:
                tb_lines = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
                if tb_lines.strip():
                    log_entry += tb_lines

        with self.lock:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(log_entry)
            except (PermissionError, OSError) as e:
                print(f"[Logger] Failed to write to log file: {e}", file=sys.stderr)

            if console or self.console_output or self._level <= _LEVEL_MAP["DEBUG"]:
                try:
                    self.console.print(message)
                except (UnicodeEncodeError, OSError):
                    pass
                
    def info(self, message, exc_info=False, console=False):
        """Log info message.
        
        Args:
            message: Message to log
            exc_info: Include exception traceback if True
            console: Print to console (message only, no formatting) if True
        """
        self._write_log("INFO", message, exc_info=exc_info, console=console)
        
    def error(self, message, exc_info=False, console=False):
        """Log error message.
        
        Args:
            message: Message to log
            exc_info: Include exception traceback if True
            console: Print to console (message only, no formatting) if True
        """
        self._write_log("ERROR", message, exc_info=exc_info, console=console)
        
    def warning(self, message, exc_info=False, console=False):
        """Log warning message.
        
        Args:
            message: Message to log
            exc_info: Include exception traceback if True
            console: Print to console (message only, no formatting) if True
        """
        self._write_log("WARNING", message, exc_info=exc_info, console=console)
        
    def debug(self, message, exc_info=False, console=False):
        """Log debug message.
        
        Args:
            message: Message to log
            exc_info: Include exception traceback if True
            console: Print to console (message only, no formatting) if True
        """
        self._write_log("DEBUG", message, exc_info=exc_info, console=console)
