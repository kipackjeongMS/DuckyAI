"""Service directory management for DuckyAI vaults.

Each vault has an associated services directory (outside the vault) containing
user code services and their git repos:

    <VaultParent>/<VaultName>-Services/
    ├── ServiceA/
    │   ├── repo1/              # Git repos
    │   └── repo2/
    └── ServiceB/
        └── main-repo/

Service metadata is stored exclusively in ``duckyai.yml`` under
``services.entries``.  The legacy ``.services.json`` sidecar file is no longer
read or written.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .config import Config, get_config_path


def get_services_path(vault_path: Path) -> Path:
    """Resolve the absolute path to the services directory for a vault.

    Reads from duckyai.yml ``services.path`` (may be relative to vault root).
    Falls back to ``<VaultParent>/<VaultDirName>-Services``.
    """
    config = Config(vault_path=vault_path)
    configured = config.get("services.path")
    if configured:
        p = Path(configured)
        if not p.is_absolute():
            p = (vault_path / p).resolve()
        return p
    vault_dir = Path(vault_path).resolve()
    return vault_dir.parent / f"{vault_dir.name}-Services"


def ensure_services_dir(vault_path: Path) -> Path:
    """Create the services directory if it doesn't exist.

    Returns the absolute path to the services directory.
    """
    services_dir = get_services_path(vault_path)
    services_dir.mkdir(parents=True, exist_ok=True)
    return services_dir


# ------------------------------------------------------------------ #
# Internal YAML helpers (ruamel round-trip for comment preservation)
# ------------------------------------------------------------------ #

def _load_config(vault_path: Path):
    """Load duckyai.yml via ruamel round-trip.

    Returns ``(yml, data, config_path)``.
    If the file does not exist, returns ``(None, None, config_path)``.
    """
    config_path = get_config_path(vault_path)
    if not config_path.exists():
        return None, None, config_path
    yml = YAML()
    yml.preserve_quotes = True
    yml.width = 4096
    with open(config_path, encoding="utf-8") as f:
        data = yml.load(f)
    return yml, data if data else CommentedMap(), config_path


def _save_config(config_path: Path, yml, data) -> None:
    """Write *data* back to *config_path* preserving formatting."""
    with open(config_path, "w", encoding="utf-8") as f:
        yml.dump(data, f)


def _get_entries(data) -> list:
    """Return the ``services.entries`` list from loaded YAML data.

    Returns the live reference (may be a ``CommentedSeq``) so callers can
    mutate in-place before saving.  Returns ``[]`` if the path is missing.
    """
    if data is None:
        return []
    services = data.get("services") if hasattr(data, "get") else None
    if not isinstance(services, dict):
        return []
    entries = services.get("entries")
    if not isinstance(entries, list):
        return []
    return entries


def _ensure_entries(data) -> list:
    """Ensure ``services.entries`` exists, creating sections as needed.

    Returns the *live* entries list.
    """
    if "services" not in data or not isinstance(data.get("services"), dict):
        data["services"] = CommentedMap()
    services = data["services"]
    if "entries" not in services or not isinstance(services.get("entries"), list):
        services["entries"] = CommentedSeq()
    return services["entries"]


def _entry_name(entry) -> str:
    """Extract the service name from an entry (dict-like or plain string)."""
    if isinstance(entry, str):
        return entry
    return entry.get("name", "") if hasattr(entry, "get") else str(entry)


def _to_plain(obj):
    """Recursively convert ruamel types to plain Python types."""
    if isinstance(obj, dict):
        return {str(k): _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain(v) for v in obj]
    return obj


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def add_service(vault_path: Path, name: str, *,
                metadata: Optional[Dict[str, Any]] = None,
                pr_scan: bool = False) -> Path:
    """Add a new service to the vault's services directory.

    Creates the service subdirectory and adds an entry to
    ``duckyai.yml  services.entries`` (using ruamel round-trip so
    comments and formatting are preserved).

    Returns the path to the created service directory.
    """
    services_dir = ensure_services_dir(vault_path)
    service_dir = services_dir / name
    service_dir.mkdir(parents=True, exist_ok=True)

    yml, data, config_path = _load_config(vault_path)
    if yml is None:
        return service_dir

    entries = _ensure_entries(data)

    if not any(_entry_name(e) == name for e in entries):
        entry = CommentedMap()
        entry["name"] = name
        if metadata:
            entry["metadata"] = metadata
        if pr_scan:
            entry["pr_scan"] = True
        entries.append(entry)
        _save_config(config_path, yml, data)

    return service_dir


def remove_service(vault_path: Path, name: str) -> bool:
    """Remove a service entry (does NOT delete the directory).

    Returns True if the service was found and removed.
    """
    yml, data, config_path = _load_config(vault_path)
    if yml is None:
        return False

    entries = _get_entries(data)
    if not entries:
        return False

    indices = [i for i, e in enumerate(entries) if _entry_name(e) == name]
    if not indices:
        return False

    for idx in reversed(indices):
        del entries[idx]

    _save_config(config_path, yml, data)
    return True


def list_services(vault_path: Path) -> List[Dict[str, Any]]:
    """List all services with their repos.

    Returns list of dicts: ``[{name, path, exists, repos: [{name, path, is_git}]}]``
    """
    services_dir = get_services_path(vault_path)
    if not services_dir.exists():
        return []

    yml, data, _ = _load_config(vault_path)
    entries = _get_entries(data)
    result = []

    for entry in entries:
        name = _entry_name(entry)
        if not name:
            continue
        svc_path = services_dir / name
        repos = []
        if svc_path.is_dir():
            for item in sorted(svc_path.iterdir()):
                if item.is_dir() and not item.name.startswith("."):
                    repos.append({
                        "name": item.name,
                        "path": str(item),
                        "is_git": (item / ".git").exists(),
                    })
        result.append({
            "name": name,
            "path": str(svc_path),
            "exists": svc_path.exists(),
            "repos": repos,
        })

    return result


def get_all_repo_paths(vault_path: Path) -> List[str]:
    """Return flat list of all git repo absolute paths across all services.

    Useful for injecting into AI agent context.
    """
    repos = []
    for svc in list_services(vault_path):
        for repo in svc.get("repos", []):
            if repo.get("is_git"):
                repos.append(repo["path"])
    return repos


def get_service_entry(vault_path: Path, name: str) -> Optional[Dict[str, Any]]:
    """Return the ``duckyai.yml`` entry for a named service, or ``None``.

    The returned dict is a plain Python dict (no ruamel types).
    """
    yml, data, _ = _load_config(vault_path)
    entries = _get_entries(data)
    for entry in entries:
        if _entry_name(entry) == name:
            return _to_plain(entry) if hasattr(entry, "items") else {"name": name}
    return None


def set_service_pr_scan(vault_path: Path, name: str, enabled: bool) -> bool:
    """Set ``pr_scan`` flag on an existing service entry.

    Returns True if the entry was found and updated.
    """
    yml, data, config_path = _load_config(vault_path)
    if yml is None:
        return False

    entries = _get_entries(data)
    for entry in entries:
        if _entry_name(entry) == name:
            if enabled:
                entry["pr_scan"] = True
            else:
                if "pr_scan" in entry:
                    del entry["pr_scan"]
            _save_config(config_path, yml, data)
            return True
    return False
