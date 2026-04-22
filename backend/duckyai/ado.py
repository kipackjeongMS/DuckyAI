"""Azure DevOps integration helpers.

Wraps ``az devops`` / ``az repos`` CLI commands for listing projects,
repos, and cloning.  All functions degrade gracefully when the Azure CLI
or azure-devops extension is missing.
"""

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AdoProject:
    id: str
    name: str


@dataclass
class AdoRepo:
    id: str
    name: str
    remote_url: str
    ssh_url: str
    default_branch: str
    size: int


# ---------------------------------------------------------------------------
# az CLI resolution
# ---------------------------------------------------------------------------

def _find_az_bin() -> Optional[str]:
    """Locate the ``az`` executable, including Windows fallback paths."""
    import os
    az = shutil.which("az")
    if az:
        return az
    # Windows fallback
    candidate = (
        Path(os.environ.get("ProgramFiles", ""))
        / "Microsoft SDKs" / "Azure" / "CLI2" / "wbin" / "az.cmd"
    )
    if candidate.exists():
        return str(candidate)
    return None


def is_az_devops_available() -> tuple[bool, str]:
    """Check whether ``az`` + azure-devops extension are usable.

    Returns ``(available, message)``.
    """
    az = _find_az_bin()
    if not az:
        return False, "Azure CLI (az) is not installed. Install from https://aka.ms/InstallAzureCLIDeb"

    try:
        result = subprocess.run(
            [az, "extension", "show", "--name", "azure-devops", "-o", "tsv", "--query", "version"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False, (
                "azure-devops extension is not installed.\n"
                "  Run: az extension add --name azure-devops"
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "Could not verify azure-devops extension."

    return True, "ok"


# ---------------------------------------------------------------------------
# az CLI wrappers
# ---------------------------------------------------------------------------

def _run_az(args: list[str], timeout: int = 30) -> Optional[str]:
    """Run an ``az`` command and return stdout, or None on failure."""
    az = _find_az_bin()
    if not az:
        return None
    try:
        result = subprocess.run(
            [az, *args],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def list_projects(org: str) -> List[AdoProject]:
    """List all projects the user can see in the given ADO organization.

    ``org`` should be just the org name (e.g. ``msazure``), not the full URL.
    """
    org_url = _normalize_org_url(org)
    raw = _run_az([
        "devops", "project", "list",
        "--org", org_url,
        "--output", "json",
    ], timeout=30)
    if not raw:
        return []

    try:
        data = json.loads(raw)
        projects = data.get("value", data) if isinstance(data, dict) else data
        return [
            AdoProject(id=p["id"], name=p["name"])
            for p in projects
        ]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def list_repos(org: str, project: str) -> List[AdoRepo]:
    """List all git repos in the given ADO project."""
    org_url = _normalize_org_url(org)
    raw = _run_az([
        "repos", "list",
        "--org", org_url,
        "--project", project,
        "--output", "json",
    ], timeout=30)
    if not raw:
        return []

    try:
        repos = json.loads(raw)
        return [
            AdoRepo(
                id=r["id"],
                name=r["name"],
                remote_url=r.get("remoteUrl", ""),
                ssh_url=r.get("sshUrl", ""),
                default_branch=r.get("defaultBranch", "refs/heads/main"),
                size=r.get("size", 0),
            )
            for r in repos
        ]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def clone_repo(remote_url: str, dest: Path) -> bool:
    """Clone a repo into *dest* using ``git clone``.

    Returns True on success.
    """
    git = shutil.which("git")
    if not git:
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [git, "clone", remote_url, str(dest)],
            capture_output=True, text=True, timeout=600,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_org_url(org: str) -> str:
    """Ensure org is a full ``https://dev.azure.com/<name>`` URL."""
    org = org.strip().rstrip("/")
    if org.startswith("https://"):
        return org
    return f"https://dev.azure.com/{org}"


def parse_ado_project_url(url: str) -> tuple[str | None, str | None]:
    """Extract ``(org, project)`` from an ADO project URL.

    Supported formats::

        https://dev.azure.com/{org}/{project}
        https://dev.azure.com/{org}/{project}/_git/...
        https://{org}.visualstudio.com/{project}

    Returns ``(org, project)`` or ``(None, None)`` if unparseable.
    Project names are URL-decoded (e.g. ``Azure%20AppConfig`` → ``Azure AppConfig``).
    """
    from urllib.parse import unquote

    url = url.strip().rstrip("/")
    if not url.startswith("https://"):
        return None, None

    try:
        # Strip protocol
        rest = url.split("://", 1)[1]
        host, _, path = rest.partition("/")
        parts = [unquote(p) for p in path.split("/") if p and p != "_git"]

        if "dev.azure.com" in host and len(parts) >= 2:
            return parts[0], parts[1]

        if host.endswith(".visualstudio.com") and len(parts) >= 1:
            org = host.replace(".visualstudio.com", "")
            return org, parts[0]
    except (ValueError, IndexError):
        pass

    return None, None
