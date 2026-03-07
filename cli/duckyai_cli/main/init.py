"""Initialize DuckyAI vault — sets up symlinks so Copilot CLI uses the CLI-bundled config."""

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
    """Initialize vault by linking .github/ to the CLI-bundled Copilot config.

    \b
    This creates a symlink so Copilot CLI auto-discovers:
      - copilot-instructions.md (vault context)
      - skills/ (all workflow + knowledge skills)
      - prompts/ (all available commands)
    """
    vault_root = find_vault_root()

    # Find the CLI package's .github directory
    cli_github = Path(__file__).parent.parent / '.playbook'
    if not cli_github.exists():
        click.echo("Error: CLI .playbook/ not found in package.", err=True)
        return

    target = vault_root / '.github'
    rel_path = os.path.relpath(cli_github, vault_root)

    if target.is_symlink():
        current = os.readlink(target)
        if current == rel_path:
            click.echo(f"✅ Already initialized — .github → {rel_path}")
            return
        if not force:
            click.echo(f"⚠️  .github symlink exists pointing to: {current}")
            click.echo(f"   Run with --force to overwrite.")
            return
        target.unlink()

    elif target.exists():
        if not force:
            click.echo(f"⚠️  .github/ directory already exists (not a symlink).")
            click.echo(f"   Run with --force to replace it with a symlink.")
            return
        import shutil
        shutil.rmtree(target)

    os.symlink(rel_path, target)
    click.echo(f"✅ Initialized: .github → {rel_path}")
    click.echo(f"   Copilot CLI will now auto-discover instructions, skills, and prompts.")
