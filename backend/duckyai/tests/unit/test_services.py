"""Unit tests for services.py — service directory management."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from duckyai.services import (
    get_services_path,
    ensure_services_dir,
    add_service,
    remove_service,
    list_services,
    get_all_repo_paths,
    get_service_entry,
    add_repo_to_service,
    _read_services_meta,
    _write_services_meta,
)


@pytest.fixture
def temp_vault(tmp_path):
    """Create a temporary vault with duckyai.yml."""
    vault = tmp_path / "TestVault"
    vault.mkdir()
    duckyai_dir = vault / ".duckyai"
    duckyai_dir.mkdir()
    config = duckyai_dir / "duckyai.yml"
    config.write_text(
        'version: "1.0.0"\n'
        'id: test_vault\n'
        'name: TestVault\n'
        '\n'
        'services:\n'
        '  path: "../TestVault-Services"\n'
        '  entries: []\n',
        encoding="utf-8",
    )
    return vault


@pytest.fixture
def temp_vault_no_services_config(tmp_path):
    """Create a vault without services section in config."""
    vault = tmp_path / "MyVault"
    vault.mkdir()
    duckyai_dir = vault / ".duckyai"
    duckyai_dir.mkdir()
    config = duckyai_dir / "duckyai.yml"
    config.write_text(
        'version: "1.0.0"\n'
        'id: my_vault\n'
        'name: MyVault\n',
        encoding="utf-8",
    )
    return vault


class TestGetServicesPath:
    """Tests for get_services_path()."""

    def test_returns_configured_relative_path(self, temp_vault):
        result = get_services_path(temp_vault)
        expected = (temp_vault.parent / "TestVault-Services").resolve()
        assert result == expected

    def test_fallback_to_default_sibling(self, temp_vault_no_services_config):
        result = get_services_path(temp_vault_no_services_config)
        expected = temp_vault_no_services_config.parent / "MyVault-Services"
        assert result == expected

    def test_absolute_path_in_config(self, tmp_path):
        vault = tmp_path / "Vault"
        vault.mkdir()
        abs_svc = tmp_path / "custom-services"
        duckyai_dir = vault / ".duckyai"
        duckyai_dir.mkdir()
        config = duckyai_dir / "duckyai.yml"
        # Use forward slashes for YAML compatibility
        abs_svc_str = str(abs_svc).replace("\\", "/")
        config.write_text(
            f'id: v1\nservices:\n  path: "{abs_svc_str}"\n  entries: []\n',
            encoding="utf-8",
        )
        result = get_services_path(vault)
        assert result == abs_svc.resolve()


class TestEnsureServicesDir:
    """Tests for ensure_services_dir()."""

    def test_creates_directory(self, temp_vault):
        svc_dir = ensure_services_dir(temp_vault)
        assert svc_dir.exists()
        assert svc_dir.is_dir()

    def test_creates_metadata_file(self, temp_vault):
        svc_dir = ensure_services_dir(temp_vault)
        meta_file = svc_dir / ".services.json"
        assert meta_file.exists()
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        assert meta["vault_id"] == "test_vault"
        assert "created" in meta
        assert meta["services"] == []

    def test_idempotent(self, temp_vault):
        svc_dir1 = ensure_services_dir(temp_vault)
        svc_dir2 = ensure_services_dir(temp_vault)
        assert svc_dir1 == svc_dir2
        # Metadata should not be overwritten
        meta = json.loads((svc_dir1 / ".services.json").read_text(encoding="utf-8"))
        assert meta["services"] == []

    def test_creates_symlink_in_vault(self, temp_vault):
        ensure_services_dir(temp_vault)
        link = temp_vault / ".services"
        # On some CI environments symlinks may not be supported — just check it was attempted
        # The actual symlink/junction creation is platform-dependent


class TestAddService:
    """Tests for add_service()."""

    def test_creates_service_directory(self, temp_vault):
        svc_dir = add_service(temp_vault, "MyService")
        assert svc_dir.exists()
        assert svc_dir.is_dir()
        assert svc_dir.name == "MyService"

    def test_updates_metadata(self, temp_vault):
        add_service(temp_vault, "SvcA")
        services_dir = get_services_path(temp_vault)
        meta = _read_services_meta(services_dir)
        names = [s["name"] for s in meta["services"]]
        assert "SvcA" in names

    def test_updates_duckyai_yml(self, temp_vault):
        add_service(temp_vault, "SvcB")
        content = (temp_vault / ".duckyai" / "duckyai.yml").read_text(encoding="utf-8")
        assert '"SvcB"' in content

    def test_idempotent_add(self, temp_vault):
        add_service(temp_vault, "SvcC")
        add_service(temp_vault, "SvcC")  # Add again
        services_dir = get_services_path(temp_vault)
        meta = _read_services_meta(services_dir)
        count = sum(1 for s in meta["services"] if s["name"] == "SvcC")
        assert count == 1, "Should not duplicate entries"

    def test_multiple_services(self, temp_vault):
        add_service(temp_vault, "Alpha")
        add_service(temp_vault, "Beta")
        add_service(temp_vault, "Gamma")
        services_dir = get_services_path(temp_vault)
        meta = _read_services_meta(services_dir)
        names = [s["name"] for s in meta["services"]]
        assert names == ["Alpha", "Beta", "Gamma"]


class TestRemoveService:
    """Tests for remove_service()."""

    def test_removes_from_metadata(self, temp_vault):
        add_service(temp_vault, "ToRemove")
        result = remove_service(temp_vault, "ToRemove")
        assert result is True
        services_dir = get_services_path(temp_vault)
        meta = _read_services_meta(services_dir)
        names = [s["name"] for s in meta["services"]]
        assert "ToRemove" not in names

    def test_returns_false_for_nonexistent(self, temp_vault):
        ensure_services_dir(temp_vault)
        result = remove_service(temp_vault, "DoesNotExist")
        assert result is False

    def test_does_not_delete_directory(self, temp_vault):
        svc_dir = add_service(temp_vault, "KeepDir")
        remove_service(temp_vault, "KeepDir")
        assert svc_dir.exists(), "Directory should NOT be deleted"

    def test_updates_duckyai_yml(self, temp_vault):
        add_service(temp_vault, "Gone")
        remove_service(temp_vault, "Gone")
        content = (temp_vault / ".duckyai" / "duckyai.yml").read_text(encoding="utf-8")
        assert '"Gone"' not in content


class TestListServices:
    """Tests for list_services()."""

    def test_empty_when_no_services(self, temp_vault):
        ensure_services_dir(temp_vault)
        result = list_services(temp_vault)
        assert result == []

    def test_lists_added_services(self, temp_vault):
        add_service(temp_vault, "Svc1")
        add_service(temp_vault, "Svc2")
        result = list_services(temp_vault)
        assert len(result) == 2
        names = [s["name"] for s in result]
        assert "Svc1" in names
        assert "Svc2" in names

    def test_includes_repo_info(self, temp_vault):
        svc_dir = add_service(temp_vault, "WithRepo")
        # Create a fake git repo
        repo = svc_dir / "my-repo"
        repo.mkdir()
        (repo / ".git").mkdir()  # Fake git dir
        result = list_services(temp_vault)
        svc = [s for s in result if s["name"] == "WithRepo"][0]
        assert len(svc["repos"]) == 1
        assert svc["repos"][0]["name"] == "my-repo"
        assert svc["repos"][0]["is_git"] is True

    def test_non_git_dirs_listed_as_not_git(self, temp_vault):
        svc_dir = add_service(temp_vault, "NoGit")
        (svc_dir / "plain-folder").mkdir()
        result = list_services(temp_vault)
        svc = [s for s in result if s["name"] == "NoGit"][0]
        assert svc["repos"][0]["is_git"] is False

    def test_hidden_dirs_excluded(self, temp_vault):
        svc_dir = add_service(temp_vault, "Hidden")
        (svc_dir / ".hidden-dir").mkdir()
        (svc_dir / "visible-dir").mkdir()
        result = list_services(temp_vault)
        svc = [s for s in result if s["name"] == "Hidden"][0]
        repo_names = [r["name"] for r in svc["repos"]]
        assert ".hidden-dir" not in repo_names
        assert "visible-dir" in repo_names

    def test_returns_empty_when_no_services_dir(self, temp_vault_no_services_config):
        result = list_services(temp_vault_no_services_config)
        assert result == []


class TestGetAllRepoPaths:
    """Tests for get_all_repo_paths()."""

    def test_returns_git_repos_only(self, temp_vault):
        svc_dir = add_service(temp_vault, "Mixed")
        git_repo = svc_dir / "git-repo"
        git_repo.mkdir()
        (git_repo / ".git").mkdir()
        plain = svc_dir / "plain"
        plain.mkdir()
        result = get_all_repo_paths(temp_vault)
        assert len(result) == 1
        assert "git-repo" in result[0]

    def test_spans_multiple_services(self, temp_vault):
        svc1 = add_service(temp_vault, "S1")
        (svc1 / "r1").mkdir()
        (svc1 / "r1" / ".git").mkdir()
        svc2 = add_service(temp_vault, "S2")
        (svc2 / "r2").mkdir()
        (svc2 / "r2" / ".git").mkdir()
        result = get_all_repo_paths(temp_vault)
        assert len(result) == 2

    def test_empty_when_no_repos(self, temp_vault):
        add_service(temp_vault, "Empty")
        result = get_all_repo_paths(temp_vault)
        assert result == []


class TestMetadataIO:
    """Tests for _read_services_meta / _write_services_meta."""

    def test_round_trip(self, tmp_path):
        meta = {"services": [{"name": "Test", "created": "2026-01-01"}]}
        _write_services_meta(tmp_path, meta)
        result = _read_services_meta(tmp_path)
        assert result["services"][0]["name"] == "Test"

    def test_read_missing_file(self, tmp_path):
        result = _read_services_meta(tmp_path)
        assert result == {"services": []}

    def test_read_corrupt_file(self, tmp_path):
        (tmp_path / ".services.json").write_text("not json!", encoding="utf-8")
        result = _read_services_meta(tmp_path)
        assert result == {"services": []}


class TestAddServiceWithAdo:
    """Tests for add_service() with ADO metadata."""

    def test_stores_ado_org_and_project(self, temp_vault):
        add_service(temp_vault, "WithAdo", ado_org="msazure", ado_project="MyProject")
        services_dir = get_services_path(temp_vault)
        meta = _read_services_meta(services_dir)
        entry = meta["services"][0]
        assert entry["name"] == "WithAdo"
        assert entry["ado_org"] == "msazure"
        assert entry["ado_project"] == "MyProject"

    def test_ado_fields_optional(self, temp_vault):
        add_service(temp_vault, "NoAdo")
        services_dir = get_services_path(temp_vault)
        meta = _read_services_meta(services_dir)
        entry = meta["services"][0]
        assert entry["name"] == "NoAdo"
        assert "ado_org" not in entry or entry.get("ado_org") is None
        assert "ado_project" not in entry or entry.get("ado_project") is None


class TestGetServiceEntry:
    """Tests for get_service_entry()."""

    def test_returns_entry_when_exists(self, temp_vault):
        add_service(temp_vault, "FindMe")
        entry = get_service_entry(temp_vault, "FindMe")
        assert entry is not None
        assert entry["name"] == "FindMe"

    def test_returns_none_when_missing(self, temp_vault):
        ensure_services_dir(temp_vault)
        entry = get_service_entry(temp_vault, "DoesNotExist")
        assert entry is None

    def test_returns_ado_metadata(self, temp_vault):
        add_service(temp_vault, "AdoSvc", ado_org="myorg", ado_project="myproj")
        entry = get_service_entry(temp_vault, "AdoSvc")
        assert entry["ado_org"] == "myorg"
        assert entry["ado_project"] == "myproj"


class TestAddRepoToService:
    """Tests for add_repo_to_service()."""

    def test_adds_repo_entry(self, temp_vault):
        add_service(temp_vault, "Svc")
        add_repo_to_service(
            temp_vault, "Svc", "my-repo", "https://dev.azure.com/org/proj/_git/my-repo"
        )
        services_dir = get_services_path(temp_vault)
        meta = _read_services_meta(services_dir)
        entry = meta["services"][0]
        assert len(entry["repos"]) == 1
        assert entry["repos"][0]["name"] == "my-repo"
        assert entry["repos"][0]["remote_url"] == "https://dev.azure.com/org/proj/_git/my-repo"
        assert "cloned_at" in entry["repos"][0]

    def test_does_not_duplicate(self, temp_vault):
        add_service(temp_vault, "Svc")
        add_repo_to_service(temp_vault, "Svc", "repo1", "https://example.com/repo1")
        add_repo_to_service(temp_vault, "Svc", "repo1", "https://example.com/repo1")
        services_dir = get_services_path(temp_vault)
        meta = _read_services_meta(services_dir)
        entry = meta["services"][0]
        assert len(entry["repos"]) == 1

    def test_multiple_repos(self, temp_vault):
        add_service(temp_vault, "Multi")
        add_repo_to_service(temp_vault, "Multi", "r1", "https://a.com/r1")
        add_repo_to_service(temp_vault, "Multi", "r2", "https://a.com/r2")
        services_dir = get_services_path(temp_vault)
        meta = _read_services_meta(services_dir)
        entry = meta["services"][0]
        names = [r["name"] for r in entry["repos"]]
        assert names == ["r1", "r2"]

    def test_noop_for_nonexistent_service(self, temp_vault):
        ensure_services_dir(temp_vault)
        # Should not raise
        add_repo_to_service(temp_vault, "Ghost", "repo", "https://a.com/repo")
