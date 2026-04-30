"""Installation diagnostics and self-repair command."""

from __future__ import annotations

import json
from pathlib import Path

import click

from .install_health import collect_install_diagnostics, repair_source_install


@click.command("doctor")
@click.option("--repair-install", is_flag=True, help="Repair local source-checkout imports by writing a site-packages .pth file")
@click.option(
    "--source-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Path to the CLI source checkout (directory containing pyproject.toml)",
)
@click.option("--json-output", "json_out", is_flag=True, help="Output diagnostics as JSON")
def doctor_command(repair_install: bool, source_dir: Path | None, json_out: bool) -> None:
    """Diagnose and repair local DuckyAI CLI installation issues."""
    repair_path = None
    if repair_install:
        try:
            repair_path = repair_source_install(source_dir)
        except (RuntimeError, ValueError) as exc:
            if json_out:
                click.echo(json.dumps({"ok": False, "error": str(exc)}))
            else:
                click.echo(f"Repair failed: {exc}", err=True)
            raise SystemExit(1) from exc

    diagnostics = collect_install_diagnostics(source_dir)
    if repair_path is not None:
        diagnostics["repair_written"] = str(repair_path)

    if json_out:
        click.echo(json.dumps(diagnostics, indent=2))
        return

    # ── Prerequisites (same surface as `duckyai setup` Step 0) ──
    from ..prereqs import check_all, print_report

    prereq_report = check_all()
    print_report(prereq_report)

    # ── Recent update failure (helps diagnose silent self-update bugs) ──
    from .update import _recent_failed_update_log

    failed_log = _recent_failed_update_log()
    if failed_log is not None:
        click.echo("Recent update failure detected")
        click.echo(f"  Log: {failed_log}")
        try:
            tail = failed_log.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in tail[-15:]:
                click.echo(f"  | {line}")
        except OSError:
            pass
        click.echo("  Likely cause: duckyai.exe / duckyai-vault-mcp.exe was locked by")
        click.echo("  Obsidian or Copilot CLI during install. Close those apps and run")
        click.echo("  'duckyai update --force' to retry.")
        click.echo()

    click.echo("DuckyAI installation health")
    click.echo(f"  Python: {diagnostics['python_executable']}")
    click.echo(f"  Site-packages: {diagnostics['purelib']}")
    click.echo(f"  duckyai wrapper: {diagnostics['wrapper_path'] or 'not found'}")
    click.echo(f"  Wrapper healthy: {'yes' if diagnostics['wrapper_healthy'] else 'no'}")
    click.echo(f"  Import outside checkout: {'yes' if diagnostics['import_ok'] else 'no'}")
    click.echo(f"  Copilot SDK in current Python: {'yes' if diagnostics['copilot_sdk_import_ok'] else 'no'}")
    if diagnostics["import_error"]:
        click.echo(f"  Import error: {diagnostics['import_error']}")
    if diagnostics["copilot_sdk_python"]:
        click.echo(f"  Copilot SDK Python: {diagnostics['copilot_sdk_python']}")
    if diagnostics["source_checkout"]:
        click.echo(f"  Source checkout: {diagnostics['source_checkout']}")
    if diagnostics["repair_pth_exists"]:
        click.echo(f"  Repair link: {diagnostics['repair_pth']}")

    if repair_path is not None:
        click.echo(f"\nRepair wrote: {repair_path}")
        click.echo("Imports should now work from a fresh shell.")
    elif not diagnostics["import_ok"]:
        click.echo("\nSuggested repair:")
        click.echo("  From a source checkout, run `py -m duckyai doctor --repair-install --source-dir <path-to-cli>`")
        click.echo("  For a fresh editable install on Windows, prefer `py -m pip install -e .[dev] --config-settings editable_mode=compat`")
    elif not diagnostics["copilot_sdk_import_ok"]:
        click.echo("\nSuggested repair:")
        click.echo("  Install the Copilot SDK into the Python environment that runs DuckyAI:")
        click.echo("  `py -m pip install github-copilot-sdk`")