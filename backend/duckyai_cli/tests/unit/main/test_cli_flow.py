"""Regression tests for default CLI launch flow."""

import json
from pathlib import Path

from click.testing import CliRunner

import duckyai_cli.main.cli as cli_module
from duckyai_cli.main.cli import main


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


def test_default_command_selects_ide_then_prompts_teams_sync_then_opens_vault(monkeypatch, tmp_path):
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()

    call_order = []

    class _Config:
        def __init__(self, vault_path=None):
            self.orchestrator_auto_start = True

        def get(self, key, default=None):
            return "vault1" if key == "id" else default

    class _ExecutionManager:
        @staticmethod
        def check_workiq_auth_flag(vault_id, vault_path=None):
            return False

    monkeypatch.setattr(cli_module, "resolve_vault", lambda working_dir=None: vault_root)
    monkeypatch.setattr(cli_module, "ensure_init", lambda path: None)
    monkeypatch.setattr(cli_module, "_select_ide", lambda: call_order.append("select_ide") or ("VS Code", "code"))
    monkeypatch.setattr(cli_module, "ensure_orchestrator_running", lambda vault_root, debug=False: call_order.append("start_orchestrator") or True)
    monkeypatch.setattr(cli_module, "_open_vault_in_selected_ide", lambda path, selected_ide: call_order.append("open_vault"))
    monkeypatch.setattr(cli_module, "_prompt_startup_teams_sync", lambda path: call_order.append("teams_sync"))
    monkeypatch.setattr(cli_module, "launch_copilot", lambda *args, **kwargs: call_order.append("launch_copilot") or 0)
    monkeypatch.setattr(cli_module.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr("duckyai_cli.config.Config", _Config)
    monkeypatch.setattr("duckyai_cli.orchestrator.execution_manager.ExecutionManager", _ExecutionManager)

    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
    assert call_order == ["select_ide", "start_orchestrator", "teams_sync", "open_vault", "launch_copilot"]
    assert "Starting orchestrator background service..." in result.output


def test_default_command_skips_teams_sync_when_orchestrator_already_running(monkeypatch, tmp_path):
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()

    call_order = []

    class _Config:
        def __init__(self, vault_path=None):
            self.orchestrator_auto_start = True

        def get(self, key, default=None):
            return "vault1" if key == "id" else default

    class _ExecutionManager:
        @staticmethod
        def check_workiq_auth_flag(vault_id, vault_path=None):
            return False

    monkeypatch.setattr(cli_module, "resolve_vault", lambda working_dir=None: vault_root)
    monkeypatch.setattr(cli_module, "ensure_init", lambda path: None)
    monkeypatch.setattr(cli_module, "_select_ide", lambda: call_order.append("select_ide") or ("VS Code", "code"))
    monkeypatch.setattr(cli_module, "ensure_orchestrator_running", lambda vault_root, debug=False: call_order.append("start_orchestrator") or False)
    monkeypatch.setattr(cli_module, "_open_vault_in_selected_ide", lambda path, selected_ide: call_order.append("open_vault"))
    monkeypatch.setattr(cli_module, "_prompt_startup_teams_sync", lambda path: call_order.append("teams_sync"))
    monkeypatch.setattr(cli_module, "launch_copilot", lambda *args, **kwargs: call_order.append("launch_copilot") or 0)
    monkeypatch.setattr(cli_module.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr("duckyai_cli.config.Config", _Config)
    monkeypatch.setattr("duckyai_cli.orchestrator.execution_manager.ExecutionManager", _ExecutionManager)

    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
    assert call_order == ["select_ide", "start_orchestrator", "teams_sync", "open_vault", "launch_copilot"]
    assert "Starting orchestrator background service..." in result.output


def test_default_command_runs_onboarding_when_no_home_vault_is_configured(monkeypatch, tmp_path):
    working_dir = tmp_path / "OutsideVault"
    working_dir.mkdir()

    onboarding_calls = []

    monkeypatch.chdir(working_dir)
    monkeypatch.setattr(cli_module, "is_inside_vault", lambda path=None: False)
    monkeypatch.setattr(cli_module.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr("duckyai_cli.vault_registry.get_home_vault", lambda: None)
    monkeypatch.setattr(cli_module, "run_orchestrator_daemon", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run orchestrator")))
    monkeypatch.setattr(cli_module, "ensure_init", lambda path: (_ for _ in ()).throw(AssertionError("should not init current dir")))
    monkeypatch.setattr(cli_module, "launch_copilot", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not launch copilot")))

    def _run_onboarding(vault_root=None):
        onboarding_calls.append(vault_root)

    monkeypatch.setattr("duckyai_cli.main.setup.run_onboarding", _run_onboarding)

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


def test_launch_copilot_uses_new_terminal_for_interactive_windows(monkeypatch, tmp_path):
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()
    popen_calls = []

    class _Proc:
        pass

    monkeypatch.setattr(cli_module.os, "name", "nt", raising=False)
    monkeypatch.setattr(cli_module, "get_mcp_config", lambda vault_root: None)
    monkeypatch.setattr(cli_module, "_resolve_copilot_command", lambda: ["C:/copilot.exe"])
    monkeypatch.setattr(
        cli_module.subprocess,
        "Popen",
        lambda cmd, cwd=None, creationflags=0: popen_calls.append((cmd, cwd, creationflags)) or _Proc(),
    )

    result = cli_module.launch_copilot(vault_root)

    assert result == 0
    assert popen_calls == [(["C:/copilot.exe"], str(vault_root), 0x00000010)]


def test_launch_copilot_keeps_prompt_mode_inline(monkeypatch, tmp_path):
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()
    run_calls = []

    class _Completed:
        returncode = 7

    monkeypatch.setattr(cli_module, "get_mcp_config", lambda vault_root: None)
    monkeypatch.setattr(cli_module, "_resolve_copilot_command", lambda: ["copilot"])
    monkeypatch.setattr(
        cli_module.subprocess,
        "run",
        lambda cmd, cwd=None: run_calls.append((cmd, cwd)) or _Completed(),
    )

    result = cli_module.launch_copilot(vault_root, prompt="hello")

    assert result == 7
    assert run_calls == [(["copilot", "--prompt", "hello"], str(vault_root))]