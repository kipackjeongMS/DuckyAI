"""Home vault configuration stored in ~/.duckyai/config.json.

Compatibility helpers still expose list/register/find semantics, but they now
operate on a single configured home vault stored only in config.json.
"""

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


CONFIG_PATH = Path.home() / ".duckyai" / "config.json"


def _empty_config() -> Dict[str, Any]:
    """Return the default home-vault configuration structure."""
    return {"home_vault": None}


def _normalize_entry(entry: Dict[str, Any]) -> Dict[str, str]:
    """Normalize a vault entry to the public shape used by callers."""
    normalized = {
        "id": entry.get("id") or "default",
        "name": entry.get("name") or Path(entry.get("path") or ".").name,
        "path": str(Path(entry.get("path") or ".").resolve()),
    }
    if entry.get("last_used"):
        normalized["last_used"] = entry["last_used"]
    if entry.get("services_path"):
        normalized["services_path"] = entry["services_path"]
    return normalized


def _load_config() -> Dict[str, Any]:
    """Load the home-vault config from config.json."""
    if not CONFIG_PATH.exists():
        return _empty_config()

    for attempt in range(3):
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("home_vault", None)
                return data
        except (json.JSONDecodeError, OSError):
            if attempt < 2:
                time.sleep(0.05)
                continue
    return _empty_config()


def _save_config(data: Dict[str, Any]) -> None:
    """Write home-vault config to disk atomically.

    Writes to a temp file in the same directory, then uses os.replace()
    which is atomic on NTFS (Windows) and POSIX filesystems. This prevents
    concurrent readers from seeing a truncated/empty file.
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False)
    # Write to temp file in same directory, then atomic rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(CONFIG_PATH.parent), suffix=".tmp", prefix="config_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        # On Windows, os.replace() fails if the target is held open by another
        # process. Retry a few times with backoff to handle concurrent access.
        last_err = None
        for attempt in range(5):
            try:
                os.replace(tmp_path, str(CONFIG_PATH))
                return
            except PermissionError as e:
                last_err = e
                time.sleep(0.1 * (attempt + 1))
        # All retries exhausted — fall back to direct write (non-atomic but
        # better than crashing). The temp file is cleaned up below.
        try:
            CONFIG_PATH.write_text(content, encoding="utf-8")
        except OSError:
            if last_err:
                raise last_err
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def get_home_vault() -> Optional[Dict[str, str]]:
    """Return the configured home vault, if any."""
    entry = _load_config().get("home_vault")
    if not entry:
        return None
    return _normalize_entry(entry)


def set_home_vault(vault_id: str, name: str, path: Path, services_path: str = None) -> Dict[str, str]:
    """Persist the single home vault and return the normalized entry."""
    entry = {
        "id": vault_id,
        "name": name,
        "path": str(path.resolve()),
        "last_used": datetime.now().isoformat(),
    }
    if services_path is not None:
        entry["services_path"] = services_path

    data = _load_config()
    data["home_vault"] = entry
    _save_config(data)
    return _normalize_entry(entry)


def clear_home_vault() -> bool:
    """Clear the configured home vault. Returns True if one existed."""
    data = _load_config()
    existed = data.get("home_vault") is not None
    data["home_vault"] = None
    _save_config(data)
    return existed


def touch_vault(vault_id: str) -> None:
    """Update last_used for the home vault if it matches the given ID."""
    try:
        home = get_home_vault()
        if not home or home["id"] != vault_id:
            return
        set_home_vault(
            vault_id=home["id"],
            name=home["name"],
            path=Path(home["path"]),
            services_path=home.get("services_path"),
        )
    except (OSError, PermissionError):
        pass


