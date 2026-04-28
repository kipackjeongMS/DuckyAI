"""Vault management CLI subcommand group.

Provides commands for managing the configured home vault:
    duckyai vault list                   — Show the configured home vault
    duckyai vault new                    — Create and configure a new home vault
    duckyai vault remove                 — Remove the home vault (deletes vault folder + runtime data)
    duckyai vault cleanup-legacy-runtime — Preview/remove stale ~/.duckyai/vaults/<id>/ folders
"""

import json
import os
import shutil
import signal
from pathlib import Path
from typing import Dict, List

import click

from ..logger import Logger
from ..vault_registry import (
    clear_home_vault,
    get_home_vault,
)
from .orch_cmd import _read_pid

logger = Logger(console_output=True)


def _get_legacy_runtime_root() -> Path:
    """Return the deprecated per-vault runtime root."""
    return Path.home() / ".duckyai" / "vaults"


def _collect_legacy_runtime_entries() -> List[Dict[str, object]]:
    """Inspect legacy runtime directories and classify cleanup safety."""
    home_vault = get_home_vault()
    registry = {home_vault["id"]: home_vault} if home_vault else {}
    legacy_root = _get_legacy_runtime_root()

    if not legacy_root.exists():
        return []

    entries: List[Dict[str, object]] = []
    for legacy_dir in sorted(p for p in legacy_root.iterdir() if p.is_dir()):
        vault_id = legacy_dir.name
        registered = registry.get(vault_id)
        vault_path = Path(registered["path"]) if registered and registered.get("path") else None
        vault_exists = bool(vault_path and vault_path.exists())
        vault_runtime = vault_path / ".duckyai" if vault_path else None
        vault_runtime_exists = bool(vault_runtime and vault_runtime.exists())
        pid = None
        orchestrator_running = False

        if vault_exists and vault_path is not None:
            pid, orchestrator_running = _read_pid(vault_path)

        if orchestrator_running:
            status = "running"
            reason = f"orchestrator is running for registered vault (PID {pid})"
        elif vault_exists and vault_runtime_exists:
            status = "safe"
            reason = "registered vault already has vault-local runtime"
        elif vault_exists:
            status = "review"
            reason = "registered vault exists but <vault>/.duckyai is missing"
        else:
            status = "orphaned"
            reason = "vault is not registered or the registered path no longer exists"

        entries.append(
            {
                "vault_id": vault_id,
                "legacy_dir": legacy_dir,
                "registered": registered is not None,
                "vault_path": vault_path,
                "vault_exists": vault_exists,
                "vault_runtime_exists": vault_runtime_exists,
                "orchestrator_running": orchestrator_running,
                "pid": pid,
                "status": status,
                "reason": reason,
            }
        )

    return entries


def _delete_legacy_runtime_entries(
    entries: List[Dict[str, object]],
    include_orphans: bool = False,
) -> Dict[str, int]:
    """Delete eligible legacy runtime directories and return summary counts."""
    deleted = 0
    skipped = 0

    for entry in entries:
        status = entry["status"]
        legacy_dir = entry["legacy_dir"]
        should_delete = status == "safe" or (include_orphans and status == "orphaned")

        if not should_delete:
            skipped += 1
            continue

        shutil.rmtree(legacy_dir)
        deleted += 1

    legacy_root = _get_legacy_runtime_root()
    if legacy_root.exists() and not any(legacy_root.iterdir()):
        legacy_root.rmdir()

    return {"deleted": deleted, "skipped": skipped}


@click.group("vault")
def vault_group():
    """Manage the configured DuckyAI home vault."""
    pass


@vault_group.command("open")
def vault_open():
    """Open the home vault folder in the system file explorer."""
    import subprocess as _sp
    import sys

    home_vault = get_home_vault()
    if not home_vault:
        click.echo("No home vault configured. Use 'duckyai setup'.")
        return

    vault_path = Path(home_vault["path"])
    if not vault_path.exists():
        click.echo(f"Vault path does not exist: {vault_path}", err=True)
        raise SystemExit(1)

    click.echo(f"Opening {vault_path} ...")
    if sys.platform == "win32":
        os.startfile(vault_path)
    elif sys.platform == "darwin":
        _sp.Popen(["open", str(vault_path)])
    else:
        _sp.Popen(["xdg-open", str(vault_path)])


@vault_group.command("list", hidden=True)
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON")
def vault_list(json_out):
    """Show the configured home vault."""
    home_vault = get_home_vault()

    if not home_vault:
        if json_out:
            click.echo(json.dumps({"home_vault": None}))
        else:
            click.echo("No home vault configured. Use 'duckyai setup'.")
        return

    results = []
    vault_path = Path(home_vault["path"])
    exists = vault_path.exists()
    pid, alive = _read_pid(vault_path) if exists else (None, False)
    entry = {
        "id": home_vault["id"],
        "name": home_vault["name"],
        "path": home_vault["path"],
        "exists": exists,
        "orchestrator_running": alive,
        "orchestrator_pid": pid,
        "last_used": home_vault.get("last_used"),
    }
    results.append(entry)

    if json_out:
        click.echo(json.dumps({"home_vault": results[0]}, indent=2))
    else:
        from rich.table import Table
        from rich.console import Console

        table = Table(title="Home Vault")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Path")
        table.add_column("Orchestrator", justify="center")

        for r in results:
            if not r["exists"]:
                orch_str = "⚠️  Path missing"
            elif r["orchestrator_running"]:
                orch_str = f"🟢 PID {r['orchestrator_pid']}"
            else:
                orch_str = "🔴 Stopped"
            table.add_row(r["id"], r["name"], r["path"], orch_str)

        Console().print(table)


@vault_group.command("new", hidden=True)
def vault_new():
    """Create and configure a new DuckyAI home vault via the onboarding wizard.

    \b
    Runs the same interactive setup as 'duckyai setup' — configures
    user info, agents, Teams sync, folder structure, and configures
    the resulting vault as the home vault.

    \b
    Example:
        duckyai vault new
    """
    from .setup import run_onboarding

    run_onboarding()


@vault_group.command("remove", hidden=True)
@click.argument("vault_id", required=False)
@click.option("--force", is_flag=True, help="Skip confirmation")
def vault_remove(vault_id, force):
    """Remove the configured home vault and its local data.

    \b
    This will:
      1. Stop the orchestrator if running
      2. Delete the vault folder (e.g., ~/MyVault/, including <vault>/.duckyai/)
      3. Delete the services folder (e.g., ~/MyVault-Services/)
      4. Clear the home vault configuration

    \b
    Examples:
        duckyai vault remove
        duckyai vault remove duckyai_vault --force
    """
    match = get_home_vault()

    if not match:
        click.echo("⚠️  No home vault is configured.", err=True)
        raise SystemExit(1)

    if vault_id and match["id"] != vault_id:
        click.echo(
            f"⚠️  Requested vault '{vault_id}' does not match the configured home vault '{match['id']}'.",
            err=True,
        )
        raise SystemExit(1)

    vault_path = Path(match["path"])
    vault_name = match["name"]
    vault_id = match["id"]
    services_path = match.get("services_path")

    # Show what will be deleted
    click.echo(f"\n  Vault: {vault_name} ({vault_id})")
    click.echo(f"  Vault folder:    {vault_path}" + (" ✓" if vault_path.exists() else " (not found)"))
    if services_path:
        click.echo(f"  Services folder: {services_path}" + (" ✓" if Path(services_path).exists() else " (not found)"))

    if not force:
        from .trigger_agent import _prompt_yn
        if not _prompt_yn(f"\n  ⚠️  Delete everything for vault '{vault_name}'?", default=False):
            click.echo("  Aborted.")
            return

    # 1. Stop orchestrator if running
    if vault_path.exists():
        pid, alive = _read_pid(vault_path)
        if alive and pid:
            click.echo(f"  Stopping orchestrator (PID {pid})...")
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            pid_file = vault_path / ".duckyai" / ".orchestrator.pid"
            pid_file.unlink(missing_ok=True)

    # 2. Delete vault folder (includes .duckyai/ runtime data)
    if vault_path.exists():
        try:
            shutil.rmtree(vault_path)
            click.echo(f"  ✓ Deleted vault folder: {vault_path}")
        except Exception as e:
            click.echo(f"  ⚠️  Could not delete vault folder: {e}", err=True)

    # 3. Delete services folder
    if services_path and Path(services_path).exists():
        try:
            shutil.rmtree(services_path)
            click.echo(f"  ✓ Deleted services folder: {services_path}")
        except Exception as e:
            click.echo(f"  ⚠️  Could not delete services folder: {e}", err=True)

    # 5. Clear home vault configuration
    removed = clear_home_vault()
    if removed:
        click.echo(f"  ✓ Cleared home vault configuration")
    click.echo(f"\n  Vault '{vault_name}' has been removed.")


@vault_group.command("cleanup-legacy-runtime", hidden=True)
@click.option("--apply", "apply_changes", is_flag=True, help="Delete eligible legacy runtime directories")
@click.option("--include-orphans", is_flag=True, help="Also delete orphaned legacy directories")
@click.option("--force", is_flag=True, help="Skip confirmation when used with --apply")
def vault_cleanup_legacy_runtime(apply_changes, include_orphans, force):
    """Preview or remove stale legacy runtime directories under ~/.duckyai/vaults/."""
    legacy_root = _get_legacy_runtime_root()
    entries = _collect_legacy_runtime_entries()

    if not entries:
        click.echo(f"No legacy runtime directories found under {legacy_root}")
        return

    click.echo(f"Legacy runtime root: {legacy_root}")
    click.echo("")
    for entry in entries:
        vault_id = entry["vault_id"]
        status = entry["status"]
        reason = entry["reason"]
        legacy_dir = entry["legacy_dir"]
        click.echo(f"- {vault_id}: {status}")
        click.echo(f"    path: {legacy_dir}")
        click.echo(f"    reason: {reason}")

    eligible = [
        entry for entry in entries
        if entry["status"] == "safe" or (include_orphans and entry["status"] == "orphaned")
    ]

    if not apply_changes:
        click.echo("")
        click.echo("Dry run only. Re-run with --apply to delete eligible directories.")
        if not include_orphans:
            click.echo("Use --include-orphans to also delete unregistered/missing-vault legacy directories.")
        return

    if not eligible:
        click.echo("")
        click.echo("No legacy runtime directories are eligible for automatic deletion.")
        return

    if not force:
        count = len(eligible)
        noun = "directory" if count == 1 else "directories"
        if not click.confirm(f"Delete {count} eligible legacy runtime {noun}?", default=False):
            click.echo("Aborted.")
            return

    summary = _delete_legacy_runtime_entries(entries, include_orphans=include_orphans)
    click.echo("")
    click.echo(f"Deleted {summary['deleted']} legacy runtime director{'y' if summary['deleted'] == 1 else 'ies'}.")
    if summary["skipped"]:
        click.echo(f"Skipped {summary['skipped']} director{'y' if summary['skipped'] == 1 else 'ies'} requiring review.")
