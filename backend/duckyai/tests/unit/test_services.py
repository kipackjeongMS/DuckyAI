"""Unit tests for services.py — service directory management."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from duckyai.services import (
    get_services_path,
    ensure_services_dir,
    add_service,
    remove_service,
    list_services,
    get_all_repo_paths,
    get_service_entry,
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


def _read_yml_entries(vault: Path) -> list:
    """Helper to read services.entries from duckyai.yml for assertions."""
    config_path = vault / ".duckyai" / "duckyai.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return (data.get("services") or {}).get("entries") or []


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

    def test_no_services_json_created(self, temp_vault):
        svc_dir = ensure_services_dir(temp_vault)
        assert not (svc_dir / ".services.json").exists()

    def test_idempotent(self, temp_vault):
        svc_dir1 = ensure_services_dir(temp_vault)
        svc_dir2 = ensure_services_dir(temp_vault)
        assert svc_dir1 == svc_dir2


class TestAddService:
    """Tests for add_service()."""

    def test_creates_service_directory(self, temp_vault):
        svc_dir = add_service(temp_vault, "MyService")
        assert svc_dir.exists()
        assert svc_dir.is_dir()
        assert svc_dir.name == "MyService"

    def test_updates_duckyai_yml(self, temp_vault):
        add_service(temp_vault, "SvcB")
        entries = _read_yml_entries(temp_vault)
        names = [e["name"] for e in entries]
        assert "SvcB" in names

    def test_idempotent_add(self, temp_vault):
        add_service(temp_vault, "SvcC")
        add_service(temp_vault, "SvcC")
        entries = _read_yml_entries(temp_vault)
        count = sum(1 for e in entries if e["name"] == "SvcC")
        assert count == 1, "Should not duplicate entries"

    def test_multiple_services(self, temp_vault):
        add_service(temp_vault, "Alpha")
        add_service(temp_vault, "Beta")
        add_service(temp_vault, "Gamma")
        entries = _read_yml_entries(temp_vault)
        names = [e["name"] for e in entries]
        assert names == ["Alpha", "Beta", "Gamma"]

    def test_preserves_existing_yml_content(self, temp_vault):
        """Adding a service must not destroy other duckyai.yml fields."""
        add_service(temp_vault, "Svc1")
        content = (temp_vault / ".duckyai" / "duckyai.yml").read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        assert data["version"] == "1.0.0"
        assert data["id"] == "test_vault"

    def test_with_metadata(self, temp_vault):
        add_service(temp_vault, "WithMeta", metadata={
            "type": "ado",
            "organization": "myorg",
            "project": "myproj",
        })
        entries = _read_yml_entries(temp_vault)
        entry = entries[0]
        assert entry["metadata"]["type"] == "ado"
        assert entry["metadata"]["organization"] == "myorg"
        assert entry["metadata"]["project"] == "myproj"

    def test_with_pr_scan(self, temp_vault):
        add_service(temp_vault, "Scanned", pr_scan=True)
        entries = _read_yml_entries(temp_vault)
        assert entries[0]["pr_scan"] is True

    def test_metadata_optional(self, temp_vault):
        add_service(temp_vault, "NoMeta")
        entries = _read_yml_entries(temp_vault)
        entry = entries[0]
        assert "metadata" not in entry
        assert "pr_scan" not in entry

    def test_creates_services_section_if_missing(self, temp_vault_no_services_config):
        svc_dir = add_service(temp_vault_no_services_config, "NewSvc")
        assert svc_dir.exists()
        entries = _read_yml_entries(temp_vault_no_services_config)
        assert len(entries) == 1
        assert entries[0]["name"] == "NewSvc"


class TestRemoveService:
    """Tests for remove_service()."""

    def test_removes_from_yml(self, temp_vault):
        add_service(temp_vault, "ToRemove")
        result = remove_service(temp_vault, "ToRemove")
        assert result is True
        entries = _read_yml_entries(temp_vault)
        names = [e["name"] for e in entries]
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
        entries = _read_yml_entries(temp_vault)
        names = [e.get("name") for e in entries]
        assert "Gone" not in names

    def test_preserves_other_entries(self, temp_vault):
        add_service(temp_vault, "Keep1")
        add_service(temp_vault, "Remove")
        add_service(temp_vault, "Keep2")
        remove_service(temp_vault, "Remove")
        entries = _read_yml_entries(temp_vault)
        names = [e["name"] for e in entries]
        assert names == ["Keep1", "Keep2"]

    def test_preserves_metadata_of_remaining_entries(self, temp_vault):
        """Removing a service must not wipe metadata of other entries."""
        add_service(temp_vault, "Rich", metadata={"type": "ado", "organization": "o"}, pr_scan=True)
        add_service(temp_vault, "Doomed")
        remove_service(temp_vault, "Doomed")
        entries = _read_yml_entries(temp_vault)
        assert len(entries) == 1
        assert entries[0]["metadata"]["organization"] == "o"
        assert entries[0]["pr_scan"] is True


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
        repo = svc_dir / "my-repo"
        repo.mkdir()
        (repo / ".git").mkdir()
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

    def test_returns_metadata(self, temp_vault):
        add_service(temp_vault, "MetaSvc", metadata={
            "type": "ado",
            "organization": "myorg",
            "project": "myproj",
        })
        entry = get_service_entry(temp_vault, "MetaSvc")
        assert entry["metadata"]["organization"] == "myorg"
        assert entry["metadata"]["project"] == "myproj"

    def test_returns_plain_dict(self, temp_vault):
        add_service(temp_vault, "Plain")
        entry = get_service_entry(temp_vault, "Plain")
        assert type(entry) is dict
