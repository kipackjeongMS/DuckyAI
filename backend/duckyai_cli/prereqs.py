"""
Prerequisite checker for DuckyAI installation.

Validates that all required tools and dependencies are present.
Used by both `duckyai setup` (Step 0) and `duckyai doctor`.
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


class CheckStatus(Enum):
    OK = "ok"
    WARN = "warn"       # Non-blocking, auto-fixable or optional
    FAIL = "fail"       # Blocking, must be resolved


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    version: Optional[str] = None
    message: Optional[str] = None
    fix_command: Optional[str] = None
    blocking: bool = True

    @property
    def ok(self) -> bool:
        return self.status == CheckStatus.OK

    @property
    def symbol(self) -> str:
        return {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}[self.status.value]


@dataclass
class PrereqReport:
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def has_blocking_failures(self) -> bool:
        return any(c.status == CheckStatus.FAIL and c.blocking for c in self.checks)

    @property
    def fixable(self) -> List[CheckResult]:
        return [c for c in self.checks if c.status == CheckStatus.WARN and c.fix_command]


def _run_cmd(cmd: List[str], timeout: int = 10) -> Optional[str]:
    """Run a command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            # shell=False is fine as long as callers use shutil.which() for the binary
        )
        if result.returncode == 0:
            return result.stdout.strip()
        # For installs, empty stdout with returncode 0 is still success
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _parse_version(output: str) -> Optional[str]:
    """Extract version-like string from command output."""
    import re
    m = re.search(r'(\d+\.\d+(?:\.\d+)*)', output)
    return m.group(1) if m else None


def check_python() -> CheckResult:
    """Check Python version >= 3.10."""
    vi = sys.version_info
    ver = f"{vi[0]}.{vi[1]}.{vi[2]}"
    if (vi[0], vi[1]) >= (3, 10):
        return CheckResult("Python", CheckStatus.OK, version=ver)
    return CheckResult(
        "Python", CheckStatus.FAIL, version=ver,
        message=f"Python 3.10+ required (found {ver})",
        fix_command="https://www.python.org/downloads/",
        blocking=True,
    )


def check_nodejs() -> CheckResult:
    """Check Node.js >= 18."""
    node_bin = shutil.which("node")
    if not node_bin:
        return CheckResult(
            "Node.js", CheckStatus.FAIL,
            message="Node.js not found on PATH",
            fix_command="https://nodejs.org/en/download/",
            blocking=True,
        )
    output = _run_cmd([node_bin, "--version"])
    if not output:
        return CheckResult("Node.js", CheckStatus.OK, version="unknown")
    ver = _parse_version(output)
    if ver:
        major = int(ver.split('.')[0])
        if major >= 18:
            return CheckResult("Node.js", CheckStatus.OK, version=ver)
        return CheckResult(
            "Node.js", CheckStatus.FAIL, version=ver,
            message=f"Node.js 18+ required (found {ver})",
            fix_command="https://nodejs.org/en/download/",
            blocking=True,
        )
    return CheckResult("Node.js", CheckStatus.OK, version=output)


def check_git() -> CheckResult:
    """Check git is installed."""
    output = _run_cmd(["git", "--version"])
    if not output:
        return CheckResult(
            "git", CheckStatus.FAIL,
            message="git not found on PATH",
            fix_command="https://git-scm.com/downloads",
            blocking=True,
        )
    ver = _parse_version(output)
    return CheckResult("git", CheckStatus.OK, version=ver)


def check_docker() -> CheckResult:
    """Check Docker is installed and running."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return CheckResult(
            "Docker", CheckStatus.WARN,
            message="Docker not found (only needed for container-mode agents)",
            fix_command="https://docs.docker.com/desktop/install/windows-install/",
            blocking=False,
        )
    output = _run_cmd(["docker", "info"], timeout=15)
    if output:
        ver_output = _run_cmd(["docker", "--version"])
        ver = _parse_version(ver_output) if ver_output else None
        return CheckResult("Docker", CheckStatus.OK, version=ver)
    return CheckResult(
        "Docker", CheckStatus.WARN,
        message="Docker installed but not running",
        fix_command="Start Docker Desktop",
        blocking=False,
    )


def check_az_cli() -> CheckResult:
    """Check Azure CLI is installed."""
    az_bin = shutil.which("az")
    if not az_bin:
        # Windows fallback
        candidate = Path(os.environ.get('ProgramFiles', '')) / 'Microsoft SDKs' / 'Azure' / 'CLI2' / 'wbin' / 'az.cmd'
        if candidate.exists():
            az_bin = str(candidate)
    if not az_bin:
        return CheckResult(
            "Azure CLI", CheckStatus.WARN,
            message="az CLI not found (needed for ADO integration)",
            fix_command="https://aka.ms/InstallAzureCLIDeb",
            blocking=False,
        )
    output = _run_cmd([az_bin, "version", "--output", "tsv"], timeout=15)
    ver = _parse_version(output) if output else None
    return CheckResult("Azure CLI", CheckStatus.OK, version=ver)


def check_az_devops_ext() -> CheckResult:
    """Check az devops extension is installed."""
    az_bin = shutil.which("az")
    if not az_bin:
        return CheckResult(
            "az devops extension", CheckStatus.WARN,
            message="Skipped (az CLI not found)",
            blocking=False,
        )
    output = _run_cmd([az_bin, "extension", "show", "--name", "azure-devops", "--query", "version", "-o", "tsv"], timeout=15)
    if output:
        return CheckResult("az devops extension", CheckStatus.OK, version=output)
    return CheckResult(
        "az devops extension", CheckStatus.WARN,
        message="Not installed",
        fix_command="az extension add --name azure-devops",
        blocking=False,
    )


def check_copilot_sdk() -> CheckResult:
    """Check GitHub Copilot SDK (Python) is importable."""
    try:
        import copilot
        ver = getattr(copilot, '__version__', 'unknown')
        return CheckResult("Copilot SDK", CheckStatus.OK, version=ver)
    except ImportError:
        return CheckResult(
            "Copilot SDK", CheckStatus.FAIL,
            message="github-copilot-sdk not installed",
            fix_command="pip install github-copilot-sdk",
            blocking=True,
        )


def check_copilot_cli() -> CheckResult:
    """Check Copilot CLI binary is available."""
    # Check bundled binary first
    try:
        from copilot import __file__ as copilot_init
        binary = "copilot.exe" if os.name == "nt" else "copilot"
        bundled = Path(copilot_init).resolve().parent / "bin" / binary
        if bundled.exists():
            return CheckResult("Copilot CLI", CheckStatus.OK, version="bundled")
    except ImportError:
        pass
    # Check PATH
    if shutil.which("copilot"):
        output = _run_cmd(["copilot", "--version"])
        ver = _parse_version(output) if output else None
        return CheckResult("Copilot CLI", CheckStatus.OK, version=ver)
    return CheckResult(
        "Copilot CLI", CheckStatus.FAIL,
        message="Copilot CLI binary not found",
        fix_command="pip install github-copilot-sdk",
        blocking=True,
    )


def check_workiq() -> CheckResult:
    """Check @microsoft/workiq npm package."""
    npm_bin = shutil.which("npm")
    if not npm_bin:
        return CheckResult(
            "WorkIQ MCP", CheckStatus.WARN,
            message="npm not found — cannot check WorkIQ",
            blocking=False,
        )
    output = _run_cmd([npm_bin, "list", "-g", "@microsoft/workiq", "--depth=0"], timeout=15)
    if output and "@microsoft/workiq" in output:
        ver = _parse_version(output.split("@microsoft/workiq@")[-1]) if "@microsoft/workiq@" in output else None
        return CheckResult("WorkIQ MCP", CheckStatus.OK, version=ver)
    return CheckResult(
        "WorkIQ MCP", CheckStatus.WARN,
        message="@microsoft/workiq not installed globally",
        fix_command="npm install -g @microsoft/workiq",
        blocking=False,
    )


def check_obsidian_plugin(vault_path: Optional[Path] = None) -> CheckResult:
    """Check if Obsidian plugin is installed in the vault."""
    if not vault_path:
        return CheckResult(
            "Obsidian plugin", CheckStatus.WARN,
            message="No vault path provided",
            blocking=False,
        )
    plugin_dir = vault_path / ".obsidian" / "plugins" / "duckyai"
    if (plugin_dir / "main.js").exists():
        return CheckResult("Obsidian plugin", CheckStatus.OK)
    if vault_path.joinpath(".obsidian").exists():
        return CheckResult(
            "Obsidian plugin", CheckStatus.WARN,
            message="Not installed in vault",
            fix_command="duckyai setup --install-plugin",
            blocking=False,
        )
    return CheckResult(
        "Obsidian plugin", CheckStatus.WARN,
        message="Obsidian vault not initialized (.obsidian/ missing)",
        blocking=False,
    )


def check_vault_config(vault_path: Optional[Path] = None) -> CheckResult:
    """Check duckyai.yml exists and is valid."""
    if not vault_path:
        return CheckResult("Vault config", CheckStatus.WARN, message="No vault", blocking=False)
    config_file = vault_path / "duckyai.yml"
    if not config_file.exists():
        config_file = vault_path / ".duckyai" / "duckyai.yml"
    if not config_file.exists():
        return CheckResult(
            "Vault config", CheckStatus.WARN,
            message="duckyai.yml not found",
            fix_command="duckyai setup",
            blocking=False,
        )
    try:
        import yaml
        data = yaml.safe_load(config_file.read_text(encoding='utf-8'))
        nodes = data.get("nodes", [])
        agent_count = len(nodes)
        return CheckResult("Vault config", CheckStatus.OK, version=f"{agent_count} agents")
    except Exception as e:
        return CheckResult(
            "Vault config", CheckStatus.WARN,
            message=f"Parse error: {e}",
            blocking=False,
        )


def check_all(vault_path: Optional[Path] = None) -> PrereqReport:
    """Run prerequisite checks.

    Without vault_path: checks only system tools (for pre-setup).
    With vault_path: also checks vault-specific items (for doctor).
    """
    report = PrereqReport()
    # System tools (required before vault setup)
    report.checks.append(check_python())
    report.checks.append(check_nodejs())
    report.checks.append(check_git())
    report.checks.append(check_copilot_sdk())
    report.checks.append(check_copilot_cli())
    report.checks.append(check_docker())
    report.checks.append(check_az_cli())
    report.checks.append(check_az_devops_ext())
    report.checks.append(check_workiq())
    # Vault-specific (only for doctor, not setup)
    if vault_path:
        report.checks.append(check_obsidian_plugin(vault_path))
        report.checks.append(check_vault_config(vault_path))
    return report


def auto_fix(report: PrereqReport) -> List[str]:
    """Attempt to auto-fix fixable issues. Returns list of actions taken."""
    actions = []
    for check in report.fixable:
        if not check.fix_command:
            continue
        # Only auto-fix safe shell commands
        if check.fix_command.startswith("az extension add"):
            az_bin = shutil.which("az")
            if az_bin:
                parts = check.fix_command.split()
                parts[0] = az_bin
                result = _run_cmd(parts, timeout=120)
                if result is not None:
                    check.status = CheckStatus.OK
                    check.message = "Auto-installed"
                    actions.append(f"Installed {check.name}")
        elif check.fix_command.startswith("npm install"):
            npm_bin = shutil.which("npm")
            if npm_bin:
                parts = check.fix_command.split()
                parts[0] = npm_bin
                result = _run_cmd(parts, timeout=120)
                if result is not None:
                    check.status = CheckStatus.OK
                    check.message = "Auto-installed"
                    actions.append(f"Installed {check.name}")
    return actions


def print_report(report: PrereqReport) -> None:
    """Print a formatted prereq report to stdout."""
    print("\n🔍 Checking prerequisites...\n")
    for check in report.checks:
        ver = f" {check.version}" if check.version else ""
        line = f"  {check.symbol} {check.name}{ver}"
        if check.message and check.status != CheckStatus.OK:
            line += f" — {check.message}"
        print(line)
        if check.fix_command and check.status != CheckStatus.OK:
            print(f"     → {check.fix_command}")
    print()
    if report.has_blocking_failures:
        print("  ❌ Blocking issues found. Please resolve them before continuing.\n")
    elif report.fixable:
        print("  ⚠️  Some optional tools missing (auto-fixable).\n")
    else:
        print("  All prerequisites met! ✅\n")
