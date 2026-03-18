"""Vault management CLI subcommand group.

Provides commands for managing registered vaults globally:
  duckyai vault list      — Show all registered vaults with orchestrator status
  duckyai vault new       — Create and register a new vault
  duckyai vault remove    — Remove a vault (deletes vault folder + runtime data)
"""

import json
import shutil
import signal
import os
from pathlib import Path

import click

from ..logger import Logger
from ..vault_registry import (
    list_vaults,
    register_vault,
    unregister_vault,
    find_vault_by_path,
)
from ..config import Config
from .orch_cmd import _read_pid

logger = Logger(console_output=True)


@click.group("vault")
def vault_group():
    """Manage registered DuckyAI vaults."""
    pass


@vault_group.command("list")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON")
def vault_list(json_out):
    """List all registered vaults with orchestrator status."""
    vaults = list_vaults()

    if not vaults:
        if json_out:
            click.echo(json.dumps({"vaults": []}))
        else:
            click.echo("No vaults registered. Use 'duckyai vault new <path>' or 'duckyai init'.")
        return

    results = []
    for v in vaults:
        vault_path = Path(v["path"])
        exists = vault_path.exists()
        pid, alive = _read_pid(vault_path) if exists else (None, False)
        entry = {
            "id": v["id"],
            "name": v["name"],
            "path": v["path"],
            "exists": exists,
            "orchestrator_running": alive,
            "orchestrator_pid": pid,
            "last_used": v.get("last_used"),
        }
        results.append(entry)

    if json_out:
        click.echo(json.dumps({"vaults": results}, indent=2))
    else:
        from rich.table import Table
        from rich.console import Console

        table = Table(title="Registered Vaults")
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


@vault_group.command("new")
def vault_new():
    """Create and register a new DuckyAI vault via the onboarding wizard.

    \b
    Runs the same interactive setup as 'duckyai setup' — configures
    user info, agents, Teams sync, folder structure, and registers
    the vault.

    \b
    Example:
        duckyai vault new
    """
    from .setup import run_onboarding

    run_onboarding()


@vault_group.command("remove")
@click.argument("vault_id")
@click.option("--force", is_flag=True, help="Skip confirmation")
def vault_remove(vault_id, force):
    """Remove a vault — deletes vault folder, services folder, and runtime data.

    \b
    This will:
      1. Stop the orchestrator if running
      2. Delete the vault folder (e.g., ~/MyVault/, including <vault>/.duckyai/)
      3. Delete the services folder (e.g., ~/MyVault-Services/)
      4. Remove from vault registry

    \b
    Examples:
        duckyai vault remove test5
        duckyai vault remove test5 --force
    """
    vaults = list_vaults()
    match = next((v for v in vaults if v["id"] == vault_id), None)

    if not match:
        click.echo(f"⚠️  Vault '{vault_id}' not found in registry.", err=True)
        raise SystemExit(1)

    vault_path = Path(match["path"])
    vault_name = match["name"]
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
            pid_file = vault_path / ".orchestrator.pid"
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

    # 5. Remove from registry
    removed = unregister_vault(vault_id)
    if removed:
        click.echo(f"  ✓ Removed from vault registry")
    click.echo(f"\n  Vault '{vault_name}' has been removed.")
