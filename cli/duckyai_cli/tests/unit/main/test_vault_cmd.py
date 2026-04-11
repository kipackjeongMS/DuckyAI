"""Unit tests for vault cleanup commands."""

from pathlib import Path

from click.testing import CliRunner

import duckyai_cli.main.cli as cli_module
from duckyai_cli.main import vault_cmd
from duckyai_cli.main.cli import main


def test_collect_legacy_runtime_entries_marks_safe(monkeypatch, tmp_path):
    legacy_root = tmp_path / ".duckyai" / "vaults"
    (legacy_root / "v1").mkdir(parents=True)

    vault_path = tmp_path / "Vault1"
    (vault_path / ".duckyai").mkdir(parents=True)

    monkeypatch.setattr(vault_cmd, "_get_legacy_runtime_root", lambda: legacy_root)
    monkeypatch.setattr(vault_cmd, "get_home_vault", lambda: {"id": "v1", "name": "Vault1", "path": str(vault_path)})
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
    monkeypatch.setattr(vault_cmd, "get_home_vault", lambda: {"id": "v1", "name": "Vault1", "path": str(vault_path)})
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
    monkeypatch.setattr(vault_cmd, "get_home_vault", lambda: {"id": "v1", "name": "Vault1", "path": str(vault_path)})
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
    monkeypatch.setattr(vault_cmd, "get_home_vault", lambda: {"id": "v1", "name": "Vault1", "path": str(vault_path)})
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


def test_init_command_registers_existing_vault(monkeypatch, tmp_path):
    vault_path = tmp_path / "Vault1"
    vault_path.mkdir()
    (vault_path / "duckyai.yml").write_text("id: vault1\nname: Vault One\n", encoding="utf-8")

    calls = []

    monkeypatch.setattr(vault_cmd, "find_vault_root", lambda path: Path(path))
    monkeypatch.setattr(vault_cmd, "get_home_vault", lambda: None)
    monkeypatch.setattr(cli_module, "ensure_init", lambda path: calls.append(("init", Path(path))))
    monkeypatch.setattr(vault_cmd, "ensure_services_dir", lambda path: (Path(path).parent / "Vault1-Services").resolve())

    def _set_home(vault_id, name, path, services_path=None):
        calls.append(("set_home", vault_id, name, Path(path), services_path))

    monkeypatch.setattr(vault_cmd, "set_home_vault", _set_home)

    runner = CliRunner()
    result = runner.invoke(main, ["init", str(vault_path)])

    assert result.exit_code == 0
    assert "Configured home vault: Vault One (vault1)" in result.output
    assert any(call[0] == "init" for call in calls)
    set_home_calls = [call for call in calls if call[0] == "set_home"]
    assert len(set_home_calls) == 2
    assert set_home_calls[-1][-1] == str((vault_path.parent / "Vault1-Services").resolve())


def test_init_command_reports_existing_home_vault(monkeypatch, tmp_path):
    vault_path = tmp_path / "Vault1"
    vault_path.mkdir()
    (vault_path / "duckyai.yml").write_text("id: vault1\nname: Vault One\n", encoding="utf-8")

    monkeypatch.setattr(vault_cmd, "find_vault_root", lambda path: Path(path))
    monkeypatch.setattr(
        vault_cmd,
        "get_home_vault",
        lambda: {"id": "vault1", "name": "Vault One", "path": str(vault_path)},
    )
    monkeypatch.setattr(cli_module, "ensure_init", lambda path: None)
    monkeypatch.setattr(vault_cmd, "ensure_services_dir", lambda path: (Path(path).parent / "Vault1-Services").resolve())
    monkeypatch.setattr(vault_cmd, "set_home_vault", lambda vault_id, name, path, services_path=None: None)

    runner = CliRunner()
    result = runner.invoke(main, ["init", str(vault_path)])

    assert result.exit_code == 0
    assert "Home vault already configured: Vault One (vault1)" in result.output


def test_init_command_fails_without_config(tmp_path):
    vault_path = tmp_path / "Vault1"
    vault_path.mkdir()

    runner = CliRunner()
    result = runner.invoke(main, ["init", str(vault_path)])

    assert result.exit_code != 0
    assert "No duckyai.yml found" in result.output
