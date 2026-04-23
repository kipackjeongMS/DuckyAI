"""Service directory management for DuckyAI vaults.

Each vault has an associated services directory (outside the vault) containing
user code services and their git repos:

    <VaultParent>/<VaultName>-Services/
    ├── .services.json          # Metadata about registered services
    ├── ServiceA/
    │   ├── repo1/              # Git repos
    │   └── repo2/
    └── ServiceB/
        └── main-repo/
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config


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

    # Initialize .services.json if missing
    meta_file = services_dir / ".services.json"
    if not meta_file.exists():
        meta = {
            "vault_id": Config(vault_path=vault_path).get("id", "default"),
            "vault_path": str(Path(vault_path).resolve()),
            "created": datetime.now().isoformat(),
            "services": [],
        }
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return services_dir


def _read_services_meta(services_dir: Path) -> Dict[str, Any]:
    """Read .services.json metadata from the services directory."""
    meta_file = services_dir / ".services.json"
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"services": []}


def _write_services_meta(services_dir: Path, meta: Dict[str, Any]) -> None:
    """Write .services.json metadata to the services directory."""
    meta_file = services_dir / ".services.json"
    meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _update_duckyai_yml(vault_path: Path, services: List[Dict]) -> None:
    """Update the services.entries list in duckyai.yml."""
    config_path = Path(vault_path) / ".duckyai" / "duckyai.yml"
    if not config_path.exists():
        return

    content = config_path.read_text(encoding="utf-8")
    import re

    # Build the new entries YAML block
    if services:
        entries_lines = "\n".join(f'    - name: "{s["name"]}"' for s in services)
        entries_block = f"  entries:\n{entries_lines}"
    else:
        entries_block = "  entries: []"

    # Replace existing entries block
    pattern = r"(  entries:).*?(?=\n\w|\n\n\w|\Z)"
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, entries_block, content, count=1, flags=re.DOTALL)
    else:
        # No entries key — append under services section
        content = content.replace("services:", f"services:\n{entries_block}", 1)

    config_path.write_text(content, encoding="utf-8")


def add_service(vault_path: Path, name: str, *,
                ado_org: Optional[str] = None,
                ado_project: Optional[str] = None) -> Path:
    """Add a new service to the vault's services directory.

    Creates the service subdirectory and updates metadata.
    Returns the path to the created service directory.
    """
    services_dir = ensure_services_dir(vault_path)
    service_dir = services_dir / name
    service_dir.mkdir(parents=True, exist_ok=True)

    # Update .services.json
    meta = _read_services_meta(services_dir)
    existing_names = {s["name"] for s in meta.get("services", [])}
    if name not in existing_names:
        entry: Dict[str, Any] = {
            "name": name,
            "created": datetime.now().isoformat(),
        }
        if ado_org:
            entry["ado_org"] = ado_org
        if ado_project:
            entry["ado_project"] = ado_project
        meta.setdefault("services", []).append(entry)
        _write_services_meta(services_dir, meta)

    # Update duckyai.yml
    _update_duckyai_yml(vault_path, meta["services"])

    return service_dir


def remove_service(vault_path: Path, name: str) -> bool:
    """Remove a service entry (does NOT delete the directory).

    Returns True if the service was found and removed.
    """
    services_dir = get_services_path(vault_path)
    meta = _read_services_meta(services_dir)

    original_count = len(meta.get("services", []))
    meta["services"] = [s for s in meta.get("services", []) if s["name"] != name]

    if len(meta["services"]) < original_count:
        _write_services_meta(services_dir, meta)
        _update_duckyai_yml(vault_path, meta["services"])
        return True
    return False


def list_services(vault_path: Path) -> List[Dict[str, Any]]:
    """List all services with their repos.

    Returns list of dicts: [{name, path, repos: [{name, path, is_git}]}]
    """
    services_dir = get_services_path(vault_path)
    if not services_dir.exists():
        return []

    meta = _read_services_meta(services_dir)
    result = []

    for entry in meta.get("services", []):
        name = entry["name"]
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
            "created": entry.get("created"),
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
    """Return the .services.json entry for a named service, or None."""
    services_dir = get_services_path(vault_path)
    meta = _read_services_meta(services_dir)
    for entry in meta.get("services", []):
        if entry["name"] == name:
            return entry
    return None


def add_repo_to_service(vault_path: Path, service_name: str,
                        repo_name: str, remote_url: str) -> None:
    """Record a cloned repo in the service's metadata."""
    services_dir = get_services_path(vault_path)
    meta = _read_services_meta(services_dir)
    for entry in meta.get("services", []):
        if entry["name"] == service_name:
            repos = entry.setdefault("repos", [])
            # Don't duplicate
            if not any(r["name"] == repo_name for r in repos):
                repos.append({
                    "name": repo_name,
                    "remote_url": remote_url,
                    "cloned_at": datetime.now().isoformat(),
                })
            _write_services_meta(services_dir, meta)
            return
