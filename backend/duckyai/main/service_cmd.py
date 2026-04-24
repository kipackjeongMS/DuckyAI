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


# duckyai service add-repo
@service_group.command("add-repo")
@click.argument("service_name")
@click.option("--url", "ado_url", type=str, help="ADO project URL (e.g. https://dev.azure.com/org/project)")
@click.option("--repo", "repo_name", type=str, help="Repo name to clone (skip interactive selection)")
@click.pass_context
def service_add_repo(ctx, service_name, ado_url, repo_name):
    """Clone an ADO repo into a service directory."""
    from ..ado import is_az_devops_available, parse_ado_project_url, list_repos, clone_repo
    from ..services import (
        get_services_path, get_service_entry,
        add_service,
    )

    vault_root = _resolve_vault_root(ctx)

    # Verify az devops is available
    available, msg = is_az_devops_available()
    if not available:
        click.echo(f"  ❌ {msg}", err=True)
        sys.exit(1)

    # Ensure service exists
    services_dir = get_services_path(vault_root)
    service_dir = services_dir / service_name
    entry = get_service_entry(vault_root, service_name)
    if not entry:
        if click.confirm(f"  Service '{service_name}' not registered. Create it?", default=True):
            service_dir = add_service(vault_root, service_name)
        else:
            sys.exit(1)

    # Resolve org + project from URL, service metadata, or prompt
    ado_org = None
    ado_project = None

    if ado_url:
        ado_org, ado_project = parse_ado_project_url(ado_url)
        if not ado_org or not ado_project:
            click.echo(f"  ❌ Could not parse org/project from URL: {ado_url}", err=True)
            sys.exit(1)
    else:
        # Try from service metadata (duckyai.yml entry)
        meta = (entry or {}).get("metadata") or {}
        ado_org = meta.get("organization")
        ado_project = meta.get("project")

    if not ado_org or not ado_project:
        ado_url = click.prompt(
            "  ADO project URL (e.g. https://dev.azure.com/org/project)"
        ).strip()
        ado_org, ado_project = parse_ado_project_url(ado_url)
        if not ado_org or not ado_project:
            click.echo(f"  ❌ Could not parse org/project from URL.", err=True)
            sys.exit(1)

    click.echo(f"  → org: {ado_org}, project: {ado_project}")

    # Resolve repo (from flag or prompt)
    if not repo_name:
        click.echo(f"  Fetching repos in {ado_project}...")
        repos = list_repos(ado_org, ado_project)
        if not repos:
            click.echo("  ❌ No repos found.", err=True)
            sys.exit(1)
        for i, r in enumerate(repos):
            size_mb = r.size / (1024 * 1024) if r.size else 0
            label = r.name + (f" ({size_mb:.0f} MB)" if size_mb > 1 else "")
            click.echo(f"    {i + 1}. {label}")
        idx = click.prompt(
            "  Select repo number",
            type=click.IntRange(1, len(repos)),
        ) - 1
        selected = repos[idx]
    else:
        # Lookup by name
        repos = list_repos(ado_org, ado_project)
        selected = next((r for r in repos if r.name == repo_name), None)
        if not selected:
            click.echo(f"  ❌ Repo '{repo_name}' not found in {ado_project}.", err=True)
            click.echo(f"  Available: {', '.join(r.name for r in repos)}", err=True)
            sys.exit(1)

    # Clone
    dest = service_dir / selected.name
    if dest.exists():
        click.echo(f"  · {selected.name}/ already exists at {dest}")
        sys.exit(0)

    click.echo(f"  Cloning {selected.name}...")
    if clone_repo(selected.remote_url, dest):
        click.echo(f"  ✅ Cloned {selected.name} into {dest}")
    else:
        click.echo(f"  ❌ Clone failed. Check git credentials and network.", err=True)
        sys.exit(1)
