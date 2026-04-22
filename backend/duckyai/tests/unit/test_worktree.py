"""Unit tests for worktree.py — git worktree management for PR reviews.

Uses real git repos in tmp_path (not mocks) since worktree operations
are tightly coupled to git state.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from duckyai.worktree import (
    find_repo_in_services,
    prepare_pr_worktree,
    cleanup_pr_worktree,
    cleanup_stale_worktrees,
)


def _run_git(cwd: Path, *args: str) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _init_bare_like_repo(path: Path, default_branch: str = "main") -> Path:
    """Create a real git repo with an initial commit (simulates a Services repo)."""
    path.mkdir(parents=True, exist_ok=True)
    _run_git(path, "init", "--initial-branch", default_branch)
    _run_git(path, "config", "user.email", "test@test.com")
    _run_git(path, "config", "user.name", "Test")
    # Initial commit on default branch
    (path / "README.md").write_text("# Initial", encoding="utf-8")
    _run_git(path, "add", ".")
    _run_git(path, "commit", "-m", "Initial commit")
    return path


def _create_branch(repo: Path, branch: str, file_content: str = "change"):
    """Create a branch with a commit diverging from current HEAD."""
    _run_git(repo, "checkout", "-b", branch)
    safe_name = branch.replace("/", "-")
    (repo / f"{safe_name}.txt").write_text(file_content, encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", f"commit on {branch}")
    _run_git(repo, "checkout", "main")


@pytest.fixture
def services_with_repo(tmp_path):
    """Create a Services directory with one service containing a real git repo.

    Layout:
        <tmp>/Services/
            .services.json
            DEPA/
                DevOpsDeploymentAgents/   ← real git repo with main + feature branch
    """
    services_dir = tmp_path / "Services"
    services_dir.mkdir()

    # .services.json
    meta = {
        "vault_id": "test",
        "services": [{"name": "DEPA", "created": "2026-01-01"}],
    }
    (services_dir / ".services.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    # Real git repo
    repo_path = services_dir / "DEPA" / "DevOpsDeploymentAgents"
    _init_bare_like_repo(repo_path)
    _create_branch(repo_path, "feature/my-pr")

    return services_dir, repo_path


@pytest.fixture
def vault_with_services(tmp_path, services_with_repo):
    """Create a vault that points to the services directory."""
    services_dir, repo_path = services_with_repo

    vault = tmp_path / "TestVault"
    vault.mkdir()
    duckyai_dir = vault / ".duckyai"
    duckyai_dir.mkdir()

    svc_rel = os.path.relpath(services_dir, vault).replace("\\", "/")
    (duckyai_dir / "duckyai.yml").write_text(
        f'version: "1.0.0"\n'
        f'id: test_vault\n'
        f'name: TestVault\n'
        f'services:\n'
        f'  path: "{svc_rel}"\n'
        f'  entries:\n'
        f'    - name: "DEPA"\n',
        encoding="utf-8",
    )
    return vault, services_dir, repo_path


# ─── find_repo_in_services ──────────────────────────────────────────


class TestFindRepoInServices:
    """Tests for find_repo_in_services()."""

    def test_finds_existing_repo_by_name(self, vault_with_services):
        vault, services_dir, repo_path = vault_with_services
        result = find_repo_in_services(vault, "DevOpsDeploymentAgents")
        assert result is not None
        assert result.name == "DevOpsDeploymentAgents"
        assert (result / ".git").exists()

    def test_returns_none_for_unknown_repo(self, vault_with_services):
        vault, _, _ = vault_with_services
        result = find_repo_in_services(vault, "NonExistentRepo")
        assert result is None

    def test_returns_none_when_services_dir_missing(self, tmp_path):
        vault = tmp_path / "EmptyVault"
        vault.mkdir()
        duckyai_dir = vault / ".duckyai"
        duckyai_dir.mkdir()
        (duckyai_dir / "duckyai.yml").write_text('id: x\n', encoding="utf-8")
        result = find_repo_in_services(vault, "SomeRepo")
        assert result is None

    def test_finds_repo_across_multiple_services(self, vault_with_services):
        vault, services_dir, _ = vault_with_services
        # Add a second service with another repo
        other_repo = services_dir / "AppConfig" / "AzureAppConfigService"
        _init_bare_like_repo(other_repo)
        # Update metadata
        meta = json.loads(
            (services_dir / ".services.json").read_text(encoding="utf-8")
        )
        meta["services"].append({"name": "AppConfig", "created": "2026-01-02"})
        (services_dir / ".services.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

        result = find_repo_in_services(vault, "AzureAppConfigService")
        assert result is not None
        assert result.name == "AzureAppConfigService"

    def test_ignores_non_git_directories(self, vault_with_services):
        vault, services_dir, _ = vault_with_services
        # Add a plain (non-git) directory with matching name
        plain = services_dir / "DEPA" / "NotAGitRepo"
        plain.mkdir(parents=True)
        result = find_repo_in_services(vault, "NotAGitRepo")
        assert result is None


# ─── prepare_pr_worktree ────────────────────────────────────────────


class TestPreparePrWorktree:
    """Tests for prepare_pr_worktree()."""

    def test_creates_worktree_at_source_branch(self, services_with_repo):
        _, repo_path = services_with_repo
        wt_path = prepare_pr_worktree(
            repo_path, pr_id="1234", source_branch="feature/my-pr", target_branch="main"
        )
        assert wt_path.exists()
        assert (wt_path / ".git").exists()  # worktree has .git file (not dir)
        # Verify we're on the source branch
        head = _run_git(wt_path, "rev-parse", "HEAD")
        source_tip = _run_git(repo_path, "rev-parse", "feature/my-pr")
        assert head == source_tip

    def test_worktree_path_under_duckyai_worktrees(self, services_with_repo):
        _, repo_path = services_with_repo
        wt_path = prepare_pr_worktree(
            repo_path, pr_id="5678", source_branch="feature/my-pr", target_branch="main"
        )
        assert ".duckyai-worktrees" in str(wt_path)
        assert "pr-5678" in wt_path.name

    def test_target_branch_accessible_from_worktree(self, services_with_repo):
        _, repo_path = services_with_repo
        wt_path = prepare_pr_worktree(
            repo_path, pr_id="1234", source_branch="feature/my-pr", target_branch="main"
        )
        # Agent needs to run git diff against target — verify it's reachable
        main_rev = _run_git(wt_path, "rev-parse", "main")
        assert main_rev  # should resolve without error

    def test_idempotent_recreates_if_exists(self, services_with_repo):
        _, repo_path = services_with_repo
        wt1 = prepare_pr_worktree(
            repo_path, pr_id="1234", source_branch="feature/my-pr", target_branch="main"
        )
        wt2 = prepare_pr_worktree(
            repo_path, pr_id="1234", source_branch="feature/my-pr", target_branch="main"
        )
        assert wt1 == wt2
        assert wt2.exists()

    def test_cleanup_after_create(self, services_with_repo):
        _, repo_path = services_with_repo
        wt_path = prepare_pr_worktree(
            repo_path, pr_id="9999", source_branch="feature/my-pr", target_branch="main"
        )
        assert wt_path.exists()
        cleanup_pr_worktree(repo_path, pr_id="9999")
        assert not wt_path.exists()


# ─── cleanup_pr_worktree ────────────────────────────────────────────


class TestCleanupPrWorktree:
    """Tests for cleanup_pr_worktree()."""

    def test_removes_worktree_and_dir(self, services_with_repo):
        _, repo_path = services_with_repo
        wt_path = prepare_pr_worktree(
            repo_path, pr_id="42", source_branch="feature/my-pr", target_branch="main"
        )
        assert wt_path.exists()
        result = cleanup_pr_worktree(repo_path, pr_id="42")
        assert result is True
        assert not wt_path.exists()

    def test_returns_false_for_nonexistent_worktree(self, services_with_repo):
        _, repo_path = services_with_repo
        result = cleanup_pr_worktree(repo_path, pr_id="nonexistent")
        assert result is False

    def test_prunes_stale_worktree_refs(self, services_with_repo):
        """After cleanup, git worktree list should not show the removed worktree."""
        _, repo_path = services_with_repo
        prepare_pr_worktree(
            repo_path, pr_id="77", source_branch="feature/my-pr", target_branch="main"
        )
        cleanup_pr_worktree(repo_path, pr_id="77")
        worktree_list = _run_git(repo_path, "worktree", "list")
        assert "pr-77" not in worktree_list


# ─── cleanup_stale_worktrees ────────────────────────────────────────


class TestCleanupStaleWorktrees:
    """Tests for cleanup_stale_worktrees()."""

    def test_removes_old_worktrees(self, services_with_repo):
        _, repo_path = services_with_repo
        services_dir = repo_path.parent.parent  # Services/DEPA/repo -> Services

        # Create a worktree and backdate its marker
        wt_path = prepare_pr_worktree(
            repo_path, pr_id="old", source_branch="feature/my-pr", target_branch="main"
        )
        marker = wt_path.parent / ".duckyai-worktree-created-old"
        if not marker.exists():
            # Create marker with old timestamp
            marker.write_text(str(time.time() - 86400 * 2), encoding="utf-8")
        else:
            marker.write_text(str(time.time() - 86400 * 2), encoding="utf-8")

        removed = cleanup_stale_worktrees(services_dir, max_age_hours=1)
        assert removed >= 1
        assert not wt_path.exists()

    def test_keeps_recent_worktrees(self, services_with_repo):
        _, repo_path = services_with_repo
        services_dir = repo_path.parent.parent

        wt_path = prepare_pr_worktree(
            repo_path, pr_id="fresh", source_branch="feature/my-pr", target_branch="main"
        )
        removed = cleanup_stale_worktrees(services_dir, max_age_hours=24)
        assert removed == 0
        assert wt_path.exists()
        # Cleanup
        cleanup_pr_worktree(repo_path, pr_id="fresh")

    def test_handles_empty_services_dir(self, tmp_path):
        empty_svc = tmp_path / "EmptyServices"
        empty_svc.mkdir()
        removed = cleanup_stale_worktrees(empty_svc)
        assert removed == 0
