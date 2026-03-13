"""DuckyAI onboarding wizard — first-time setup for new users."""

import os
import sys
import shutil
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime

import click


def _detect_timezone() -> str:
    """Detect local timezone name."""
    try:
        import time
        if hasattr(time, 'tzname') and time.tzname[0]:
            return time.tzname[0]
    except Exception:
        pass
    return "America/Los_Angeles"


def _build_cron(frequency: str, minute: int = 0, hour: int = 18, interval: int = 1) -> str:
    """Build a cron expression from user-friendly inputs."""
    if frequency == "hourly":
        if interval == 1:
            return f"{minute} * * * *"
        else:
            return f"{minute} */{interval} * * *"
    elif frequency == "daily":
        return f"{minute} {hour} * * *"
    return "0 * * * *"


def _prompt_teams_schedule() -> str:
    """Interactive prompt to configure Teams sync cron schedule."""
    click.echo("\n📅 How often should Teams chats & meetings sync?")
    freq = click.prompt(
        "  Frequency",
        type=click.Choice(["hourly", "daily", "disabled"], case_sensitive=False),
        default="hourly"
    )

    if freq == "disabled":
        return ""

    if freq == "daily":
        time_str = click.prompt("  What time? (24h format HH:MM)", default="18:00")
        parts = time_str.split(":")
        hour = int(parts[0]) if parts else 18
        minute = int(parts[1]) if len(parts) > 1 else 0
        cron = _build_cron("daily", minute=minute, hour=hour)
        click.echo(f"  → Cron: {cron} (daily at {time_str})")
        return cron

    # Hourly
    click.echo("  Run every hour, or every N hours?")
    interval = click.prompt(
        "  Interval (1=every hour, 2=every 2 hours, etc.)",
        type=int, default=1
    )
    minute = click.prompt(
        "  At which minute past the hour?",
        type=int, default=0
    )
    cron = _build_cron("hourly", minute=minute, interval=interval)
    label = "every hour" if interval == 1 else f"every {interval} hours"
    click.echo(f"  → Cron: {cron} ({label} at :{minute:02d})")
    return cron


def run_onboarding(vault_root: Path = None):
    """Run the full onboarding wizard."""
    click.echo("")
    click.echo("👋 Welcome to DuckyAI! Let's set up your vault.")
    click.echo("=" * 50)

    # ─── Step 1: Vault Location ─────────────────────────
    click.echo("\n📁 Step 1/10 — Vault Location")
    vault_name = click.prompt("  What would you like to name your vault?", default="MyVault")
    default_location = str(vault_root) if vault_root else str(Path.cwd())
    vault_location = Path(click.prompt("  Where should your vault be created?", default=default_location))
    vault_path = (vault_location / vault_name).resolve()
    vault_path.mkdir(parents=True, exist_ok=True)
    click.echo(f"  ✓ Vault: {vault_path}")

    # ─── Step 2: About You ──────────────────────────────
    click.echo("\n👤 Step 2/10 — About You")
    user_name = click.prompt("  Your full name")
    primary_lang = click.prompt(
        "  Primary language",
        type=click.Choice(["en", "ko", "ja", "zh", "es", "fr", "de"], case_sensitive=False),
        default="en"
    )
    timezone = click.prompt("  Timezone", default=_detect_timezone())

    # ─── Step 3: GitHub Copilot Auth ────────────────────
    click.echo("\n🔑 Step 3/10 — GitHub Copilot")
    copilot_path = shutil.which("copilot")
    if copilot_path:
        click.echo(f"  ✓ Copilot CLI found: {copilot_path}")
        # Check auth
        try:
            result = subprocess.run(
                ["copilot", "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                click.echo(f"  ✓ Version: {result.stdout.strip().splitlines()[0]}")
        except Exception:
            pass
    else:
        click.echo("  ⚠️  Copilot CLI not found.")
        if click.confirm("  Install GitHub Copilot CLI?", default=True):
            click.echo("  → Visit: https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli")
            webbrowser.open("https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli")
            click.echo("  Install and re-run `duckyai` when ready.")

    # ─── Step 4: MCP Server ────────────────────────────
    click.echo("\n🔧 Step 4/10 — MCP Server")
    cli_root = Path(__file__).resolve().parent.parent.parent  # cli/duckyai_cli/main -> cli/
    mcp_js = cli_root / 'mcp-server' / 'dist' / 'index.js'
    if mcp_js.exists():
        click.echo("  ✓ MCP server found")
    else:
        click.echo("  ⚠️  MCP server not built — run: cd cli/mcp-server && npm install && npm run build")

    # ─── Step 5: WorkIQ EULA ────────────────────────────
    click.echo("\n📋 Step 5/10 — WorkIQ (Teams Data)")
    eula_url = "https://github.com/microsoft/work-iq-mcp"
    click.echo(f"  EULA: {eula_url}")
    if click.confirm("  Accept WorkIQ EULA to enable Teams sync?", default=True):
        click.echo("  ✓ EULA acceptance noted (will be confirmed on first agent run)")
    else:
        click.echo("  ℹ️  Skipped — Teams sync agents will prompt later")

    # ─── Step 6: Vault Structure ────────────────────────
    click.echo("\n📂 Step 6/10 — Vault Structure")
    folders = [
        "00-Inbox",
        "01-Work",
        "02-People",
        "02-People/Meetings",
        "03-Knowledge",
        "03-Knowledge/Documentation",
        "03-Knowledge/Topics",
        "04-Periodic",
        "04-Periodic/Daily",
        "04-Periodic/Weekly",
        "05-Archive",
        "Templates",
    ]
    for folder in folders:
        folder_path = vault_path / folder
        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)
            click.echo(f"  ✓ {folder}/")
        else:
            click.echo(f"  · {folder}/ (exists)")

    # Create .gitignore
    gitignore_path = vault_path / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(
            "# OS\n.DS_Store\nThumbs.db\n\n"
            "# Obsidian\n.obsidian/workspace*.json\n.obsidian/plugins/\n.trash/\n\n"
            "# Python\n__pycache__/\n*.pyc\n\n"
            "# Services directory junction (points outside vault)\n.services/\n",
            encoding="utf-8",
        )
        click.echo(f"  ✓ .gitignore")
    else:
        click.echo(f"  · .gitignore (exists)")

    # Create VS Code workspace file
    workspace_file = vault_path / f"{vault_name}.code-workspace"
    if not workspace_file.exists():
        import json
        workspace_config = {
            "folders": [
                {"name": vault_name, "path": "."}
            ],
            "settings": {
                "files.exclude": {
                    "**/.git": True,
                    "**/.obsidian/plugins": True,
                    "**/.obsidian/workspace*.json": True,
                    "**/.services": True,
                },
                "search.exclude": {
                    "**/.obsidian": True,
                    "**/.services": True,
                },
                "git.scanRepositories": ["."],
            },
        }
        workspace_file.write_text(
            json.dumps(workspace_config, indent=2), encoding="utf-8"
        )
        click.echo(f"  ✓ {vault_name}.code-workspace")
    else:
        click.echo(f"  · {vault_name}.code-workspace (exists)")

    # Create .vscode/mcp.json placeholder
    vscode_dir = vault_path / ".vscode"
    vscode_dir.mkdir(exist_ok=True)

    # Create profile note
    profile_path = vault_path / f"{user_name}.md"
    if not profile_path.exists():
        today = datetime.now().strftime("%Y-%m-%d")
        profile_content = f"""---
created: {today}
type: person
role: 
team: 
email: 
tags:
  - person
  - me
---

# {user_name}

## Role
- **Title:** 
- **Team:** 

## Contact
- **Email:** 

## Notes
- 
"""
        profile_path.write_text(profile_content, encoding="utf-8")
        click.echo(f"  ✓ {user_name}.md (profile)")
    else:
        click.echo(f"  · {user_name}.md (exists)")

    # Create first daily note
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_path = vault_path / "04-Periodic" / "Daily" / f"{today_str}.md"
    if not daily_path.exists():
        day_name = datetime.now().strftime("%A, %B %d, %Y")
        daily_content = f"""---
created: {today_str}
type: daily
date: {today_str}
tags:
  - daily
---

# {day_name}

## Focus Today
- [ ] 

## Carried from yesterday
- (none)

## PRs & Code Reviews
- 

## Meetings
- 

## Tasks Completed
- [x] 

## Technical Notes
- 

## End of Day
### What shipped?
- 

### Blockers / Risks
- 

### Carry forward to tomorrow
- [ ] 
"""
        daily_path.write_text(daily_content, encoding="utf-8")
        click.echo(f"  ✓ {today_str}.md (daily note)")
    else:
        click.echo(f"  · {today_str}.md (exists)")

    # ─── Step 7: IDE Selection ─────────────────────────────
    click.echo("\n🖥️  Step 7/10 — IDE")
    from .cli import _detect_ides
    available_ides = _detect_ides()
    selected_ide = None

    if available_ides:
        for name, exe in available_ides:
            click.echo(f"  ✓ {name} found")
        selected_ide = available_ides[0]  # Will open after setup
    else:
        click.echo("  ⚠️  No VS Code or VS Code Insiders found on PATH.")
        click.echo("  Install from: https://code.visualstudio.com/")

    # ─── Step 8: Model Preference ───────────────────────
    click.echo("\n🤖 Step 8/10 — Default Model")
    model = click.prompt(
        "  Default model for agents",
        type=click.Choice([
            "claude-sonnet-4.6",
            "gpt-5",
            "claude-opus-4.6",
            "claude-haiku-4.5",
        ], case_sensitive=False),
        default="claude-sonnet-4.6"
    )

    # ─── Step 9: Teams Sync Schedule ────────────────────
    click.echo("\n🔄 Step 9/10 — Teams Sync Schedule")
    teams_cron = _prompt_teams_schedule()

    # ─── Step 10: Services (Code Repos) ──────────────────
    click.echo("\n🛠️  Step 10/10 — Services (Code Repos)")
    click.echo("  Services are code projects you work on (each can contain git repos).")
    click.echo("  They live outside your vault in a sibling directory.\n")
    service_names = []
    while True:
        svc_name = click.prompt(
            "  Service name (leave empty to finish)",
            default="", show_default=False
        ).strip()
        if not svc_name:
            break
        service_names.append(svc_name)
        click.echo(f"    ✅ Added: {svc_name}")
    if not service_names:
        click.echo("  (No services added — you can add them later with 'duckyai service add')")

    # ─── Generate Config Files ──────────────────────────
    click.echo("\n⚙️  Generating configuration...")

    # duckyai.yml (single unified config)
    duckyai_yml_path = vault_path / "duckyai.yml"
    if duckyai_yml_path.exists():
        content = duckyai_yml_path.read_text(encoding="utf-8")

        # Ensure user: block exists; update if present
        import re
        if "user:" in content:
            content = re.sub(
                r'(user:\s*\n\s*name:\s*).*',
                f'\\1"{user_name}"',
                content
            )
            content = re.sub(
                r'(primaryLanguage:\s*).*',
                f'\\1{primary_lang}',
                content
            )
            content = re.sub(
                r'(timezone:\s*).*',
                f'\\1"{timezone}"',
                content
            )
        else:
            # Insert user block after version/id/name lines
            user_block = f"\nuser:\n  name: \"{user_name}\"\n  primaryLanguage: {primary_lang}\n  timezone: \"{timezone}\"\n"
            content = re.sub(r'(name:\s*.*\n)', f'\\1{user_block}', content, count=1)

        # Update default model
        content = re.sub(
            r'(model:\s*).*',
            f'\\1{model}',
            content
        )

        # Update TCS/TMS cron if teams sync is enabled
        if teams_cron:
            content = re.sub(
                r'(name: Teams Chat Summary \(TCS\)\n\s*cron:\s*)"[^"]*"',
                f'\\1"{teams_cron}"',
                content
            )
            content = re.sub(
                r'(name: Teams Meeting Summary \(TMS\)\n\s*cron:\s*)"[^"]*"',
                f'\\1"{teams_cron}"',
                content
            )
        else:
            # Disable TCS/TMS
            content = re.sub(
                r'(name: Teams Chat Summary \(TCS\)[\s\S]*?)(enabled:\s*)true',
                r'\1\2false',
                content
            )
            content = re.sub(
                r'(name: Teams Meeting Summary \(TMS\)[\s\S]*?)(enabled:\s*)true',
                r'\1\2false',
                content
            )

        duckyai_yml_path.write_text(content, encoding="utf-8")
        click.echo(f"  ✓ duckyai.yml (updated)")
    else:
        # Generate a fresh duckyai.yml for the new vault
        import re as _re2
        _vault_slug = _re2.sub(r'[^a-z0-9]+', '_', vault_name.lower()).strip('_') or "vault"
        tcs_enabled = "true" if teams_cron else "false"
        tms_enabled = "true" if teams_cron else "false"
        tcs_cron_val = teams_cron or "10 * * * *"
        tms_cron_val = teams_cron or "10 * * * *"
        duckyai_content = f"""version: "0.0.18"
id: {_vault_slug}
name: {vault_name}

user:
  name: "{user_name}"
  primaryLanguage: {primary_lang}
  timezone: "{timezone}"

services:
  path: "../{vault_name}-Services"
  entries: []

orchestrator:
  auto_start: true
  prompts_dir: .github/prompts-agent
  skills_dir: .github/skills
  bases_dir: .github/bases
  max_concurrent: 3
  poll_interval: 1
  file_extensions:
    - .md
    - .pdf
    - .docx
    - .doc
    - .txt
defaults:
  executor: copilot_cli
  timeout_minutes: 30
  max_parallel: 3
  task_create: true
  task_priority: medium
  task_archived: false
  agent_params:
    model: {model}
nodes:
  - type: agent
    name: Enrich Ingested Content (EIC)
    input_path: 00-Inbox
    output_path: 03-Knowledge/Documentation
    output_type: new_file
    enabled: true
  - type: agent
    name: Extract Document to Markdown (EDM)
    input_path: 00-Inbox
    output_path: 03-Knowledge/Documentation
    executor: copilot_cli
    input_type: new_file
    input_pattern: "*.pdf|*.docx|*.doc|*.txt"
    trigger_exclude_pattern: "*.md"
    output_naming: "{{title}}.md"
    enabled: true
  - type: agent
    name: Generate Daily Roundup (GDR)
    cron: 0 18 * * 1-5
    output_path: 04-Periodic/Daily
    requires_input_file: false
    enabled: true
  - type: agent
    name: Topic Index Update (TIU)
    cron: 30 18 * * 5
    input_path: 04-Periodic/Daily
    output_path: 03-Knowledge/Topics
    requires_input_file: false
    enabled: true
  - type: agent
    name: Teams Chat Summary (TCS)
    cron: "{tcs_cron_val}"
    output_path: 04-Periodic/Daily
    output_type: update_file
    executor: copilot_sdk
    requires_input_file: false
    enabled: {tcs_enabled}
  - type: agent
    name: Teams Meeting Summary (TMS)
    cron: "{tms_cron_val}"
    output_path: 04-Periodic/Daily
    output_type: update_file
    executor: copilot_sdk
    requires_input_file: false
    enabled: {tms_enabled}
"""
        duckyai_yml_path.write_text(duckyai_content, encoding="utf-8")
        click.echo(f"  ✓ duckyai.yml (created)")

    # ─── Summary ────────────────────────────────────────
    click.echo("\n" + "=" * 50)
    click.echo("🎉 DuckyAI is ready!")
    click.echo("")
    click.echo(f"  Vault:      {vault_path} ({vault_name})")
    click.echo(f"  User:       {user_name}")
    click.echo(f"  Language:   {primary_lang}")
    click.echo(f"  Model:      {model}")
    if teams_cron:
        click.echo(f"  Teams sync: {teams_cron}")
    else:
        click.echo(f"  Teams sync: disabled")
    click.echo("")

    # Register vault in global registry (~/.duckyai/vaults.json)
    from ..vault_registry import register_vault, list_vaults as _list_existing
    import yaml as _yaml
    import re as _re

    # Derive vault_id from duckyai.yml if present, otherwise from vault name
    _vault_id = None
    from duckyai_cli.config import CONFIG_FILENAME
    _config_path = vault_path / CONFIG_FILENAME
    if _config_path.exists():
        try:
            with _config_path.open("r", encoding="utf-8") as _fh:
                _config_data = _yaml.safe_load(_fh) or {}
                _id = _config_data.get("id")
                if _id and _id != "default":
                    _vault_id = _id
        except Exception:
            pass

    if not _vault_id:
        # Generate a unique slug from vault name (e.g. "My Vault" -> "my-vault")
        _vault_id = _re.sub(r'[^a-z0-9]+', '-', vault_name.lower()).strip('-') or "vault"
        # Ensure uniqueness against existing registry entries
        _existing_ids = {v["id"] for v in _list_existing()}
        _candidate = _vault_id
        _suffix = 2
        while _candidate in _existing_ids:
            _candidate = f"{_vault_id}-{_suffix}"
            _suffix += 1
        _vault_id = _candidate

    register_vault(
        vault_id=_vault_id,
        name=vault_name,
        path=vault_path,
    )
    click.echo(f"  ✓ Registered in ~/.duckyai/vaults.json")

    # Create services directory and register services
    from ..services import ensure_services_dir, add_service, get_services_path
    services_dir = ensure_services_dir(vault_path)
    click.echo(f"  ✓ Services directory: {services_dir}")
    for svc_name in service_names:
        add_service(vault_path, svc_name)
        click.echo(f"    ✓ Service: {svc_name}/")

    # Update vault registry with services_path
    register_vault(
        vault_id=_vault_id,
        name=vault_name,
        path=vault_path,
        services_path=str(services_dir),
    )

    # Initialize .github/skills symlinks so built-in skills are available immediately
    from .cli import ensure_init
    ensure_init(vault_path)
    click.echo(f"  ✓ Skills symlinked into .github/skills/")

    # Open vault in IDE if detected
    if selected_ide:
        ide_name, ide_exe = selected_ide
        click.echo(f"  🖥️  Opening vault in {ide_name}...")
        try:
            subprocess.Popen([ide_exe, str(vault_path)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            click.echo(f"  ⚠️  Could not launch {ide_name} automatically. Open it manually.")

    click.echo("")
    click.echo("  Run `duckyai` to start your first session.")
    click.echo("")


@click.command("setup")
@click.option("--vault-path", type=click.Path(), default=None, help="Vault directory path")
def setup_command(vault_path):
    """Run the DuckyAI onboarding wizard for the current vault."""
    vault = Path(vault_path) if vault_path else None
    run_onboarding(vault_root=vault)


@click.command("new")
@click.argument("vault_path", required=False, type=click.Path())
def new_command(vault_path):
    """Create a new DuckyAI vault.

    \b
    Sets up a fresh vault with folders, config, MCP server,
    and Teams sync schedule via an interactive wizard.

    \b
    Examples:
        duckyai new                    # Wizard prompts for location
        duckyai new ~/MyVault          # Create vault at specified path
    """
    vault = Path(vault_path).resolve() if vault_path else None
    run_onboarding(vault_root=vault)


def needs_onboarding(vault_root: Path) -> bool:
    """Check if onboarding is needed (no duckyai.yml or missing user config)."""
    from duckyai_cli.config import CONFIG_FILENAME
    duckyai_yml = vault_root / CONFIG_FILENAME
    if not duckyai_yml.exists():
        return True

    # Check if user section exists (added by onboarding)
    try:
        import yaml
        with duckyai_yml.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return "user" not in data
    except Exception:
        return True

