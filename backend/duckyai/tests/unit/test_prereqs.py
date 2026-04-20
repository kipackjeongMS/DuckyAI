"""Tests for prerequisite checker (duckyai.prereqs).

Tests cover:
- Individual check functions (mock external commands)
- check_all aggregation
- auto_fix behavior
- Report formatting
- Edge cases (missing tools, version parsing)
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from duckyai.prereqs import (
    CheckResult,
    CheckStatus,
    PrereqReport,
    check_python,
    check_nodejs,
    check_git,
    check_docker,
    check_az_cli,
    check_az_devops_ext,
    check_copilot_sdk,
    check_copilot_cli,
    check_workiq,
    check_obsidian_plugin,
    check_vault_config,
    check_all,
    auto_fix,
    print_report,
    _run_cmd,
    _parse_version,
)


# ── Helpers ──────────────────────────────────────────────────────


class TestParseVersion:
    def test_simple(self):
        assert _parse_version("v22.7.0") == "22.7.0"

    def test_git_style(self):
        assert _parse_version("git version 2.44.0.windows.1") == "2.44.0"

    def test_no_version(self):
        assert _parse_version("no version here") is None

    def test_two_digit(self):
        assert _parse_version("Python 3.14") == "3.14"


class TestRunCmd:
    def test_success(self):
        result = _run_cmd([sys.executable, "-c", "print('hello')"])
        assert result == "hello"

    def test_failure_returns_none(self):
        result = _run_cmd(["nonexistent-binary-xyz"])
        assert result is None

    def test_timeout_returns_none(self):
        result = _run_cmd([sys.executable, "-c", "import time; time.sleep(5)"], timeout=1)
        assert result is None


# ── CheckResult / PrereqReport ───────────────────────────────────


class TestCheckResult:
    def test_ok(self):
        r = CheckResult("Test", CheckStatus.OK, version="1.0")
        assert r.ok
        assert r.symbol == "✅"

    def test_fail(self):
        r = CheckResult("Test", CheckStatus.FAIL, message="missing")
        assert not r.ok
        assert r.symbol == "❌"

    def test_warn(self):
        r = CheckResult("Test", CheckStatus.WARN)
        assert not r.ok
        assert r.symbol == "⚠️ "


class TestPrereqReport:
    def test_all_ok(self):
        report = PrereqReport(checks=[
            CheckResult("A", CheckStatus.OK),
            CheckResult("B", CheckStatus.OK),
        ])
        assert report.all_ok
        assert not report.has_blocking_failures

    def test_blocking_failure(self):
        report = PrereqReport(checks=[
            CheckResult("A", CheckStatus.OK),
            CheckResult("B", CheckStatus.FAIL, blocking=True),
        ])
        assert not report.all_ok
        assert report.has_blocking_failures

    def test_non_blocking_warn(self):
        report = PrereqReport(checks=[
            CheckResult("A", CheckStatus.OK),
            CheckResult("B", CheckStatus.WARN, fix_command="fix it", blocking=False),
        ])
        assert not report.all_ok
        assert not report.has_blocking_failures
        assert len(report.fixable) == 1

    def test_fixable_empty_when_all_ok(self):
        report = PrereqReport(checks=[CheckResult("A", CheckStatus.OK)])
        assert report.fixable == []


# ── Individual Check Functions ───────────────────────────────────


class TestCheckPython:
    def test_current_python_passes(self):
        result = check_python()
        assert result.ok  # We're running on 3.10+ (test requires it)
        assert result.version is not None

    @patch.object(sys, 'version_info', (3, 9, 0, 'final', 0))
    def test_old_python_fails(self):
        result = check_python()
        assert result.status == CheckStatus.FAIL
        assert result.blocking
        assert "3.10+" in result.message


class TestCheckNodejs:
    @patch('duckyai.prereqs._run_cmd', return_value="v22.7.0")
    def test_node_found(self, mock):
        result = check_nodejs()
        assert result.ok
        assert result.version == "22.7.0"

    @patch('shutil.which', return_value=None)
    def test_node_missing(self, mock):
        result = check_nodejs()
        assert result.status == CheckStatus.FAIL
        assert result.blocking

    @patch('duckyai.prereqs._run_cmd', return_value="v16.20.0")
    def test_node_too_old(self, mock):
        result = check_nodejs()
        assert result.status == CheckStatus.FAIL
        assert "18+" in result.message


class TestCheckGit:
    @patch('duckyai.prereqs._run_cmd', return_value="git version 2.44.0.windows.1")
    def test_git_found(self, mock):
        result = check_git()
        assert result.ok
        assert result.version == "2.44.0"

    @patch('duckyai.prereqs._run_cmd', return_value=None)
    def test_git_missing(self, mock):
        result = check_git()
        assert result.status == CheckStatus.FAIL
        assert result.blocking


class TestCheckDocker:
    @patch('shutil.which', return_value="/usr/bin/docker")
    @patch('duckyai.prereqs._run_cmd')
    def test_docker_running(self, mock_run, mock_which):
        mock_run.side_effect = lambda cmd, **kw: "Server Version: 27.0" if "info" in cmd else "Docker version 27.0.3"
        result = check_docker()
        assert result.ok

    @patch('shutil.which', return_value=None)
    def test_docker_missing(self, mock):
        result = check_docker()
        assert result.status == CheckStatus.WARN
        assert not result.blocking

    @patch('shutil.which', return_value="/usr/bin/docker")
    @patch('duckyai.prereqs._run_cmd', return_value=None)
    def test_docker_not_running(self, mock_run, mock_which):
        result = check_docker()
        assert result.status == CheckStatus.WARN
        assert "not running" in result.message


class TestCheckAzCli:
    @patch('shutil.which', return_value="/usr/bin/az")
    @patch('duckyai.prereqs._run_cmd', return_value="2.73.0")
    def test_az_found(self, mock_run, mock_which):
        result = check_az_cli()
        assert result.ok

    @patch('shutil.which', return_value=None)
    def test_az_missing(self, mock_which):
        # Also patch the Windows fallback
        with patch.object(Path, 'exists', return_value=False):
            result = check_az_cli()
        assert result.status == CheckStatus.WARN
        assert not result.blocking


class TestCheckAzDevopsExt:
    @patch('shutil.which', return_value="/usr/bin/az")
    @patch('duckyai.prereqs._run_cmd', return_value="1.0.1")
    def test_ext_installed(self, mock_run, mock_which):
        result = check_az_devops_ext()
        assert result.ok

    @patch('shutil.which', return_value="/usr/bin/az")
    @patch('duckyai.prereqs._run_cmd', return_value=None)
    def test_ext_missing(self, mock_run, mock_which):
        result = check_az_devops_ext()
        assert result.status == CheckStatus.WARN
        assert result.fix_command == "az extension add --name azure-devops"

    @patch('shutil.which', return_value=None)
    def test_skipped_no_az(self, mock):
        result = check_az_devops_ext()
        assert result.status == CheckStatus.WARN
        assert "Skipped" in result.message


class TestCheckCopilotSdk:
    def test_sdk_importable(self):
        # Should pass in our environment
        result = check_copilot_sdk()
        assert result.ok

    @patch.dict('sys.modules', {'copilot': None})
    def test_sdk_missing(self):
        # Force ImportError
        with patch('builtins.__import__', side_effect=ImportError("No module")):
            result = check_copilot_sdk()
        assert result.status == CheckStatus.FAIL


class TestCheckWorkiq:
    @patch('duckyai.prereqs._run_cmd', return_value="├── @microsoft/workiq@1.2.3")
    def test_installed(self, mock):
        result = check_workiq()
        assert result.ok

    @patch('duckyai.prereqs._run_cmd', return_value="(empty)")
    def test_not_installed(self, mock):
        result = check_workiq()
        assert result.status == CheckStatus.WARN
        assert "npm install" in result.fix_command


class TestCheckObsidianPlugin:
    def test_no_vault(self):
        result = check_obsidian_plugin(None)
        assert result.status == CheckStatus.WARN

    def test_plugin_installed(self, tmp_path):
        plugin_dir = tmp_path / ".obsidian" / "plugins" / "duckyai"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "main.js").write_text("// plugin")
        result = check_obsidian_plugin(tmp_path)
        assert result.ok

    def test_plugin_missing(self, tmp_path):
        (tmp_path / ".obsidian").mkdir()
        result = check_obsidian_plugin(tmp_path)
        assert result.status == CheckStatus.WARN
        assert "Not installed" in result.message

    def test_no_obsidian(self, tmp_path):
        result = check_obsidian_plugin(tmp_path)
        assert result.status == CheckStatus.WARN
        assert ".obsidian" in result.message


class TestCheckVaultConfig:
    def test_no_vault(self):
        result = check_vault_config(None)
        assert result.status == CheckStatus.WARN

    def test_valid_config(self, tmp_path):
        config = tmp_path / "duckyai.yml"
        config.write_text("nodes:\n  - name: TCS\n  - name: TMS\n")
        result = check_vault_config(tmp_path)
        assert result.ok
        assert "2 agents" in result.version

    def test_missing_config(self, tmp_path):
        result = check_vault_config(tmp_path)
        assert result.status == CheckStatus.WARN

    def test_invalid_yaml(self, tmp_path):
        config = tmp_path / "duckyai.yml"
        config.write_text("nodes: [[[invalid")
        result = check_vault_config(tmp_path)
        assert result.status == CheckStatus.WARN
        assert "Parse error" in result.message


# ── check_all ────────────────────────────────────────────────────


class TestCheckAll:
    @patch('duckyai.prereqs.check_python', return_value=CheckResult("Python", CheckStatus.OK, version="3.14"))
    @patch('duckyai.prereqs.check_nodejs', return_value=CheckResult("Node.js", CheckStatus.OK, version="22.7"))
    @patch('duckyai.prereqs.check_git', return_value=CheckResult("git", CheckStatus.OK, version="2.44"))
    @patch('duckyai.prereqs.check_copilot_sdk', return_value=CheckResult("SDK", CheckStatus.OK))
    @patch('duckyai.prereqs.check_copilot_cli', return_value=CheckResult("CLI", CheckStatus.OK))
    @patch('duckyai.prereqs.check_docker', return_value=CheckResult("Docker", CheckStatus.OK))
    @patch('duckyai.prereqs.check_az_cli', return_value=CheckResult("az", CheckStatus.OK))
    @patch('duckyai.prereqs.check_az_devops_ext', return_value=CheckResult("ext", CheckStatus.OK))
    @patch('duckyai.prereqs.check_workiq', return_value=CheckResult("wiq", CheckStatus.OK))
    def test_all_pass(self, *mocks):
        report = check_all()
        assert report.all_ok
        assert len(report.checks) == 9  # no vault checks when vault_path is None

    def test_includes_vault_checks_when_path_given(self, tmp_path):
        with patch('duckyai.prereqs._run_cmd', return_value="ok"):
            report = check_all(vault_path=tmp_path)
        # Should have vault-specific checks at the end
        names = [c.name for c in report.checks]
        assert "Obsidian plugin" in names
        assert "Vault config" in names


# ── auto_fix ─────────────────────────────────────────────────────


class TestAutoFix:
    def test_fixes_az_extension(self):
        report = PrereqReport(checks=[
            CheckResult("az devops extension", CheckStatus.WARN,
                       fix_command="az extension add --name azure-devops", blocking=False),
        ])
        with patch('duckyai.prereqs._run_cmd', return_value="installed"):
            actions = auto_fix(report)
        assert len(actions) == 1
        assert report.checks[0].ok

    def test_fixes_npm_package(self):
        report = PrereqReport(checks=[
            CheckResult("WorkIQ", CheckStatus.WARN,
                       fix_command="npm install -g @microsoft/workiq", blocking=False),
        ])
        with patch('duckyai.prereqs._run_cmd', return_value="installed"):
            actions = auto_fix(report)
        assert len(actions) == 1

    def test_skips_non_fixable(self):
        report = PrereqReport(checks=[
            CheckResult("Python", CheckStatus.FAIL,
                       fix_command="https://python.org", blocking=True),
        ])
        actions = auto_fix(report)
        assert len(actions) == 0  # URLs aren't auto-fixable


# ── print_report ─────────────────────────────────────────────────


class TestPrintReport:
    def test_no_crash(self, capsys):
        report = PrereqReport(checks=[
            CheckResult("Python", CheckStatus.OK, version="3.14"),
            CheckResult("Docker", CheckStatus.WARN, message="not running", fix_command="start it"),
            CheckResult("Node.js", CheckStatus.FAIL, message="missing", blocking=True),
        ])
        print_report(report)
        captured = capsys.readouterr()
        assert "Python" in captured.out
        assert "✅" in captured.out
        assert "⚠️" in captured.out
        assert "❌" in captured.out
        assert "Blocking" in captured.out
