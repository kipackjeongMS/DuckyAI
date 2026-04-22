"""Unit tests for ado.py — Azure DevOps integration helpers."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from duckyai.ado import (
    AdoProject,
    AdoRepo,
    _normalize_org_url,
    _run_az,
    is_az_devops_available,
    list_projects,
    list_repos,
    clone_repo,
    parse_ado_project_url,
)


# ---------------------------------------------------------------------------
# parse_ado_project_url
# ---------------------------------------------------------------------------

class TestParseAdoProjectUrl:

    def test_standard_url(self):
        org, proj = parse_ado_project_url("https://dev.azure.com/msazure/Azure%20AppConfig")
        assert org == "msazure"
        assert proj == "Azure AppConfig"

    def test_url_with_git_suffix(self):
        org, proj = parse_ado_project_url("https://dev.azure.com/myorg/MyProject/_git/MyRepo")
        assert org == "myorg"
        assert proj == "MyProject"

    def test_legacy_visualstudio_url(self):
        org, proj = parse_ado_project_url("https://msazure.visualstudio.com/MyProject")
        assert org == "msazure"
        assert proj == "MyProject"

    def test_trailing_slash(self):
        org, proj = parse_ado_project_url("https://dev.azure.com/org/proj/")
        assert org == "org"
        assert proj == "proj"

    def test_no_protocol_returns_none(self):
        assert parse_ado_project_url("dev.azure.com/org/proj") == (None, None)

    def test_empty_string(self):
        assert parse_ado_project_url("") == (None, None)

    def test_org_only_returns_none(self):
        assert parse_ado_project_url("https://dev.azure.com/orgonly") == (None, None)

    def test_url_encoded_project(self):
        org, proj = parse_ado_project_url("https://dev.azure.com/org/My%20Big%20Project")
        assert proj == "My Big Project"


# ---------------------------------------------------------------------------
# _normalize_org_url
# ---------------------------------------------------------------------------

class TestNormalizeOrgUrl:

    def test_bare_name(self):
        assert _normalize_org_url("msazure") == "https://dev.azure.com/msazure"

    def test_already_full_url(self):
        assert _normalize_org_url("https://dev.azure.com/msazure") == "https://dev.azure.com/msazure"

    def test_strips_whitespace_and_trailing_slash(self):
        assert _normalize_org_url("  msazure/ ") == "https://dev.azure.com/msazure"

    def test_full_url_with_trailing_slash(self):
        assert _normalize_org_url("https://dev.azure.com/myorg/") == "https://dev.azure.com/myorg"


# ---------------------------------------------------------------------------
# is_az_devops_available
# ---------------------------------------------------------------------------

class TestIsAzDevopsAvailable:

    @patch("duckyai.ado._find_az_bin", return_value=None)
    def test_no_az_binary(self, _):
        ok, msg = is_az_devops_available()
        assert ok is False
        assert "not installed" in msg.lower()

    @patch("duckyai.ado._find_az_bin", return_value="az")
    @patch("duckyai.ado.subprocess.run")
    def test_extension_missing(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        ok, msg = is_az_devops_available()
        assert ok is False
        assert "azure-devops extension" in msg.lower()

    @patch("duckyai.ado._find_az_bin", return_value="az")
    @patch("duckyai.ado.subprocess.run")
    def test_extension_present(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0\n")
        ok, msg = is_az_devops_available()
        assert ok is True
        assert msg == "ok"

    @patch("duckyai.ado._find_az_bin", return_value="az")
    @patch("duckyai.ado.subprocess.run", side_effect=subprocess.TimeoutExpired("az", 15))
    def test_timeout(self, *_):
        ok, msg = is_az_devops_available()
        assert ok is False
        assert "could not verify" in msg.lower()


# ---------------------------------------------------------------------------
# _run_az
# ---------------------------------------------------------------------------

class TestRunAz:

    @patch("duckyai.ado._find_az_bin", return_value=None)
    def test_no_az_returns_none(self, _):
        assert _run_az(["devops", "project", "list"]) is None

    @patch("duckyai.ado._find_az_bin", return_value="az")
    @patch("duckyai.ado.subprocess.run")
    def test_success(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"ok": true}')
        result = _run_az(["devops", "project", "list"])
        assert result == '{"ok": true}'

    @patch("duckyai.ado._find_az_bin", return_value="az")
    @patch("duckyai.ado.subprocess.run")
    def test_failure_returns_none(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=1, stdout="error")
        assert _run_az(["repos", "list"]) is None

    @patch("duckyai.ado._find_az_bin", return_value="az")
    @patch("duckyai.ado.subprocess.run", side_effect=subprocess.TimeoutExpired("az", 30))
    def test_timeout_returns_none(self, *_):
        assert _run_az(["repos", "list"]) is None


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------

class TestListProjects:

    @patch("duckyai.ado._run_az")
    def test_parses_value_envelope(self, mock_az):
        mock_az.return_value = json.dumps({
            "value": [
                {"id": "p1", "name": "Project Alpha"},
                {"id": "p2", "name": "Project Beta"},
            ]
        })
        projects = list_projects("myorg")
        assert len(projects) == 2
        assert projects[0] == AdoProject(id="p1", name="Project Alpha")
        assert projects[1] == AdoProject(id="p2", name="Project Beta")

    @patch("duckyai.ado._run_az")
    def test_parses_bare_list(self, mock_az):
        mock_az.return_value = json.dumps([
            {"id": "p1", "name": "Only Project"},
        ])
        projects = list_projects("myorg")
        assert len(projects) == 1
        assert projects[0].name == "Only Project"

    @patch("duckyai.ado._run_az", return_value=None)
    def test_az_failure_returns_empty(self, _):
        assert list_projects("myorg") == []

    @patch("duckyai.ado._run_az", return_value="not valid json")
    def test_invalid_json_returns_empty(self, _):
        assert list_projects("myorg") == []

    @patch("duckyai.ado._run_az", return_value='{"value": []}')
    def test_empty_projects(self, _):
        assert list_projects("myorg") == []

    @patch("duckyai.ado._run_az")
    def test_passes_normalized_org_url(self, mock_az):
        mock_az.return_value = '{"value": []}'
        list_projects("msazure")
        args = mock_az.call_args[0][0]
        assert "https://dev.azure.com/msazure" in args


# ---------------------------------------------------------------------------
# list_repos
# ---------------------------------------------------------------------------

class TestListRepos:

    @patch("duckyai.ado._run_az")
    def test_parses_repo_list(self, mock_az):
        mock_az.return_value = json.dumps([
            {
                "id": "r1",
                "name": "MyRepo",
                "remoteUrl": "https://dev.azure.com/org/proj/_git/MyRepo",
                "sshUrl": "git@ssh.dev.azure.com:v3/org/proj/MyRepo",
                "defaultBranch": "refs/heads/main",
                "size": 1048576,
            },
        ])
        repos = list_repos("org", "proj")
        assert len(repos) == 1
        r = repos[0]
        assert r.name == "MyRepo"
        assert r.remote_url == "https://dev.azure.com/org/proj/_git/MyRepo"
        assert r.ssh_url == "git@ssh.dev.azure.com:v3/org/proj/MyRepo"
        assert r.default_branch == "refs/heads/main"
        assert r.size == 1048576

    @patch("duckyai.ado._run_az")
    def test_handles_missing_optional_fields(self, mock_az):
        mock_az.return_value = json.dumps([
            {"id": "r2", "name": "Minimal"},
        ])
        repos = list_repos("org", "proj")
        assert len(repos) == 1
        assert repos[0].remote_url == ""
        assert repos[0].default_branch == "refs/heads/main"
        assert repos[0].size == 0

    @patch("duckyai.ado._run_az", return_value=None)
    def test_az_failure_returns_empty(self, _):
        assert list_repos("org", "proj") == []

    @patch("duckyai.ado._run_az", return_value="bad json")
    def test_invalid_json_returns_empty(self, _):
        assert list_repos("org", "proj") == []


# ---------------------------------------------------------------------------
# clone_repo
# ---------------------------------------------------------------------------

class TestCloneRepo:

    @patch("duckyai.ado.shutil.which", return_value=None)
    def test_no_git_returns_false(self, _, tmp_path):
        assert clone_repo("https://example.com/repo.git", tmp_path / "dest") is False

    @patch("duckyai.ado.shutil.which", return_value="git")
    @patch("duckyai.ado.subprocess.run")
    def test_successful_clone(self, mock_run, _, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        dest = tmp_path / "dest"
        assert clone_repo("https://example.com/repo.git", dest) is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "git"
        assert call_args[1] == "clone"
        assert call_args[2] == "https://example.com/repo.git"

    @patch("duckyai.ado.shutil.which", return_value="git")
    @patch("duckyai.ado.subprocess.run")
    def test_failed_clone(self, mock_run, _, tmp_path):
        mock_run.return_value = MagicMock(returncode=128)
        assert clone_repo("https://example.com/bad.git", tmp_path / "dest") is False

    @patch("duckyai.ado.shutil.which", return_value="git")
    @patch("duckyai.ado.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 600))
    def test_timeout_returns_false(self, *_, tmp_path=None):
        # tmp_path not available in side_effect fixtures, use a manual temp
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            assert clone_repo("https://example.com/slow.git", Path(td) / "dest") is False

    @patch("duckyai.ado.shutil.which", return_value="git")
    @patch("duckyai.ado.subprocess.run")
    def test_creates_parent_dir(self, mock_run, _, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        dest = tmp_path / "deep" / "nested" / "repo"
        clone_repo("https://example.com/repo.git", dest)
        assert dest.parent.exists()
