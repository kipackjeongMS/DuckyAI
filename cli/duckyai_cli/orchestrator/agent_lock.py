"""
Cross-process file-based agent lock.

Prevents the same agent type from running concurrently for a vault,
even across separate terminal sessions or processes.

Lock files live at: <vault>/.duckyai/locks/<AGENT_ABBR>.lock
Each lock file contains JSON: {"pid": <int>, "acquired_at": <iso>, "agent": <str>}
"""
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from ..logger import Logger

logger = Logger()

# Stale lock threshold — if a lock's process is dead OR older than this, steal it
LOCK_TTL_SECONDS = 30 * 60  # 30 minutes


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with given PID is still running."""
    if pid <= 0:
        return False
    try:
        # On Windows, os.kill(pid, 0) doesn't work reliably — use ctypes
        if os.name == 'nt':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except (OSError, PermissionError):
        return False


def _locks_dir(vault_path: Path) -> Path:
    """Get the locks directory for a vault."""
    d = vault_path / ".duckyai" / "locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def acquire_agent_lock(vault_path: Path, agent_abbr: str) -> bool:
    """
    Attempt to acquire a file-based lock for an agent.

    Returns True if lock acquired, False if another process holds it.
    Stale locks (dead process or TTL expired) are automatically cleaned.
    """
    lock_file = _locks_dir(vault_path) / f"{agent_abbr}.lock"

    # Check existing lock
    if lock_file.exists():
        try:
            data = json.loads(lock_file.read_text(encoding="utf-8"))
            holder_pid = data.get("pid", -1)
            acquired_at = data.get("acquired_at", "")

            # Check if holder is still alive
            if _is_pid_alive(holder_pid):
                # Check TTL
                try:
                    lock_time = datetime.fromisoformat(acquired_at)
                    age = (datetime.now(timezone.utc) - lock_time).total_seconds()
                    if age < LOCK_TTL_SECONDS:
                        logger.warning(
                            f"Agent {agent_abbr} is already running (PID {holder_pid}, "
                            f"age {age:.0f}s). Skipping.",
                            console=True
                        )
                        return False
                    else:
                        logger.warning(
                            f"Stealing stale lock for {agent_abbr} "
                            f"(PID {holder_pid} alive but lock age {age:.0f}s > TTL {LOCK_TTL_SECONDS}s)",
                            console=True
                        )
                except (ValueError, TypeError):
                    logger.warning(
                        f"Stealing lock for {agent_abbr} — malformed acquired_at",
                        console=True
                    )
            else:
                logger.info(
                    f"Cleaning stale lock for {agent_abbr} (PID {holder_pid} no longer alive)"
                )
        except (json.JSONDecodeError, KeyError):
            logger.info(f"Cleaning corrupted lock file for {agent_abbr}")

    # Write new lock
    lock_data = {
        "pid": os.getpid(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "agent": agent_abbr,
    }
    try:
        lock_file.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")
        logger.debug(f"Acquired lock for {agent_abbr} (PID {os.getpid()})")
        return True
    except OSError as e:
        logger.error(f"Failed to write lock file for {agent_abbr}: {e}")
        return False


def release_agent_lock(vault_path: Path, agent_abbr: str) -> None:
    """Release the file-based lock for an agent. Safe to call even if not held."""
    lock_file = _locks_dir(vault_path) / f"{agent_abbr}.lock"
    try:
        if lock_file.exists():
            # Only release if we own it
            data = json.loads(lock_file.read_text(encoding="utf-8"))
            if data.get("pid") == os.getpid():
                lock_file.unlink()
                logger.debug(f"Released lock for {agent_abbr}")
            else:
                logger.debug(
                    f"Lock for {agent_abbr} owned by PID {data.get('pid')}, not releasing"
                )
    except (json.JSONDecodeError, OSError) as e:
        # Best-effort cleanup
        try:
            lock_file.unlink(missing_ok=True)
        except OSError:
            pass
        logger.debug(f"Force-cleaned lock for {agent_abbr}: {e}")
