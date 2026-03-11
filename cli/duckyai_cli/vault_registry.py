"""Global vault registry — tracks registered vaults in ~/.duckyai/vaults.json."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


REGISTRY_PATH = Path.home() / ".duckyai" / "vaults.json"


def _load_registry() -> Dict[str, Any]:
    """Load the registry file, returning empty structure if missing/corrupt."""
    if not REGISTRY_PATH.exists():
        return {"vaults": [], "default": None}
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "vaults" in data:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"vaults": [], "default": None}


def _save_registry(data: Dict[str, Any]) -> None:
    """Write registry to disk."""
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def list_vaults() -> List[Dict[str, str]]:
    """Return list of registered vault entries."""
    return _load_registry().get("vaults", [])


def get_default_vault_id() -> Optional[str]:
    """Return the default vault id, or None."""
    return _load_registry().get("default")


def find_vault_by_path(vault_path: Path) -> Optional[Dict[str, str]]:
    """Find a registered vault whose path matches."""
    resolved = str(vault_path.resolve())
    for v in list_vaults():
        if str(Path(v["path"]).resolve()) == resolved:
            return v
    return None


def register_vault(
    vault_id: str, name: str, path: Path, set_default: bool = True
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
            found = True
            break
    if not found:
        data["vaults"].append(
            {
                "id": vault_id,
                "name": name,
                "path": resolved,
                "last_used": datetime.now().isoformat(),
            }
        )

    if set_default or data.get("default") is None:
        data["default"] = vault_id

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
    if data.get("default") == vault_id:
        data["default"] = data["vaults"][0]["id"] if data["vaults"] else None
    _save_registry(data)
    return len(data["vaults"]) < before
