"""Initialize DuckyAI vault - sets up user directories and runtime dirs."""

import os
import click
from .vault import find_vault_root



@click.command('init')
@click.option('--force', is_flag=True, help='Force cleanup of legacy junctions')
def init_vault(force):
    """Initialize vault: create user directories and global runtime dirs.

    \b
    Sets up:
      1. .github/skills/ (user-owned custom skills directory)
      2. <vault_root>/.duckyai/ runtime dirs (tasks, logs, history, state)

    System files (prompts-agent, bases, templates, etc.) are
    managed by the CLI package and NOT placed in .github/.
    """
    from .cli import _is_junction

    vault_root = find_vault_root()

    # --- 1. Set up .github/skills/ (user-owned) ---
    github_dir = vault_root / '.github'

    # Clean up legacy: if .github is a junction/symlink to .playbook, remove it
    if github_dir.is_symlink() or _is_junction(github_dir):
        if force:
            if os.name == 'nt':
                os.rmdir(str(github_dir))
            else:
                github_dir.unlink()
            click.echo("  Removed legacy .github junction")
        else:
            click.echo("  .github is a legacy junction. Use --force to clean up.")
            return
    elif github_dir.is_file():
        github_dir.unlink()
        click.echo("  Removed broken .github symlink file")

    # Ensure .github/ is a real directory
    github_dir.mkdir(parents=True, exist_ok=True)

    # Clean up legacy junctions inside .github/ (from previous versions)
    for subdir in ('prompts-agent', 'bases', 'templates', 'guidelines', 'prompts'):
        link = github_dir / subdir
        if link.is_symlink() or _is_junction(link):
            if os.name == 'nt':
                os.rmdir(str(link))
            else:
                link.unlink()
            click.echo(f"    Removed legacy {subdir}/ junction")

    # Clean up legacy copied file
    ci_file = github_dir / 'copilot-instructions.md'
    if ci_file.is_symlink() or (ci_file.exists() and not ci_file.is_dir()):
        ci_file.unlink()

    # Ensure .github/skills/ exists (user-owned)
    skills_dir = github_dir / 'skills'
    if not skills_dir.exists():
        skills_dir.mkdir(parents=True, exist_ok=True)
        click.echo("  .github/skills/ (created, user-owned)")
    else:
        click.echo("  .github/skills/ (exists, user-owned)")

    # --- 2. Create .duckyai/ vault-local runtime dirs ---
    from duckyai_cli.config import get_global_runtime_dir, CONFIG_FILENAME
    import yaml as _yaml
    vault_id = "default"
    config_path = vault_root / CONFIG_FILENAME
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as fh:
                data = _yaml.safe_load(fh) or {}
                vault_id = data.get("id", "default")
        except Exception:
            pass
    runtime_dir = get_global_runtime_dir(vault_id, vault_path=vault_root)
    runtime_subdirs = ["tasks", "logs", "history", "state"]
    for d in runtime_subdirs:
        full = runtime_dir / d
        if not full.exists():
            full.mkdir(parents=True, exist_ok=True)
            click.echo(f"  Created .duckyai/{d}/")
        else:
            click.echo(f"  .duckyai/{d}/ exists")

    click.echo("\nDuckyAI initialized. Run `duckyai` to start.")
