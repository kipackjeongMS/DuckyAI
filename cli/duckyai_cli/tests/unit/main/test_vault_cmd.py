"""Unit tests for vault cleanup commands."""

from pathlib import Path

from click.testing import CliRunner

from duckyai_cli.main import vault_cmd


def test_collect_legacy_runtime_entries_marks_safe(monkeypatch, tmp_path):
    legacy_root = tmp_path / ".duckyai" / "vaults"
    (legacy_root / "v1").mkdir(parents=True)

    vault_path = tmp_path / "Vault1"
    (vault_path / ".duckyai").mkdir(parents=True)

    monkeypatch.setattr(vault_cmd, "_get_legacy_runtime_root", lambda: legacy_root)
    monkeypatch.setattr(
        vault_cmd,
        "list_vaults",
        lambda: [{"id": "v1", "name": "Vault1", "path": str(vault_path)}],
    )
    monkeypatch.setattr(vault_cmd, "_read_pid", lambda path: (None, False))

    entries = vault_cmd._collect_legacy_runtime_entries()

    assert len(entries) == 1
    assert entries[0]["vault_id"] == "v1"
    assert entries[0]["status"] == "safe"
    assert entries[0]["vault_runtime_exists"] is True


def test_collect_legacy_runtime_entries_marks_review_when_local_runtime_missing(monkeypatch, tmp_path):
    legacy_root = tmp_path / ".duckyai" / "vaults"
    (legacy_root / "v1").mkdir(parents=True)

    vault_path = tmp_path / "Vault1"
    vault_path.mkdir()

    monkeypatch.setattr(vault_cmd, "_get_legacy_runtime_root", lambda: legacy_root)
    monkeypatch.setattr(
        vault_cmd,
        "list_vaults",
        lambda: [{"id": "v1", "name": "Vault1", "path": str(vault_path)}],
    )
    monkeypatch.setattr(vault_cmd, "_read_pid", lambda path: (None, False))

    entries = vault_cmd._collect_legacy_runtime_entries()

    assert len(entries) == 1
    assert entries[0]["status"] == "review"


def test_cleanup_legacy_runtime_dry_run_does_not_delete(monkeypatch, tmp_path):
    legacy_root = tmp_path / ".duckyai" / "vaults"
    legacy_dir = legacy_root / "v1"
    legacy_dir.mkdir(parents=True)

    vault_path = tmp_path / "Vault1"
    (vault_path / ".duckyai").mkdir(parents=True)

    monkeypatch.setattr(vault_cmd, "_get_legacy_runtime_root", lambda: legacy_root)
    monkeypatch.setattr(
        vault_cmd,
        "list_vaults",
        lambda: [{"id": "v1", "name": "Vault1", "path": str(vault_path)}],
    )
    monkeypatch.setattr(vault_cmd, "_read_pid", lambda path: (None, False))

    runner = CliRunner()
    result = runner.invoke(vault_cmd.vault_cleanup_legacy_runtime, [])

    assert result.exit_code == 0
    assert "Dry run only" in result.output
    assert legacy_dir.exists()


def test_cleanup_legacy_runtime_apply_deletes_safe_and_orphaned(monkeypatch, tmp_path):
    legacy_root = tmp_path / ".duckyai" / "vaults"
    safe_dir = legacy_root / "v1"
    orphan_dir = legacy_root / "orphan"
    safe_dir.mkdir(parents=True)
    orphan_dir.mkdir(parents=True)

    vault_path = tmp_path / "Vault1"
    (vault_path / ".duckyai").mkdir(parents=True)

    monkeypatch.setattr(vault_cmd, "_get_legacy_runtime_root", lambda: legacy_root)
    monkeypatch.setattr(
        vault_cmd,
        "list_vaults",
        lambda: [{"id": "v1", "name": "Vault1", "path": str(vault_path)}],
    )
    monkeypatch.setattr(vault_cmd, "_read_pid", lambda path: (None, False))

    runner = CliRunner()
    result = runner.invoke(
        vault_cmd.vault_cleanup_legacy_runtime,
        ["--apply", "--include-orphans", "--force"],
    )

    assert result.exit_code == 0
    assert "Deleted 2 legacy runtime directories." in result.output
    assert not safe_dir.exists()
    assert not orphan_dir.exists()
    assert not legacy_root.exists()
