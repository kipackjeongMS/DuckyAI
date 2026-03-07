"""Dynamic command runner — turns .github/prompts/ into CLI commands and auto-loads skills."""

import os
import subprocess
import click
from pathlib import Path
from ..config import Config
from ..logger import Logger

logger = Logger()

VAULT_MARKERS = ['orchestrator.yaml', '.github', 'Home.md']


def find_vault_root(start: Path = None) -> Path:
    """Walk up from start to find the vault root."""
    current = start or Path.cwd()
    while current != current.parent:
        if any((current / m).exists() for m in VAULT_MARKERS):
            return current
        current = current.parent
    return start or Path.cwd()




def load_prompt_file(prompt_path: Path) -> str:
    """Read a prompt file and strip the YAML frontmatter."""
    content = prompt_path.read_text(encoding='utf-8')
    # Strip frontmatter (--- ... ---)
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            content = content[end + 3:].strip()
    return content


def get_available_prompts(vault_root: Path) -> dict:
    """Discover all available prompts from .github/prompts/ and _Settings_/Prompts/."""
    prompts = {}

    # .github/prompts/ — Copilot-style prompts (new-task, code-review, etc.)
    gh_prompts = vault_root / '.github' / 'prompts'
    if gh_prompts.exists():
        for f in sorted(gh_prompts.glob('*.prompt.md')):
            name = f.stem.replace('.prompt', '')
            prompts[name] = {'path': f, 'source': 'prompts'}

    # _Settings_/Prompts/ — Orchestrator prompts (EIC, GDR, etc.)
    settings_prompts = vault_root / '_Settings_' / 'Prompts'
    if settings_prompts.exists():
        for f in sorted(settings_prompts.glob('*.md')):
            if f.name in ('Prompts.md', 'README_PROMPTS.md'):
                continue
            # Extract abbreviation from name like "Enrich Ingested Content (EIC).md"
            import re
            abbrev_match = re.search(r'\((\w+)\)', f.stem)
            if abbrev_match:
                name = abbrev_match.group(1).lower()
                prompts[name] = {'path': f, 'source': 'agents'}

    return prompts


def run_prompt(vault_root: Path, prompt_content: str, user_input: str = None):
    """Execute a prompt via Copilot CLI."""
    full_prompt = prompt_content
    if user_input:
        full_prompt += f"\n\n# User Input\n{user_input}"

    cmd = ['copilot', '--prompt', full_prompt, '--allow-all-tools', '--output-format', 'text']

    try:
        result = subprocess.run(
            cmd,
            cwd=str(vault_root),
            timeout=1800,
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        logger.error("Command timed out after 30 minutes")
        return 1
    except FileNotFoundError:
        click.echo("Error: 'copilot' CLI not found. Install GitHub Copilot CLI first.", err=True)
        return 1


@click.command('run')
@click.argument('command', required=False)
@click.argument('args', nargs=-1)
@click.option('--list', 'list_cmds', is_flag=True, help='List all available commands')
@click.pass_context
def run_command(ctx, command, args, list_cmds):
    """Run a DuckyAI prompt command via Copilot CLI.

    \b
    Examples:
        duckyai run new-task
        duckyai run code-review
        duckyai run eic --file 00-Inbox/article.md
        duckyai run gdr
        duckyai run prioritize-work
        duckyai run --list
    """
    vault_root = find_vault_root()
    prompts = get_available_prompts(vault_root)

    if list_cmds or not command:
        click.echo("Available commands:\n")
        click.echo("  Vault prompts (.github/prompts/):")
        for name, info in sorted(prompts.items()):
            if info['source'] == 'prompts':
                click.echo(f"    {name:25s} ← {info['path'].name}")
        click.echo("\n  Agent prompts (_Settings_/Prompts/):")
        for name, info in sorted(prompts.items()):
            if info['source'] == 'agents':
                click.echo(f"    {name:25s} ← {info['path'].name}")
        return

    if command not in prompts:
        click.echo(f"Unknown command: '{command}'")
        click.echo(f"Run 'duckyai run --list' to see available commands.")
        return

    prompt_info = prompts[command]
    prompt_content = load_prompt_file(prompt_info['path'])

    user_input = ' '.join(args) if args else None

    click.echo(f"Running: {command} (via Copilot CLI)")
    if user_input:
        click.echo(f"Input: {user_input}")

    returncode = run_prompt(vault_root, prompt_content, user_input)
    if returncode != 0:
        click.echo(f"Command exited with code {returncode}", err=True)
