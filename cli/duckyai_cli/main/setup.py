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
    click.echo("\n📁 Step 1/9 — Vault Location")
    default_vault = str(vault_root) if vault_root else str(Path.cwd())
    vault_path = Path(click.prompt("  Where should your vault live?", default=default_vault))
    vault_path = vault_path.resolve()
    vault_path.mkdir(parents=True, exist_ok=True)
    click.echo(f"  ✓ Vault: {vault_path}")

    # ─── Step 2: About You ──────────────────────────────
    click.echo("\n👤 Step 2/9 — About You")
    user_name = click.prompt("  Your full name")
    primary_lang = click.prompt(
        "  Primary language",
        type=click.Choice(["en", "ko", "ja", "zh", "es", "fr", "de"], case_sensitive=False),
        default="en"
    )
    timezone = click.prompt("  Timezone", default=_detect_timezone())

    # ─── Step 3: GitHub Copilot Auth ────────────────────
    click.echo("\n🔑 Step 3/9 — GitHub Copilot")
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

    # ─── Step 4: MCP Server Build ───────────────────────
    click.echo("\n🔧 Step 4/9 — MCP Server")
    mcp_dir = vault_path / "mcp-server"
    if mcp_dir.exists() and (mcp_dir / "package.json").exists():
        click.echo("  Building vault MCP tools...")
        npm_cmd = shutil.which("npm")
        if not npm_cmd:
            click.echo("  ⚠️  npm not found — install Node.js and re-run")
        else:
            try:
                subprocess.run(
                    [npm_cmd, "install"], cwd=str(mcp_dir),
                    capture_output=True, timeout=120, shell=(os.name == "nt")
                )
                click.echo("  ✓ npm install complete")
                subprocess.run(
                    [npm_cmd, "run", "build"], cwd=str(mcp_dir),
                    capture_output=True, timeout=120, shell=(os.name == "nt")
                )
                click.echo("  ✓ TypeScript compiled")
            except Exception as e:
                click.echo(f"  ⚠️  Build failed: {e}")
    else:
        click.echo("  ℹ️  No mcp-server/ found — skipping build")

    # ─── Step 5: WorkIQ EULA ────────────────────────────
    click.echo("\n📋 Step 5/9 — WorkIQ (Teams Data)")
    eula_url = "https://github.com/microsoft/work-iq-mcp"
    click.echo(f"  EULA: {eula_url}")
    if click.confirm("  Accept WorkIQ EULA to enable Teams sync?", default=True):
        click.echo("  ✓ EULA acceptance noted (will be confirmed on first agent run)")
    else:
        click.echo("  ℹ️  Skipped — Teams sync agents will prompt later")

    # ─── Step 6: Vault Structure ────────────────────────
    click.echo("\n📂 Step 6/9 — Vault Structure")
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

    # ─── Step 7: Obsidian ───────────────────────────────
    click.echo("\n🗃️  Step 7/9 — Obsidian")
    obsidian_path = shutil.which("obsidian")
    if obsidian_path:
        click.echo("  ✓ Obsidian is installed")
    else:
        if click.confirm("  Obsidian not found. Install Obsidian?", default=False):
            webbrowser.open("https://obsidian.md/download")
            click.echo("  → Opening download page...")

    # ─── Step 8: Model Preference ───────────────────────
    click.echo("\n🤖 Step 8/9 — Default Model")
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
    click.echo("\n🔄 Step 9/9 — Teams Sync Schedule")
    teams_cron = _prompt_teams_schedule()

    # ─── Generate Config Files ──────────────────────────
    click.echo("\n⚙️  Generating configuration...")

    # duckyai.yaml
    duckyai_yaml_path = vault_path / "duckyai.yaml"
    duckyai_yaml = f"""# DuckyAI Workspace Configuration
# Generated by `duckyai init` on {today_str}

# User profile
user:
  name: "{user_name}"
  primaryLanguage: {primary_lang}
  timezone: "{timezone}"

# Orchestrator settings
orchestrator:
  auto_start: true
"""
    duckyai_yaml_path.write_text(duckyai_yaml, encoding="utf-8")
    click.echo(f"  ✓ duckyai.yaml")

    # Update orchestrator.yaml — set cron for TCS/TMS and model
    orch_yaml_path = vault_path / "orchestrator.yaml"
    if orch_yaml_path.exists():
        content = orch_yaml_path.read_text(encoding="utf-8")

        # Update default model
        import re
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

        orch_yaml_path.write_text(content, encoding="utf-8")
        click.echo(f"  ✓ orchestrator.yaml (updated)")
    else:
        click.echo("  ℹ️  orchestrator.yaml not found — skipping")

    # ─── Summary ────────────────────────────────────────
    click.echo("\n" + "=" * 50)
    click.echo("🎉 DuckyAI is ready!")
    click.echo("")
    click.echo(f"  Vault:      {vault_path}")
    click.echo(f"  User:       {user_name}")
    click.echo(f"  Language:   {primary_lang}")
    click.echo(f"  Model:      {model}")
    if teams_cron:
        click.echo(f"  Teams sync: {teams_cron}")
    else:
        click.echo(f"  Teams sync: disabled")
    click.echo("")
    click.echo("  Run `duckyai` to start your first session.")
    click.echo("")


@click.command("setup")
@click.option("--vault-path", type=click.Path(), default=None, help="Vault directory path")
def setup_command(vault_path):
    """Run the DuckyAI onboarding wizard."""
    vault = Path(vault_path) if vault_path else None
    run_onboarding(vault_root=vault)


def needs_onboarding(vault_root: Path) -> bool:
    """Check if onboarding is needed (no duckyai.yaml or missing user config)."""
    duckyai_yaml = vault_root / "duckyai.yaml"
    if not duckyai_yaml.exists():
        return True

    # Check if user section exists (added by onboarding)
    try:
        import yaml
        with duckyai_yaml.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return "user" not in data
    except Exception:
        return True
