"""Vault management CLI subcommand group.

Provides commands for managing registered vaults globally:
  duckyai vault list      — Show all registered vaults with orchestrator status
  duckyai vault new       — Create and register a new vault
  duckyai vault remove    — Unregister a vault (doesn't delete files)
"""

import json
from pathlib import Path

import click

from ..logger import Logger
from ..vault_registry import (
    list_vaults,
    register_vault,
    unregister_vault,
    find_vault_by_path,
)
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
    """Unregister a vault (does NOT delete vault files).

    \b
    Examples:
        duckyai vault remove doitall
        duckyai vault remove work --force
    """
    # Check if vault exists in registry
    vaults = list_vaults()
    match = next((v for v in vaults if v["id"] == vault_id), None)

    if not match:
        click.echo(f"⚠️  Vault '{vault_id}' not found in registry.", err=True)
        raise SystemExit(1)

    # Warn if orchestrator is running
    vault_path = Path(match["path"])
    if vault_path.exists():
        pid, alive = _read_pid(vault_path)
        if alive:
            click.echo(f"⚠️  Orchestrator is running (PID {pid}) for this vault.")
            if not force:
                if not click.confirm("Stop and unregister?"):
                    click.echo("Aborted.")
                    return

    if not force:
        if not click.confirm(f"Unregister vault '{match['name']}' ({match['path']})?"):
            click.echo("Aborted.")
            return

    removed = unregister_vault(vault_id)
    if removed:
        click.echo(f"✓ Unregistered vault '{match['name']}'")
        click.echo(f"  Files at {match['path']} are untouched.")
    else:
        click.echo(f"⚠️  Failed to unregister vault '{vault_id}'.", err=True)
