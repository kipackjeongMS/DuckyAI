"""Service management CLI subcommand group.

Provides commands for managing services associated with a vault:
  duckyai service list      — Show registered services and their repos
  duckyai service add       — Register a new service
  duckyai service remove    — Unregister a service
  duckyai service path      — Print the services directory path
"""

import click
import json
import sys
from pathlib import Path


@click.group("service")
def service_group():
    """Manage services (code repos) linked to a vault."""
    pass


def _resolve_vault_root(ctx) -> Path:
    """Resolve vault root from CLI context."""
    obj = ctx.obj or {}
    vault_root = obj.get("vault_root")
    if vault_root:
        return Path(vault_root)

    from .vault import resolve_vault
    resolved = resolve_vault(obj.get("working_dir"))
    if (resolved / ".duckyai" / "duckyai.yml").exists() or (resolved / "duckyai.yml").exists():
        return resolved

    click.echo("Could not determine the home vault. Run 'duckyai init' or 'duckyai setup'.", err=True)
    sys.exit(1)


# duckyai service list
@service_group.command("list")
@click.option("--json-output", "json_out", is_flag=True, help="Output JSON")
@click.pass_context
def service_list(ctx, json_out):
    """List all registered services and their repos."""
    from ..services import list_services, get_services_path

    vault_root = _resolve_vault_root(ctx)
    services = list_services(vault_root)
    services_path = get_services_path(vault_root)

    if json_out:
        click.echo(json.dumps({
            "services_path": str(services_path),
            "services": services,
        }, indent=2))
        return

    if not services:
        click.echo(f"  No services registered.")
        click.echo(f"  Services dir: {services_path}")
        click.echo(f"  Use 'duckyai service add <name>' to register one.")
        return

    click.echo(f"\n  📂 Services: {services_path}\n")
    for svc in services:
        status = "✅" if svc["exists"] else "❌ (missing)"
        click.echo(f"  {status} {svc['name']}/")
        for repo in svc.get("repos", []):
            git_badge = "📦" if repo["is_git"] else "📁"
            click.echo(f"      {git_badge} {repo['name']}/")
        if not svc.get("repos"):
            click.echo(f"      (no repos yet)")
    click.echo()


# duckyai service add
@service_group.command("add")
@click.argument("name")
@click.pass_context
def service_add(ctx, name):
    """Register a new service and create its directory."""
    from ..services import add_service

    vault_root = _resolve_vault_root(ctx)
    service_dir = add_service(vault_root, name)
    click.echo(f"  ✅ Service '{name}' created at {service_dir}")
    click.echo(f"  Clone repos into this directory to get started.")


# duckyai service remove
@service_group.command("remove")
@click.argument("name")
@click.option("--force", is_flag=True, help="Skip confirmation")
@click.pass_context
def service_remove(ctx, name, force):
    """Unregister a service (does NOT delete files)."""
    from ..services import remove_service

    vault_root = _resolve_vault_root(ctx)

    if not force:
        click.confirm(f"Unregister service '{name}'? (files will NOT be deleted)", abort=True)

    if remove_service(vault_root, name):
        click.echo(f"  ✅ Service '{name}' unregistered.")
        click.echo(f"  (Directory was NOT deleted — remove manually if needed.)")
    else:
        click.echo(f"  ❌ Service '{name}' not found.", err=True)
        sys.exit(1)


# duckyai service path
@service_group.command("path")
@click.pass_context
def service_path(ctx):
    """Print the services directory path."""
    from ..services import get_services_path

    vault_root = _resolve_vault_root(ctx)
    click.echo(str(get_services_path(vault_root)))
