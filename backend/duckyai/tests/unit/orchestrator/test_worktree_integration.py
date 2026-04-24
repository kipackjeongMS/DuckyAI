"""Tests for worktree integration in execution_manager.py.

Tests the host-side PR worktree preparation flow:
- _prepare_pr_worktree() creates worktrees from Services repos
- _build_docker_cmd() mounts worktree at /repo instead of repo-cache
- Cleanup after execution
- Fallback to shallow clone when repo not in Services
"""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from duckyai.config import Config
from duckyai.orchestrator.execution_manager import ExecutionManager
from duckyai.orchestrator.models import AgentDefinition


def _run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd), capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _init_repo(path: Path, branch: str = "main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run_git(path, "init", "--initial-branch", branch)
    _run_git(path, "config", "user.email", "test@test.com")
    _run_git(path, "config", "user.name", "Test")
    (path / "README.md").write_text("# Init", encoding="utf-8")
    _run_git(path, "add", ".")
    _run_git(path, "commit", "-m", "init")
    return path


def _create_branch(repo: Path, branch: str):
    _run_git(repo, "checkout", "-b", branch)
    safe = branch.replace("/", "-")
    (repo / f"{safe}.txt").write_text("change", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", f"commit on {branch}")
    _run_git(repo, "checkout", "main")


@pytest.fixture
def vault_with_pr_setup(tmp_path):
    """Full vault + services + repo with branches for PR review testing."""
    # Services dir with a real repo
    services_dir = tmp_path / "TestVault-Services"
    repo_path = services_dir / "DEPA" / "MyRepo"
    _init_repo(repo_path)
    _create_branch(repo_path, "feature/my-change")

    # Services metadata is in duckyai.yml (no .services.json needed)

    # Vault
    vault = tmp_path / "TestVault"
    vault.mkdir()
    duckyai_dir = vault / ".duckyai"
    duckyai_dir.mkdir()
    (duckyai_dir / "duckyai.yml").write_text(
        'version: "1.0.0"\n'
        'id: test\n'
        'services:\n'
        '  path: "../TestVault-Services"\n'
        '  entries:\n'
        '    - name: "DEPA"\n',
        encoding="utf-8",
    )

    # PR review file
    pr_dir = vault / "01-Work" / "PRReviews"
    pr_dir.mkdir(parents=True)
    pr_file = pr_dir / "Review PR 42 - Fix something.md"
    pr_file.write_text(
        "---\nstatus: todo\n---\n## PR Details\n"
        "**PR**: [PR 42](https://dev.azure.com/testorg/testproject/_git/MyRepo/pullrequest/42)\n",
        encoding="utf-8",
    )

    return vault, services_dir, repo_path


@pytest.fixture
def pr_metadata():
    """Pre-fetched PR metadata dict (simulates _prefetch_pr_metadata output)."""
    return {
        "pr_number": "42",
        "org": "testorg",
        "project": "testproject",
        "repo": "MyRepo",
        "title": "Fix something",
        "source_branch": "feature/my-change",
        "target_branch": "main",
        "status": "active",
    }


class TestPrepareprWorktree:
    """Tests for ExecutionManager._prepare_pr_worktree()."""

    def test_creates_worktree_from_services_repo(self, vault_with_pr_setup, pr_metadata):
        vault, _, repo_path = vault_with_pr_setup
        config = Config(vault_path=vault)
        em = ExecutionManager(vault_path=vault, config=config)

        wt_path = em._prepare_pr_worktree(pr_metadata)

        assert wt_path is not None
        assert wt_path.exists()
        assert ".duckyai-worktrees" in str(wt_path)
        assert "pr-42" in wt_path.name

    def test_returns_none_when_repo_not_in_services(self, vault_with_pr_setup, pr_metadata):
        vault, _, _ = vault_with_pr_setup
        config = Config(vault_path=vault)
        em = ExecutionManager(vault_path=vault, config=config)

        pr_metadata["repo"] = "UnknownRepo"
        wt_path = em._prepare_pr_worktree(pr_metadata)
        assert wt_path is None

    def test_returns_none_when_metadata_missing_fields(self, vault_with_pr_setup):
        vault, _, _ = vault_with_pr_setup
        config = Config(vault_path=vault)
        em = ExecutionManager(vault_path=vault, config=config)

        wt_path = em._prepare_pr_worktree({"pr_number": "42"})
        assert wt_path is None

    def test_returns_none_when_metadata_has_error(self, vault_with_pr_setup, pr_metadata):
        vault, _, _ = vault_with_pr_setup
        config = Config(vault_path=vault)
        em = ExecutionManager(vault_path=vault, config=config)

        pr_metadata["error"] = "some error"
        wt_path = em._prepare_pr_worktree(pr_metadata)
        assert wt_path is None

    def test_cleanup_after_worktree_created(self, vault_with_pr_setup, pr_metadata):
        vault, _, _ = vault_with_pr_setup
        config = Config(vault_path=vault)
        em = ExecutionManager(vault_path=vault, config=config)

        wt_path = em._prepare_pr_worktree(pr_metadata)
        assert wt_path.exists()

        em._cleanup_pr_worktree(pr_metadata)
        assert not wt_path.exists()


class TestBuildDockerCmdNoRepoCache:
    """Tests that _build_docker_cmd no longer resolves ${repo_cache}."""

    def test_repo_cache_placeholder_not_resolved(self, vault_with_pr_setup):
        """${repo_cache} mounts should be skipped (no longer supported)."""
        vault, _, _ = vault_with_pr_setup
        config = Config(vault_path=vault)
        em = ExecutionManager(
            vault_path=vault, config=config,
            orchestrator_settings={
                'use_container': True,
                'container': {'image': 'test:latest'},
            },
        )

        agent = AgentDefinition()
        agent.name = "PR Review (PR)"
        agent.abbreviation = "PR"
        agent.extra_mounts = [
            {"source": "${repo_cache}", "target": "/repo-cache"},
            {"source": "${services_path}", "target": "/services", "readonly": True},
        ]

        with patch.object(em, '_get_copilot_token', return_value=None), \
             patch.object(em, '_get_azure_access_token', return_value=None), \
             patch('shutil.which', return_value='docker'):
            docker_cmd = em._build_docker_cmd(
                ['echo', 'test'], agent=agent
            )

        # /repo-cache should NOT appear in the docker command
        cmd_str = " ".join(docker_cmd)
        assert "/repo-cache" not in cmd_str
        assert "repo-cache" not in cmd_str
