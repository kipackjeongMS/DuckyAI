"""Regression tests for default CLI launch flow."""

import json
from pathlib import Path

from click.testing import CliRunner

import duckyai.main.cli as cli_module
from duckyai.main.cli import main


def test_get_mcp_config_uses_native_python_vault_server(tmp_path):
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()

    config_json = cli_module.get_mcp_config(vault_root)
    config = json.loads(config_json)

    assert config["mcpServers"]["duckyai-vault"] == {
        "command": "duckyai-vault-mcp",
        "args": [],
        "env": {"DUCKYAI_VAULT_ROOT": str(vault_root)},
    }


def test_default_command_shows_help_when_no_subcommand(monkeypatch, tmp_path):
    """Bare `duckyai` with no args should display help listing subcommands."""
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()

    monkeypatch.setattr(cli_module, "resolve_vault", lambda working_dir=None: vault_root)
    monkeypatch.setattr(cli_module.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr("duckyai.vault_registry.get_home_vault", lambda: {"path": str(vault_root)})

    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
    # Help text should list known subcommands
    assert "setup" in result.output
    assert "update" in result.output
    assert "doctor" in result.output


def test_default_command_shows_help_even_with_vault_configured(monkeypatch, tmp_path):
    """Bare `duckyai` should show help even when a vault exists (no Copilot launch)."""
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()

    monkeypatch.setattr(cli_module, "resolve_vault", lambda working_dir=None: vault_root)
    monkeypatch.setattr(cli_module.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr("duckyai.vault_registry.get_home_vault", lambda: {"path": str(vault_root)})

    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
    assert "Commands:" in result.output or "Options:" in result.output


def test_default_command_runs_onboarding_when_no_home_vault_is_configured(monkeypatch, tmp_path):
    working_dir = tmp_path / "OutsideVault"
    working_dir.mkdir()

    onboarding_calls = []

    monkeypatch.chdir(working_dir)
    monkeypatch.setattr(cli_module, "is_inside_vault", lambda path=None: False)
    monkeypatch.setattr(cli_module.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr("duckyai.vault_registry.get_home_vault", lambda: None)
    monkeypatch.setattr(cli_module, "run_orchestrator_daemon", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run orchestrator")))
    monkeypatch.setattr(cli_module, "ensure_init", lambda path: (_ for _ in ()).throw(AssertionError("should not init current dir")))

    def _run_onboarding(vault_root=None):
        onboarding_calls.append(vault_root)

    monkeypatch.setattr("duckyai.main.setup.run_onboarding", _run_onboarding)

    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
    assert onboarding_calls == [working_dir.resolve()]
    assert "No home vault configured. Starting first-time setup..." in result.output


def test_ensure_orchestrator_running_keeps_healthy_process(monkeypatch, tmp_path):
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()

    monkeypatch.setattr(cli_module, "_cleanup_orchestrator_processes", lambda vault_root, fresh_start=False: {"healthy_pid": 4242})

    result = cli_module.ensure_orchestrator_running(vault_root)

    assert result is False


def test_config_subcommand_calls_show_config(monkeypatch, tmp_path):
    """Test that `duckyai config` invokes show_config with vault_root."""
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()

    show_config_calls = []

    monkeypatch.setattr(cli_module, "resolve_vault", lambda working_dir=None: vault_root)
    monkeypatch.setattr(cli_module.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr("duckyai.vault_registry.get_home_vault", lambda: {"path": str(vault_root)})
    monkeypatch.setattr(
        "duckyai.main.show_config.show_config",
        lambda vault_path=None: show_config_calls.append(vault_path),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["config"])

    assert result.exit_code == 0
    assert show_config_calls == [vault_root]