"""Global vault registry — tracks registered vaults in ~/.duckyai/vaults.json."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


REGISTRY_PATH = Path.home() / ".duckyai" / "vaults.json"


def _load_registry() -> Dict[str, Any]:
    """Load the registry file, returning empty structure if missing/corrupt."""
    if not REGISTRY_PATH.exists():
        return {"vaults": []}
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "vaults" in data:
            # Strip legacy "default" key if present
            data.pop("default", None)
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"vaults": []}


def _save_registry(data: Dict[str, Any]) -> None:
    """Write registry to disk."""
    data.pop("default", None)  # never persist default
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def list_vaults() -> List[Dict[str, str]]:
    """Return list of registered vault entries."""
    return _load_registry().get("vaults", [])


def find_vault_by_id(vault_id: str) -> Optional[Dict[str, str]]:
    """Find a registered vault by its ID."""
    for v in list_vaults():
        if v["id"] == vault_id:
            return v
    return None


def find_vault_by_path(vault_path: Path) -> Optional[Dict[str, str]]:
    """Find a registered vault whose path matches."""
    resolved = str(vault_path.resolve())
    for v in list_vaults():
        if str(Path(v["path"]).resolve()) == resolved:
            return v
    return None


def register_vault(
    vault_id: str, name: str, path: Path, set_default: bool = False,
    services_path: str = None,
) -> None:
    """Register a vault (or update if id already exists)."""
    data = _load_registry()
    resolved = str(path.resolve())

    # Update existing or append
    found = False
    for v in data["vaults"]:
        if v["id"] == vault_id:
            v["name"] = name
            v["path"] = resolved
            v["last_used"] = datetime.now().isoformat()
            if services_path is not None:
                v["services_path"] = services_path
            found = True
            break
    if not found:
        entry = {
            "id": vault_id,
            "name": name,
            "path": resolved,
            "last_used": datetime.now().isoformat(),
        }
        if services_path is not None:
            entry["services_path"] = services_path
        data["vaults"].append(entry)

    _save_registry(data)


def touch_vault(vault_id: str) -> None:
    """Update last_used timestamp for a vault."""
    data = _load_registry()
    for v in data["vaults"]:
        if v["id"] == vault_id:
            v["last_used"] = datetime.now().isoformat()
            break
    _save_registry(data)


def unregister_vault(vault_id: str) -> bool:
    """Remove a vault from the registry. Returns True if found."""
    data = _load_registry()
    before = len(data["vaults"])
    data["vaults"] = [v for v in data["vaults"] if v["id"] != vault_id]
    _save_registry(data)
    return len(data["vaults"]) < before
