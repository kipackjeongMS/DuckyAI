"""Logging system with file output and real-time tail display."""

import os
import time
import logging
import threading
from pathlib import Path
from datetime import datetime
from threading import Lock
from rich.console import Console
from rich.text import Text


class Logger:
    """Logger that writes to logs.txt and supports real-time tail display."""

    _instances = {}
    _lock = Lock()

    def __new__(cls, log_file=None, console_output=False):
        """Singleton pattern: return same instance for same parameters."""
        # Create a key based on log_file and console_output
        key = (log_file, console_output)

        if key not in cls._instances:
            with cls._lock:
                # Double-check after acquiring lock
                if key not in cls._instances:
                    instance = super().__new__(cls)
                    cls._instances[key] = instance
                    instance._initialized = False
        return cls._instances[key]

    @staticmethod
    def _read_logs_dir_from_config():
        """Read logs directory from duckyai.yml without importing Config.

        Returns the configured ``orchestrator.logs_dir`` value, or the default
        ``~/.duckyai/vaults/{vault_id}/logs`` when the file is missing or unparseable.
        """
        vault_id = "default"
        default = os.path.join(str(Path.home()), ".duckyai", "vaults", vault_id, "logs")
        try:
            import yaml
            config_path = Path(os.getcwd()) / "duckyai.yml"
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                if isinstance(data, dict):
                    # Read vault_id for namespacing
                    vault_id = data.get("id", "default")
                    default = os.path.join(str(Path.home()), ".duckyai", "vaults", vault_id, "logs")
                    orch = data.get("orchestrator", {})
                    if isinstance(orch, dict):
                        return orch.get("logs_dir", default)
        except Exception:
            pass
        return default

    def __init__(self, log_file=None, console_output=False):
        """Initialize logger (only once per instance)."""
        if self._initialized:
            return

        if log_file is None:
            # Read logs directory from config (returns absolute path to global dir)
            logs_dir = self._read_logs_dir_from_config()
            if not os.path.isabs(logs_dir):
                logs_dir = os.path.join(os.getcwd(), logs_dir)

            # Ensure logs directory exists
            os.makedirs(logs_dir, exist_ok=True)

            # Create date-based log filename with duckyai prefix
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_file = os.path.join(logs_dir, f"duckyai_{date_str}.log")

        self.log_file = log_file
        self.lock = Lock()
        self.console_output = console_output
        self.console = Console()

        # Print log file path for user reference
        # print(f"📝 Log file: {os.path.abspath(self.log_file)}")

        self._ensure_log_file()

        self._initialized = True
        
    def _ensure_log_file(self):
        """Ensure log file exists and add header if it's a new file."""
        # Only write header if file doesn't exist
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(f"PKM CLI Log - Started at {datetime.now().isoformat()}\n")
                f.write("=" * 60 + "\n")

    def _write_log(self, level, message, exc_info=False, console=False):
        """Write log entry to file and optionally to console."""
        import traceback
        import sys

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
                # Log write failed (e.g., OneDrive sync lock) - fail silently
                # Optionally print to stderr as fallback
                import sys
                print(f"[Logger] Failed to write to log file: {e}", file=sys.stderr)

            # Print to console if requested
            if console or self.console_output or logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                try:
                    self.console.print(message)
                except (UnicodeEncodeError, OSError):
                    # Detached/no-console processes may fail on Rich output — skip silently
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
