"""Unit tests for CLI install health and doctor command."""

from pathlib import Path

from click.testing import CliRunner
import pytest

from duckyai_cli.main.cli import main
from duckyai_cli.main import doctor as doctor_module
from duckyai_cli.main import install_health


def test_get_duckyai_launch_cmd_prefers_healthy_wrapper(monkeypatch):
    wrapper_path = Path("C:/Python314/Scripts/duckyai.exe")
    monkeypatch.setattr(install_health, "get_duckyai_wrapper_path", lambda: wrapper_path)
    monkeypatch.setattr(install_health, "is_duckyai_wrapper_healthy", lambda wrapper_path=None: True)

    result = install_health.get_duckyai_launch_cmd("-o")

    assert result == [str(wrapper_path), "-o"]


def test_get_duckyai_launch_cmd_falls_back_when_wrapper_unhealthy(monkeypatch):
    monkeypatch.setattr(install_health, "get_duckyai_wrapper_path", lambda: Path("C:/Python314/Scripts/duckyai.exe"))
    monkeypatch.setattr(install_health, "is_duckyai_wrapper_healthy", lambda wrapper_path=None: False)

    result = install_health.get_duckyai_launch_cmd("-o")

    assert result[0].endswith("python.exe") or result[0].endswith("python")
    assert result[1:] == ["-m", "duckyai_cli", "-o"]


def test_repair_source_install_writes_pth(monkeypatch, tmp_path):
    source_dir = tmp_path / "cli"
    source_dir.mkdir()
    (source_dir / "pyproject.toml").write_text("[project]\nname='duckyai-cli'\n", encoding="utf-8")
    (source_dir / "duckyai_cli").mkdir()
    purelib = tmp_path / "site-packages"

    monkeypatch.setattr(install_health, "get_python_purelib", lambda: purelib)
    monkeypatch.setattr(install_health, "can_import_package_outside_checkout", lambda: (True, ""))

    result = install_health.repair_source_install(source_dir)

    assert result == purelib / install_health.REPO_PTH_FILENAME
    assert result.read_text(encoding="utf-8").strip() == str(source_dir.resolve())


def test_doctor_command_reports_json(monkeypatch):
    monkeypatch.setattr(
        doctor_module,
        "collect_install_diagnostics",
        lambda source_dir=None: {
            "python_executable": "C:/Python314/python.exe",
            "purelib": "C:/Python314/Lib/site-packages",
            "wrapper_path": "C:/Python314/Scripts/duckyai.exe",
            "wrapper_healthy": True,
            "import_ok": True,
            "import_error": None,
            "source_checkout": None,
            "repair_pth": "C:/Python314/Lib/site-packages/duckyai_cli_repo.pth",
            "repair_pth_exists": False,
            "copilot_sdk_import_ok": True,
            "copilot_sdk_python": "C:/Python314/python.exe",
        },
    )

    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--json-output"])

    assert result.exit_code == 0
    assert '"wrapper_healthy": true' in result.output


def test_doctor_command_repairs_install(monkeypatch, tmp_path):
    source_dir = tmp_path / "cli"
    source_dir.mkdir()

    monkeypatch.setattr(doctor_module, "repair_source_install", lambda source: tmp_path / "site-packages" / "duckyai_cli_repo.pth")
    monkeypatch.setattr(
        doctor_module,
        "collect_install_diagnostics",
        lambda source_dir=None: {
            "python_executable": "C:/Python314/python.exe",
            "purelib": "C:/Python314/Lib/site-packages",
            "wrapper_path": "C:/Python314/Scripts/duckyai.exe",
            "wrapper_healthy": True,
            "import_ok": True,
            "import_error": None,
            "source_checkout": str(source_dir),
            "repair_pth": "C:/Python314/Lib/site-packages/duckyai_cli_repo.pth",
            "repair_pth_exists": True,
            "copilot_sdk_import_ok": True,
            "copilot_sdk_python": "C:/Python314/python.exe",
        },
    )

    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--repair-install", "--source-dir", str(source_dir)])

    assert result.exit_code == 0
    assert "Repair wrote:" in result.output


def test_find_copilot_sdk_python_prefers_current_interpreter(monkeypatch):
    monkeypatch.setattr(install_health.sys, "executable", "C:/Python314/python.exe")
    monkeypatch.setattr(install_health, "iter_sdk_python_candidates", lambda: ["C:/Python314/python.exe", "C:/Other/python.exe"])
    monkeypatch.setattr(
        install_health,
        "python_can_import_module",
        lambda python_executable, module_name: python_executable == "C:/Python314/python.exe" and module_name == install_health.COPILOT_SDK_IMPORT_NAME,
    )

    result = install_health.find_copilot_sdk_python()

    assert result == "C:/Python314/python.exe"


def test_find_copilot_sdk_python_raises_when_missing(monkeypatch):
    monkeypatch.setattr(install_health, "iter_sdk_python_candidates", lambda: ["C:/Python314/python.exe"])
    monkeypatch.setattr(install_health, "python_can_import_module", lambda python_executable, module_name: False)

    with pytest.raises(FileNotFoundError, match="github-copilot-sdk"):
        install_health.find_copilot_sdk_python()