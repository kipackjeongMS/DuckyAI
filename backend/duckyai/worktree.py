"""Git worktree management for PR reviews.

Provides host-side functions to create lightweight git worktrees from
existing Services repos, so the PR Review container receives a ready-to-use
checkout instead of cloning from scratch.

Worktree layout inside a Services repo:
    Services/DEPA/DevOpsDeploymentAgents/
        .duckyai-worktrees/
            pr-1234/          ← worktree checked out at source branch
"""

import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from .services import get_services_path, list_services

logger = logging.getLogger(__name__)

WORKTREE_DIR_NAME = ".duckyai-worktrees"


def _run_git(cwd: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a git command and return the CompletedProcess."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def find_repo_in_services(vault_path: Path, repo_name: str) -> Optional[Path]:
    """Locate a git repo by name across all Services.

    Scans every service directory for a subdirectory matching *repo_name*
    that contains a ``.git`` directory (confirming it's a real git repo).

    Returns:
        Path to the repo root, or None if not found.
    """
    try:
        services = list_services(vault_path)
    except Exception:
        return None

    for svc in services:
        for repo in svc.get("repos", []):
            if repo.get("name") == repo_name and repo.get("is_git"):
                repo_path = Path(repo["path"])
                if repo_path.exists() and (repo_path / ".git").exists():
                    return repo_path
    return None


def prepare_pr_worktree(
    repo_path: Path,
    pr_id: str,
    source_branch: str,
    target_branch: str,
) -> Path:
    """Create a git worktree for a PR review.

    1. Fetches source and target branches (handles shallow repos)
    2. Creates a worktree checked out at the source branch
    3. Writes a timestamp marker for stale cleanup

    If a worktree for the same pr_id already exists, it is removed and
    recreated to ensure a clean state.

    Args:
        repo_path: Path to the Services git repo (the main working tree).
        pr_id: PR identifier (used to name the worktree directory).
        source_branch: The PR source branch to check out.
        target_branch: The PR target branch (fetched so diffs work).

    Returns:
        Path to the created worktree directory.
    """
    wt_dir = repo_path / WORKTREE_DIR_NAME
    wt_dir.mkdir(parents=True, exist_ok=True)
    wt_path = wt_dir / f"pr-{pr_id}"

    # Clean up existing worktree for this PR (idempotent re-create)
    if wt_path.exists():
        cleanup_pr_worktree(repo_path, pr_id)

    # Remove stale lock files from potential previous crashes
    git_dir = repo_path / ".git"
    for lock in git_dir.glob("*.lock"):
        try:
            lock.unlink()
        except OSError:
            pass

    # Fetch source and target branches from origin (if remote exists)
    _has_origin = _run_git(repo_path, "remote", "get-url", "origin").returncode == 0
    if _has_origin:
        _run_git(repo_path, "fetch", "origin", source_branch, "--depth", "50")
        _run_git(repo_path, "fetch", "origin", target_branch, "--depth", "50")

    # Determine the commit to check out
    # Try origin/source_branch first, fall back to local branch
    ref_check = _run_git(repo_path, "rev-parse", "--verify", f"origin/{source_branch}")
    if ref_check.returncode == 0:
        checkout_ref = f"origin/{source_branch}"
    else:
        checkout_ref = source_branch

    result = _run_git(
        repo_path, "worktree", "add", "--detach", str(wt_path), checkout_ref
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed for pr-{pr_id}: {result.stderr.strip()}"
        )

    # Write timestamp marker for stale cleanup
    marker = wt_dir / f".duckyai-worktree-created-{pr_id}"
    marker.write_text(str(time.time()), encoding="utf-8")

    logger.info(f"Created worktree pr-{pr_id} at {wt_path}")
    return wt_path


def cleanup_pr_worktree(repo_path: Path, pr_id: str) -> bool:
    """Remove a PR worktree and prune git worktree refs.

    Returns True if the worktree was found and removed.
    """
    wt_dir = repo_path / WORKTREE_DIR_NAME
    wt_path = wt_dir / f"pr-{pr_id}"

    if not wt_path.exists():
        return False

    # git worktree remove (force in case of uncommitted changes)
    result = _run_git(repo_path, "worktree", "remove", "--force", str(wt_path))
    if result.returncode != 0:
        # Fallback: manual removal + prune
        try:
            shutil.rmtree(str(wt_path), ignore_errors=True)
        except OSError:
            pass
        _run_git(repo_path, "worktree", "prune")
    else:
        _run_git(repo_path, "worktree", "prune")

    # Remove timestamp marker
    marker = wt_dir / f".duckyai-worktree-created-{pr_id}"
    if marker.exists():
        try:
            marker.unlink()
        except OSError:
            pass

    logger.info(f"Cleaned up worktree pr-{pr_id}")
    return True


def cleanup_stale_worktrees(services_path: Path, max_age_hours: int = 24) -> int:
    """Garbage-collect old worktrees across all repos in the Services directory.

    Scans for ``.duckyai-worktrees/`` directories in any repo under *services_path*.
    Removes worktrees whose timestamp marker is older than *max_age_hours*.

    Returns the number of worktrees removed.
    """
    if not services_path.exists():
        return 0

    removed = 0
    max_age_seconds = max_age_hours * 3600
    now = time.time()

    # Walk: services_path / <service> / <repo> / .duckyai-worktrees/
    for service_dir in services_path.iterdir():
        if not service_dir.is_dir() or service_dir.name.startswith("."):
            continue
        for repo_dir in service_dir.iterdir():
            if not repo_dir.is_dir() or not (repo_dir / ".git").exists():
                continue
            wt_dir = repo_dir / WORKTREE_DIR_NAME
            if not wt_dir.exists():
                continue

            for marker in wt_dir.glob(".duckyai-worktree-created-*"):
                pr_id = marker.name.replace(".duckyai-worktree-created-", "")
                try:
                    created_ts = float(marker.read_text(encoding="utf-8").strip())
                except (ValueError, OSError):
                    created_ts = 0  # Treat unreadable as ancient

                if (now - created_ts) > max_age_seconds:
                    if cleanup_pr_worktree(repo_dir, pr_id):
                        removed += 1

    return removed
