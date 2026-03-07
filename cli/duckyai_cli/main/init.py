"""Initialize DuckyAI vault - sets up symlinks and runtime directories."""

import os
import click
from pathlib import Path


def find_vault_root(start: Path = None) -> Path:
    """Walk up from start to find the vault root (has orchestrator.yaml)."""
    current = start or Path.cwd()
    while current != current.parent:
        if (current / 'orchestrator.yaml').exists():
            return current
        current = current.parent
    return start or Path.cwd()


@click.command('init')
@click.option('--force', is_flag=True, help='Overwrite existing .github/ if present')
def init_vault(force):
    """Initialize vault: link .github/ to CLI playbook and create runtime dirs.

    \b
    Sets up:
      1. .github -> cli/.playbook (symlink for Copilot discovery)
      2. .duckyai/ runtime dirs (tasks, logs, history)
    """
    vault_root = find_vault_root()

    # --- 1. Symlink .github -> .playbook ---
    cli_playbook = Path(__file__).parent.parent / '.playbook'
    if not cli_playbook.exists():
        click.echo("Error: CLI .playbook/ not found in package.", err=True)
        return

    target = vault_root / '.github'
    rel_path = os.path.relpath(cli_playbook, vault_root)

    if target.is_symlink():
        current = os.readlink(target)
        if current == rel_path:
            click.echo(f"  .github -> {rel_path}")
        elif force:
            target.unlink()
            os.symlink(rel_path, target)
            click.echo(f"  .github -> {rel_path} (overwritten)")
        else:
            click.echo(f"  .github symlink exists -> {current}. Use --force to overwrite.")
    elif target.exists():
        if force:
            import shutil
            shutil.rmtree(target)
            os.symlink(rel_path, target)
            click.echo(f"  .github -> {rel_path} (replaced directory)")
        else:
            click.echo(f"  .github/ directory exists. Use --force to replace.")
    else:
        os.symlink(rel_path, target)
        click.echo(f"  .github -> {rel_path}")

    # --- 2. Create .duckyai/ runtime dirs ---
    runtime_dirs = ['.duckyai/tasks', '.duckyai/logs', '.duckyai/history']
    for d in runtime_dirs:
        full = vault_root / d
        if not full.exists():
            full.mkdir(parents=True, exist_ok=True)
            click.echo(f"  Created {d}/")
        else:
            click.echo(f"  {d}/ exists")

    click.echo("\nDuckyAI initialized. Run `duckyai` to start.")
