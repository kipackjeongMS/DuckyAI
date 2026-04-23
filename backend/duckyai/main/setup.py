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
    """Detect local timezone as an IANA name (e.g. ``America/Los_Angeles``).

    Priority: Windows ``time.tzname`` mapped via Config's table → tzlocal → hardcoded fallback.
    """
    # Map common Windows timezone display names to IANA
    _WIN_MAP = {
        "Pacific Standard Time": "America/Los_Angeles",
        "Pacific Daylight Time": "America/Los_Angeles",
        "Mountain Standard Time": "America/Denver",
        "Mountain Daylight Time": "America/Denver",
        "Central Standard Time": "America/Chicago",
        "Central Daylight Time": "America/Chicago",
        "Eastern Standard Time": "America/New_York",
        "Eastern Daylight Time": "America/New_York",
        "Alaskan Standard Time": "America/Anchorage",
        "Alaskan Daylight Time": "America/Anchorage",
        "Hawaiian Standard Time": "Pacific/Honolulu",
        "Atlantic Standard Time": "America/Halifax",
        "Atlantic Daylight Time": "America/Halifax",
        "GMT Standard Time": "Europe/London",
        "Central European Standard Time": "Europe/Berlin",
        "China Standard Time": "Asia/Shanghai",
        "Tokyo Standard Time": "Asia/Tokyo",
        "Korea Standard Time": "Asia/Seoul",
        "AUS Eastern Standard Time": "Australia/Sydney",
        "India Standard Time": "Asia/Kolkata",
    }
    try:
        import time
        if hasattr(time, 'tzname') and time.tzname[0]:
            win_name = time.tzname[0]
            if win_name in _WIN_MAP:
                return _WIN_MAP[win_name]
            # If it already looks like an IANA name (contains '/'), use as-is
            if '/' in win_name:
                return win_name
    except Exception:
        pass
    # Fallback: try tzlocal
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            from tzlocal import get_localzone
            tz = str(get_localzone())
            if tz and tz not in ("UTC", "Etc/UTC"):
                return tz
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


# ---------------------------------------------------------------------------
# ADO integration helpers for setup flow
# ---------------------------------------------------------------------------

def _prompt_ado_for_service(
    service_name: str,
    default_url: str | None = None,
) -> tuple[str | None, str | None, list]:
    """Prompt user for ADO project URL → repos for one service.

    Returns ``(ado_org, ado_project, selected_repos)`` where
    ``selected_repos`` is a list of ``AdoRepo`` dataclass instances.
    Returns ``(None, None, [])`` if the user cancels at any point.
    """
    from ..ado import parse_ado_project_url, list_repos

    # 1) Project URL
    hint = " (e.g. https://dev.azure.com/org/project)"
    url = click.prompt(
        f"    ADO project URL{hint}",
        default=default_url or "", show_default=bool(default_url),
    ).strip()
    if not url:
        click.echo("    (skipped)")
        return None, None, []

    org, project = parse_ado_project_url(url)
    if not org or not project:
        click.echo("    ⚠ Could not parse org/project from URL")
        return None, None, []
    click.echo(f"    → org: {org}, project: {project}")

    # 2) Repo multi-select
    click.echo("    Fetching repos...")
    repos = list_repos(org, project)
    if not repos:
        click.echo("    ⚠ No repos found in this project")
        return org, project, []

    click.echo(f"    Found {len(repos)} repo(s):")
    for i, repo in enumerate(repos, 1):
        size_mb = repo.size / (1024 * 1024) if repo.size else 0
        size_str = f" ({size_mb:.0f} MB)" if size_mb > 1 else ""
        click.echo(f"      {i}. {repo.name}{size_str}")

    raw = click.prompt(
        "    Enter repo numbers to clone (comma-separated, or 'all')",
        default="all",
    ).strip()

    if raw.lower() == "all":
        selected = list(repos)
    else:
        selected = []
        for tok in raw.split(","):
            tok = tok.strip()
            if tok.isdigit():
                idx = int(tok) - 1
                if 0 <= idx < len(repos):
                    selected.append(repos[idx])
                else:
                    click.echo(f"    ⚠ Skipping invalid number: {tok}")

    if selected:
        click.echo(f"    → Selected: {', '.join(r.name for r in selected)}")
    else:
        click.echo("    (no repos selected)")

    return org, project, selected


def run_onboarding(vault_root: Path = None):
    """Run the full onboarding wizard."""
    click.echo("")
    click.echo("👋 Welcome to DuckyAI!")
    click.echo("=" * 50)

    # ─── Step 0: Prerequisites ───────────────────────────
    from ..prereqs import check_all, auto_fix, print_report

    report = check_all()
    print_report(report)

    # Auto-fix what we can
    if report.fixable:
        if click.confirm("  Auto-install missing optional tools?", default=True):
            click.echo("  Installing...")
            actions = auto_fix(report)
            for a in actions:
                click.echo(f"    ✓ {a}")
            if actions:
                click.echo("")

    # Block on critical failures
    if report.has_blocking_failures:
        click.echo("  Please install the missing tools above and re-run `duckyai setup`.")
        raise SystemExit(1)

    # ─── Step 1: Vault Location ─────────────────────────
    click.echo("\n📁 Step 1/8 — Vault Location")
    vault_name = click.prompt("  What would you like to name your vault?", default="MyVault")
    default_location = str(vault_root) if vault_root else str(Path.cwd())
    vault_location = Path(click.prompt("  Where should your vault be created?", default=default_location))
    vault_path = (vault_location / vault_name).resolve()
    vault_path.mkdir(parents=True, exist_ok=True)
    click.echo(f"  ✓ Vault: {vault_path}")

    # Services directory — code workspace where repos are cloned
    click.echo("")
    click.echo("  Services is the code workspace directory where your repos live.")
    default_services_parent = str(vault_path.parent)
    services_parent = Path(click.prompt(
        "  Parent directory for vault-services",
        default=default_services_parent,
    ))
    services_dir_name = f"{vault_name}-Services"
    services_path = (services_parent / services_dir_name).resolve()
    click.echo(f"  ✓ Services: {services_path}")

    # ─── Step 2: About You ──────────────────────────────
    click.echo("\n👤 Step 2/8 — About You")
    user_name = click.prompt("  Your full name")
    primary_lang = click.prompt(
        "  Primary language",
        type=click.Choice(["en", "ko", "ja", "zh", "es", "fr", "de"], case_sensitive=False),
        default="en"
    )
    timezone = click.prompt("  Timezone", default=_detect_timezone())

    # ─── Step 3: WorkIQ EULA ─────────────────────────────
    click.echo("\n📋 Step 3/8 — WorkIQ (Teams Data)")
    eula_url = "https://github.com/microsoft/work-iq-mcp"
    click.echo(f"  EULA: {eula_url}")
    if click.confirm("  Accept WorkIQ EULA to enable Teams sync?", default=True):
        click.echo("  ✓ EULA acceptance noted (will be confirmed on first agent run)")
    else:
        click.echo("  ℹ️  Skipped — Teams sync agents will prompt later")

    # ─── Step 6: Vault Structure ────────────────────────
    click.echo("\n📂 Step 4/8 — Vault Structure")
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

    # Copy bundled vault-template files (Obsidian templates, agent instructions, workspace)
    vault_template_dir = Path(__file__).resolve().parent.parent / ".vault-template"
    if vault_template_dir.is_dir():
        for item in vault_template_dir.iterdir():
            dest = vault_path / item.name
            if item.is_dir():
                # Copy template subdirectories (e.g. Templates/)
                for child in item.rglob("*"):
                    if child.is_file():
                        rel = child.relative_to(item)
                        target = dest / rel
                        if not target.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(str(child), str(target))
                            click.echo(f"  ✓ {item.name}/{rel}")
                        else:
                            click.echo(f"  · {item.name}/{rel} (exists)")
            else:
                if not dest.exists():
                    shutil.copy2(str(item), str(dest))
                    click.echo(f"  ✓ {item.name}")
                else:
                    click.echo(f"  · {item.name} (exists)")

    # Create .gitignore
    gitignore_path = vault_path / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(
            "# OS\n.DS_Store\nThumbs.db\n\n"
            "# Obsidian\n.obsidian/workspace*.json\n.obsidian/plugins/\n.trash/\n\n"
            "# Python\n__pycache__/\n*.pyc\n",
            encoding="utf-8",
        )
        click.echo(f"  ✓ .gitignore")
    else:
        click.echo(f"  · .gitignore (exists)")

    # Create .vscode/settings.json
    vscode_dir = vault_path / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    vscode_settings_path = vscode_dir / "settings.json"
    if not vscode_settings_path.exists():
        import json
        vscode_settings = {
            "files.exclude": {
                "**/.git": True,
                "**/.obsidian/plugins": True,
                "**/.obsidian/workspace*.json": True,
            },
            "git.scanRepositories": ["."],
        }
        vscode_settings_path.write_text(
            json.dumps(vscode_settings, indent=2), encoding="utf-8"
        )
        click.echo(f"  ✓ .vscode/settings.json")
    else:
        click.echo(f"  · .vscode/settings.json (exists)")

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
        # Load template from vault source, falling back to packaged playbook template
        _template_candidates = []
        if vault_root:
            _template_candidates.append(Path(vault_root) / "Templates" / "Daily Note.md")
        _template_candidates.append(
            Path(__file__).parent.parent / ".playbook" / "templates" / "Daily Note Template.md"
        )
        _template_source = next((p for p in _template_candidates if p.exists()), None)
        if _template_source:
            import re as _re
            _raw = _template_source.read_text(encoding="utf-8")
            # Replace Obsidian template variables with actual values
            _raw = _re.sub(r"\{\{date:[^}]*YYYY-MM-DD[^}]*\}\}", today_str, _raw)
            _raw = _re.sub(r"\{\{date:[^}]*dddd[^}]*\}\}", day_name, _raw)
            _raw = _raw.replace("{{date}}", today_str).replace("{{dayHeading}}", day_name)
            daily_content = _raw
        else:
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

## Tasks
- [ ] 

## PRs & Code Reviews
- [ ] 

## Notes

## Teams Meeting Highlights

## Teams Chat Highlights

## End of Day
### Carry forward to tomorrow
- [ ] 
"""
        daily_path.write_text(daily_content, encoding="utf-8")
        click.echo(f"  ✓ {today_str}.md (daily note)")
    else:
        click.echo(f"  · {today_str}.md (exists)")

    # ─── Step 7: IDE Selection ─────────────────────────────
    click.echo("\n🖥️  Step 5/8 — IDE")
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
    click.echo("\n🤖 Step 6/8 — Default Model")
    click.echo("  Select the default AI model for orchestrator agents (↑/↓ navigate, Enter select)\n")
    from .vault import _interactive_select
    model_choices = [
        {"name": "claude-sonnet-4.6", "path": "Recommended — fast, high quality"},
        {"name": "claude-haiku-4.5", "path": "Fast, cost-effective"},
        {"name": "claude-sonnet-4.5", "path": "Previous-gen Sonnet"},
        {"name": "claude-sonnet-4", "path": "Stable Sonnet"},
        {"name": "claude-opus-4.6", "path": "Premium — highest quality"},
        {"name": "claude-opus-4.6-fast", "path": "Premium — faster variant"},
        {"name": "claude-opus-4.5", "path": "Previous-gen Opus"},
        {"name": "gpt-5.4", "path": "Latest GPT"},
        {"name": "gpt-5.3-codex", "path": "GPT Codex — code-focused"},
        {"name": "gpt-5.2-codex", "path": "GPT Codex — code-focused"},
        {"name": "gpt-5.2", "path": "GPT general purpose"},
        {"name": "gpt-5.1-codex-max", "path": "GPT Codex Max"},
        {"name": "gpt-5.1-codex", "path": "GPT Codex"},
        {"name": "gpt-5.1", "path": "GPT general purpose"},
        {"name": "gpt-5.1-codex-mini", "path": "GPT Codex Mini — fast"},
        {"name": "gpt-5-mini", "path": "GPT Mini — fastest"},
        {"name": "gpt-4.1", "path": "GPT 4.1 — legacy"}
    ]
    model_idx = _interactive_select(model_choices, default_index=0)
    model = model_choices[model_idx]["name"] if model_idx is not None else "claude-sonnet-4.6"
    click.echo(f"  Selected: {model}")

    # ─── Step 9: Teams Sync Schedule ────────────────────
    click.echo("\n🔄 Step 7/8 — Teams Sync Schedule")
    teams_cron = _prompt_teams_schedule()

    # ─── Step 10: Services (Code Repos) ──────────────────
    click.echo("\n🛠️  Step 8/8 — Services (Code Repos)")
    click.echo("  Services are code projects you work on (each can contain git repos).")
    click.echo("  They live outside your vault in a sibling directory.\n")

    # Check ADO availability once upfront (Decision 4: prereq check at start)
    from ..ado import is_az_devops_available
    ado_available, ado_msg = is_az_devops_available()
    if not ado_available:
        click.echo(f"  ℹ️  ADO integration unavailable: {ado_msg}")
        click.echo("  (You can still add services — repos must be cloned manually)\n")

    service_entries = []  # list of (name, ado_org, ado_project, selected_repos)
    last_ado_url = None   # remember URL across services

    while True:
        svc_name = click.prompt(
            "  Service name (leave empty to finish)",
            default="", show_default=False
        ).strip()
        if not svc_name:
            break

        ado_org = None
        ado_project = None
        selected_repos = []

        # Decision 2: Optional — ask "Link to ADO?" per service
        if ado_available and click.confirm("    Link this service to an ADO project?", default=True):
            ado_org, ado_project, selected_repos = _prompt_ado_for_service(
                svc_name, default_url=last_ado_url,
            )
            if ado_org and ado_project:
                last_ado_url = f"https://dev.azure.com/{ado_org}/{ado_project}"

        service_entries.append((svc_name, ado_org, ado_project, selected_repos))
        click.echo(f"    ✅ Added: {svc_name}")
        if selected_repos:
            click.echo(f"       ({len(selected_repos)} repo(s) will be cloned)")

    if not service_entries:
        click.echo("  (No services added — you can add them later with 'duckyai service add')")
    service_names = [e[0] for e in service_entries]

    # ─── Step 9: Container Isolation ──────────────────────
    use_container = False
    docker_bin = shutil.which('docker')
    if docker_bin:
        click.echo("\n🐳 Docker detected.")
        if click.confirm("  Use container isolation for TP/PR agents?", default=False):
            use_container = True
            click.echo("  Building duckyai-agent image (this may take a few minutes)...")
            dockerfile_path = Path(__file__).parent.parent / '.playbook' / 'Dockerfile.agent'
            build_ctx = dockerfile_path.parent  # no COPY needed, context is minimal
            if not dockerfile_path.exists():
                click.echo("  ⚠ Dockerfile.agent not found in package — skipping build")
                use_container = False
            else:
                try:
                    result = subprocess.run(
                        [docker_bin, 'build', '-f', str(dockerfile_path),
                         '-t', 'duckyai-agent:latest', str(build_ctx)],
                        capture_output=True, encoding='utf-8', errors='replace',
                        timeout=600,
                    )
                    if result.returncode == 0:
                        click.echo("  ✅ duckyai-agent:latest built successfully")
                    else:
                        click.echo(f"  ⚠ Docker build failed: {result.stderr[:200]}")
                        click.echo("  Falling back to local execution (no container)")
                        use_container = False
                except subprocess.TimeoutExpired:
                    click.echo("  ⚠ Docker build timed out — falling back to local execution")
                    use_container = False
                except Exception as e:
                    click.echo(f"  ⚠ Docker build error: {e}")
                    use_container = False

    # ─── Generate Config Files ──────────────────────────
    click.echo("\n⚙️  Generating configuration...")

    # duckyai.yml (single unified config) — lives inside .duckyai/
    duckyai_dir = vault_path / ".duckyai"
    duckyai_dir.mkdir(parents=True, exist_ok=True)
    duckyai_yml_path = duckyai_dir / "duckyai.yml"

    # Migrate legacy root-level duckyai.yml into .duckyai/
    legacy_yml = vault_path / "duckyai.yml"
    if legacy_yml.exists() and not duckyai_yml_path.exists():
        shutil.move(str(legacy_yml), str(duckyai_yml_path))
        click.echo(f"  ✓ Migrated duckyai.yml → .duckyai/duckyai.yml")
    elif legacy_yml.exists() and duckyai_yml_path.exists():
        legacy_yml.unlink()
        click.echo(f"  ✓ Removed stale root duckyai.yml")

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

        # Update use_container on TP and PR agents
        uc_val = "true" if use_container else "false"
        content = re.sub(
            r'(name: Task Planner \(TP\)[\s\S]*?)(use_container:\s*)\S+',
            rf'\1\g<2>{uc_val}',
            content
        )
        content = re.sub(
            r'(name: PR Review \(PR\)[\s\S]*?)(use_container:\s*)\S+',
            rf'\1\g<2>{uc_val}',
            content
        )

        duckyai_yml_path.write_text(content, encoding="utf-8")
        click.echo(f"  ✓ duckyai.yml (updated)")
    else:
        # Generate a fresh duckyai.yml from the single-source-of-truth template
        import re as _re2
        from string import Template as _StrTemplate

        _vault_slug = _re2.sub(r'[^a-z0-9]+', '_', vault_name.lower()).strip('_') or "vault"
        tcs_enabled = "true" if teams_cron else "false"
        tms_enabled = "true" if teams_cron else "false"
        tcs_cron_val = teams_cron or "10 * * * *"
        tms_cron_val = teams_cron or "10 * * * *"

        template_path = Path(__file__).parent.parent / '.playbook' / 'duckyai.yml.template'
        template_content = template_path.read_text(encoding='utf-8')
        duckyai_content = _StrTemplate(template_content).safe_substitute(
            vault_id=_vault_slug,
            vault_name=vault_name,
            user_name=user_name,
            primary_language=primary_lang,
            timezone=timezone,
            model=model,
            tcs_cron=tcs_cron_val,
            tms_cron=tms_cron_val,
            tcs_enabled=tcs_enabled,
            tms_enabled=tms_enabled,
            use_container="true" if use_container else "false",
            services_path=str(services_path).replace("\\", "\\\\"),
        )
        duckyai_yml_path.write_text(duckyai_content, encoding="utf-8")
        click.echo(f"  ✓ duckyai.yml (created)")

    # ─── Summary ────────────────────────────────────────
    click.echo("\n" + "=" * 50)
    click.echo("🎉 DuckyAI is ready!")
    click.echo("")
    click.echo(f"  Vault:      {vault_path} ({vault_name})")
    click.echo(f"  Services:   {services_path}")
    click.echo(f"  User:       {user_name}")
    click.echo(f"  Language:   {primary_lang}")
    click.echo(f"  Model:      {model}")
    if teams_cron:
        click.echo(f"  Teams sync: {teams_cron}")
    else:
        click.echo(f"  Teams sync: disabled")
    click.echo(f"  Container:  {'enabled' if use_container else 'disabled'}")
    click.echo("")

    # Configure the single home vault (~/.duckyai/config.json)
    from ..vault_registry import set_home_vault
    import yaml as _yaml

    # Derive vault_id from duckyai.yml if present, otherwise from vault name
    _vault_id = None
    from duckyai.config import CONFIG_FILENAME
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
        import re as _re
        _vault_id = _re.sub(r'[^a-z0-9]+', '-', vault_name.lower()).strip('-') or "vault"

    set_home_vault(
        vault_id=_vault_id,
        name=vault_name,
        path=vault_path,
        services_path=str(services_path),
    )
    click.echo(f"  ✓ Configured as home vault in ~/.duckyai/config.json")

    # Create services directory and register services
    from ..services import ensure_services_dir, add_service, add_repo_to_service, get_services_path
    from ..ado import clone_repo as ado_clone_repo
    services_dir = ensure_services_dir(vault_path)
    click.echo(f"  ✓ Services directory: {services_dir}")

    # Build clone jobs: (svc_name, service_dir, repo) for each repo to clone
    clone_jobs = []
    for svc_name, ado_org, ado_project, selected_repos in service_entries:
        service_dir = add_service(
            vault_path, svc_name,
            ado_org=ado_org, ado_project=ado_project,
        )
        click.echo(f"    ✓ Service: {svc_name}/")
        for repo in selected_repos:
            dest = service_dir / repo.name
            if dest.exists():
                click.echo(f"      · {repo.name}/ (already exists)")
            else:
                clone_jobs.append((svc_name, dest, repo))

    # Clone repos in parallel
    if clone_jobs:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        total = len(clone_jobs)
        click.echo(f"\n  Cloning {total} repo(s) in parallel...")

        def _do_clone(job):
            svc, dest, repo = job
            dest.parent.mkdir(parents=True, exist_ok=True)
            ok = ado_clone_repo(repo.remote_url, dest)
            return svc, repo, ok

        with ThreadPoolExecutor(max_workers=min(total, 4)) as pool:
            futures = {pool.submit(_do_clone, j): j for j in clone_jobs}
            for future in as_completed(futures):
                svc, repo, ok = future.result()
                if ok:
                    add_repo_to_service(vault_path, svc, repo.name, repo.remote_url)
                    click.echo(f"      ✓ {svc}/{repo.name}")
                else:
                    click.echo(f"      ⚠ Failed: {svc}/{repo.name}")

    # Update home vault config with services_path
    set_home_vault(
        vault_id=_vault_id,
        name=vault_name,
        path=vault_path,
        services_path=str(services_dir),
    )

    # Initialize .github/ structure, skills symlinks, and copilot-instructions
    from .cli import ensure_init
    ensure_init(vault_path)
    click.echo(f"  ✓ .github/ initialized")

    # Open vault in IDE if detected
    if selected_ide:
        ide_name, ide_exe = selected_ide
        click.echo(f"  🖥️  Opening vault in {ide_name}...")
        try:
            subprocess.Popen([ide_exe, str(vault_path)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            click.echo(f"  ⚠️  Could not launch {ide_name} automatically. Open it manually.")

    # Offer to sync Teams data now (if Teams agents are enabled)
    if teams_cron:
        try:
            from .trigger_agent import _prompt_yn
            if _prompt_yn("\n🔄 Sync vault with Teams data now?"):
                from .trigger_agent import _prompt_teams_sync_lookback
                from rich.console import Console
                console = Console()

                override = _prompt_teams_sync_lookback(vault_path, console)

                from ..config import Config
                from ..orchestrator.core import Orchestrator
                orch = Orchestrator(
                    vault_path=vault_path,
                    config=Config(vault_path=vault_path),
                )
                import threading
                threads = []
                for abbr in ("TCS", "TMS"):
                    agent = orch.agent_registry.agents.get(abbr)
                    if not agent:
                        continue
                    click.echo(f"  Triggering {abbr}...")
                    def _run(a=abbr, o=override):
                        orch.trigger_agent_once(a, agent_params_override=o)
                    t = threading.Thread(target=_run, daemon=True)
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join()
                click.echo("  ✓ Teams sync complete")
        except (EOFError, KeyboardInterrupt):
            pass
        except Exception as e:
            click.echo(f"  ⚠️  Teams sync skipped: {e}")

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
    from duckyai.config import CONFIG_FILENAME
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

