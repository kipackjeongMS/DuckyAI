"""Helpers for diagnosing and repairing DuckyAI CLI installation health."""

from __future__ import annotations

import shutil
import subprocess
import os
import sys
import sysconfig
from pathlib import Path


PACKAGE_IMPORT_NAME = "duckyai"
REPO_PTH_FILENAME = "duckyai_repo.pth"
COPILOT_SDK_PACKAGE_NAME = "github-copilot-sdk"
COPILOT_SDK_IMPORT_NAME = "copilot"


def get_python_purelib() -> Path:
    """Return the current interpreter's purelib/site-packages directory."""
    return Path(sysconfig.get_paths()["purelib"]).resolve()


def python_can_import_module(python_executable: str, module_name: str) -> bool:
    """Return True when the given Python executable can import the module."""
    probe = subprocess.run(
        [python_executable, "-c", f"import {module_name}"],
        capture_output=True,
        text=True,
        cwd=str(Path.home()),
        timeout=10,
        check=False,
    )
    return probe.returncode == 0


def iter_sdk_python_candidates() -> list[str]:
    """Return ordered Python 3.10+ candidates for Copilot SDK execution."""
    candidates: list[str] = []

    def _add(candidate: str | None) -> None:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    _add(sys.executable)

    uv_python_dir = Path.home() / ".local" / "share" / "uv" / "python"
    if not uv_python_dir.exists():
        uv_python_dir = Path(os.environ.get("APPDATA", "")) / "uv" / "python"

    if uv_python_dir.exists():
        for ver_dir in sorted(uv_python_dir.iterdir(), reverse=True):
            if "cpython-3.1" in ver_dir.name or "cpython-3.2" in ver_dir.name:
                py = ver_dir / "python.exe" if sys.platform == "win32" else ver_dir / "bin" / "python3"
                if py.exists():
                    _add(str(py))

    for ver in ["3.14", "3.13", "3.12", "3.11", "3.10"]:
        _add(shutil.which(f"python{ver}"))

    _add(shutil.which("python3"))
    _add(shutil.which("python"))

    return candidates


def find_copilot_sdk_python() -> str:
    """Find a Python 3.10+ interpreter with the Copilot SDK installed."""
    for candidate in iter_sdk_python_candidates():
        if python_can_import_module(candidate, COPILOT_SDK_IMPORT_NAME):
            return candidate

    raise FileNotFoundError(
        "Python 3.10+ with the Copilot SDK was not found. "
        f"Install with: py -m pip install {COPILOT_SDK_PACKAGE_NAME}"
    )


def is_source_checkout(path: Path) -> bool:
    """Return True when the directory looks like the CLI source checkout."""
    return path.is_dir() and (path / "pyproject.toml").exists() and (path / "duckyai").is_dir()


def detect_source_checkout(candidate: Path | None = None) -> Path | None:
    """Detect a usable local source checkout for the CLI."""
    candidates: list[Path] = []
    if candidate is not None:
        candidates.append(Path(candidate).resolve())
    candidates.append(Path.cwd().resolve())
    candidates.append(Path(__file__).resolve().parents[2])

    seen: set[Path] = set()
    for current in candidates:
        if current in seen:
            continue
        seen.add(current)
        if is_source_checkout(current):
            return current
    return None


def get_duckyai_wrapper_path() -> Path | None:
    """Return the duckyai wrapper path when it exists on PATH."""
    wrapper = shutil.which("duckyai")
    return Path(wrapper).resolve() if wrapper else None


def can_import_package_outside_checkout() -> tuple[bool, str]:
    """Verify that a fresh Python process can import duckyai outside the repo."""
    probe = subprocess.run(
        [sys.executable, "-c", "import duckyai"],
        capture_output=True,
        text=True,
        cwd=str(Path.home()),
        timeout=10,
        check=False,
    )
    return probe.returncode == 0, probe.stderr.strip() or probe.stdout.strip()


def is_duckyai_wrapper_healthy(wrapper_path: Path | None = None) -> bool:
    """Return True when the shell wrapper can start successfully."""
    wrapper = wrapper_path or get_duckyai_wrapper_path()
    if not wrapper:
        return False

    probe = subprocess.run(
        [str(wrapper), "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path.home()),
        timeout=15,
        check=False,
    )
    return probe.returncode == 0


def get_duckyai_launch_cmd(*args: str) -> list[str]:
    """Return a launch command that avoids a broken duckyai.exe wrapper."""
    wrapper = get_duckyai_wrapper_path()
    if wrapper and is_duckyai_wrapper_healthy(wrapper):
        return [str(wrapper), *args]
    return [sys.executable, "-m", "duckyai", *args]


def write_source_checkout_pth(source_dir: Path) -> Path:
    """Register the source checkout in site-packages via a .pth file."""
    root = Path(source_dir).resolve()
    if not is_source_checkout(root):
        raise ValueError(f"Not a DuckyAI CLI source checkout: {root}")

    purelib = get_python_purelib()
    purelib.mkdir(parents=True, exist_ok=True)
    pth_path = purelib / REPO_PTH_FILENAME
    pth_path.write_text(f"{root}\n", encoding="utf-8")
    return pth_path


def repair_source_install(source_dir: Path | None = None) -> Path:
    """Repair local source checkout imports by creating a stable .pth file."""
    root = detect_source_checkout(source_dir)
    if root is None:
        raise ValueError("Could not detect a DuckyAI CLI source checkout")

    pth_path = write_source_checkout_pth(root)
    import_ok, error_text = can_import_package_outside_checkout()
    if not import_ok:
        raise RuntimeError(error_text or "duckyai is still not importable after repair")
    return pth_path


def collect_install_diagnostics(source_dir: Path | None = None) -> dict:
    """Collect installation diagnostics for doctor output."""
    source_checkout = detect_source_checkout(source_dir)
    wrapper_path = get_duckyai_wrapper_path()
    import_ok, import_error = can_import_package_outside_checkout()
    pth_path = get_python_purelib() / REPO_PTH_FILENAME
    sdk_import_ok = python_can_import_module(sys.executable, COPILOT_SDK_IMPORT_NAME)

    try:
        sdk_python = find_copilot_sdk_python()
    except FileNotFoundError:
        sdk_python = None

    return {
        "python_executable": sys.executable,
        "purelib": str(get_python_purelib()),
        "wrapper_path": str(wrapper_path) if wrapper_path else None,
        "wrapper_healthy": is_duckyai_wrapper_healthy(wrapper_path) if wrapper_path else False,
        "import_ok": import_ok,
        "import_error": import_error or None,
        "source_checkout": str(source_checkout) if source_checkout else None,
        "repair_pth": str(pth_path),
        "repair_pth_exists": pth_path.exists(),
        "copilot_sdk_import_ok": sdk_import_ok,
        "copilot_sdk_python": sdk_python,
    }