"""Shared vault utilities for DuckyAI CLI."""

import os
import sys
from pathlib import Path
from typing import List, Optional

import click

VAULT_MARKERS = ['duckyai.yml', 'Home.md']


def _read_key() -> str:
    """Read a single keypress and return a normalized name.

    Returns one of: 'up', 'down', 'enter', 'q', or the character pressed.
    Works on Windows (msvcrt) and Unix (tty/termios).
    """
    if os.name == 'nt':
        import msvcrt
        ch = msvcrt.getwch()
        if ch == '\x03':
            raise KeyboardInterrupt
        if ch in ('\r', '\n'):
            return 'enter'
        if ch in ('\x00', '\xe0'):
            # Arrow keys send a two-byte sequence
            ch2 = msvcrt.getwch()
            if ch2 == 'H':
                return 'up'
            if ch2 == 'P':
                return 'down'
            return ''
        return ch
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\r' or ch == '\n':
                return 'enter'
            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A':
                        return 'up'
                    if ch3 == 'B':
                        return 'down'
                return ''
            if ch == '\x03':
                raise KeyboardInterrupt
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _interactive_select(items: List[dict], default_index: int = 0) -> Optional[int]:
    """Show an interactive arrow-key selector. Returns chosen index or None."""
    if not items:
        return None

    cursor = default_index
    count = len(items)

    # Get terminal width to prevent line wrapping (which breaks cursor math)
    try:
        term_width = os.get_terminal_size().columns
    except OSError:
        term_width = 80

    def _truncate(text: str) -> str:
        """Truncate visible text to terminal width, ignoring ANSI escapes."""
        import re
        visible_len = len(re.sub(r'\033\[[0-9;]*m', '', text))
        if visible_len <= term_width:
            return text
        # Over budget — trim from the raw string end, preserving reset code
        overshoot = visible_len - term_width + 1  # +1 for safety
        stripped = text.rstrip('\033[0m')
        return stripped[:-overshoot] + '\033[0m'

    # Hide cursor
    sys.stdout.write('\033[?25l')
    sys.stdout.flush()

    def _render(first: bool = False):
        if not first:
            if count > 1:
                sys.stdout.write(f'\033[{count - 1}A\r')
            else:
                sys.stdout.write('\r')
        for i, v in enumerate(items):
            if i == cursor:
                line = f'  \033[36;1m❯ {v["name"]}\033[0m \033[2m— {v["path"]}\033[0m'
            else:
                line = f'    {v["name"]} \033[2m— {v["path"]}\033[0m'
            sys.stdout.write(f'\033[2K{_truncate(line)}')
            if i < count - 1:
                sys.stdout.write('\n\r')
        sys.stdout.write('\033[J')
        sys.stdout.flush()

    try:
        _render(first=True)
        while True:
            key = _read_key()
            if key == 'up':
                cursor = (cursor - 1) % count
                _render()
            elif key == 'down':
                cursor = (cursor + 1) % count
                _render()
            elif key == 'enter':
                # Move past the rendered list before returning
                sys.stdout.write('\n')
                sys.stdout.flush()
                return cursor
            elif key == 'q':
                sys.stdout.write('\n')
                sys.stdout.flush()
                return None
    except (KeyboardInterrupt, EOFError):
        sys.stdout.write('\n')
        sys.stdout.flush()
        raise SystemExit(130)
    finally:
        # Show cursor again
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()


def find_vault_root(start: Path = None) -> Path:
    """Walk up from start to find the DuckyAI vault root."""
    current = start or Path.cwd()
    while current != current.parent:
        if any((current / m).exists() for m in VAULT_MARKERS):
            return current
        current = current.parent
    return start or Path.cwd()


def is_inside_vault(path: Path = None) -> bool:
    """Check whether the given path (or CWD) is inside a recognized vault."""
    current = path or Path.cwd()
    while current != current.parent:
        if any((current / m).exists() for m in VAULT_MARKERS):
            return True
        current = current.parent
    return False


def resolve_vault(working_dir: Optional[str] = None) -> Path:
    """Resolve which vault to use.

    Priority:
      1. If working_dir is given, use it directly (explicit --working-dir flag).
      2. If CWD is inside a vault, use that vault (backward-compatible).
      3. If ~/.duckyai/vaults.json has registered vaults, prompt user to pick one.
      4. Otherwise, return CWD (will trigger onboarding downstream).
    """
    from ..vault_registry import list_vaults, find_vault_by_path, touch_vault

    # 1. Explicit working dir
    if working_dir:
        return find_vault_root(Path(working_dir))

    # 2. CWD is inside a vault
    if is_inside_vault():
        vault_root = find_vault_root()
        # Touch registry if this vault is registered
        entry = find_vault_by_path(vault_root)
        if entry:
            touch_vault(entry["id"])
        return vault_root

    # 3. Check global registry
    vaults = list_vaults()
    if not vaults:
        # No vaults registered — return CWD (onboarding will handle it)
        return Path.cwd()

    if len(vaults) == 1:
        vault = vaults[0]
        vault_path = Path(vault["path"])
        if vault_path.exists():
            touch_vault(vault["id"])
            # Show action menu for the single vault
            action = _vault_action_menu(vault["name"])
            if action is None:
                raise SystemExit(0)
            if action == "open":
                click.echo(f"\n  ✓ Opening: {vault['name']}\n")
                return vault_path
            elif action == "delete":
                _delete_vault(vault)
                raise SystemExit(0)
            elif action == "orchestrator":
                _orchestrator_menu(vault_path, vault["name"])
                raise SystemExit(0)

    # Multiple vaults — interactive arrow-key selection
    click.echo("\n🗂️  Select a vault: (↑↓ to move, Enter to select)\n")
    choice = _interactive_select(vaults, default_index=0)

    if choice is None:
        click.echo("\nAborted.")
        raise SystemExit(1)

    selected = vaults[choice]
    vault_path = Path(selected["path"])
    if not vault_path.exists():
        click.echo(f"⚠️  Vault path does not exist: {vault_path}", err=True)
        return Path.cwd()

    touch_vault(selected["id"])

    # Show action menu for selected vault
    action = _vault_action_menu(selected["name"])
    if action is None:
        raise SystemExit(0)

    if action == "open":
        click.echo(f"\n  ✓ Opening: {selected['name']}\n")
        return vault_path
    elif action == "delete":
        _delete_vault(selected)
        raise SystemExit(0)
    elif action == "orchestrator":
        _orchestrator_menu(vault_path, selected["name"])
        raise SystemExit(0)

    return vault_path


def _vault_action_menu(vault_name: str) -> Optional[str]:
    """Show action menu after vault selection. Returns 'open', 'delete', 'orchestrator', or None."""
    click.echo(f"\n  📂 {vault_name}\n")
    items = [
        {"name": "Open vault", "path": "IDE + orchestrator + Copilot"},
        {"name": "Delete vault", "path": "Remove vault and all data"},
        {"name": "Orchestrator", "path": "Status / Stop"},
    ]
    choice = _interactive_select(items, default_index=0)
    if choice is None:
        return None
    return ["open", "delete", "orchestrator"][choice]


def _delete_vault(vault_entry: dict) -> None:
    """Delete a vault: folder, services folder, and registry entry.
    
    Runtime data (.duckyai/) lives inside the vault folder, so it's deleted with it.
    """
    import shutil
    from ..vault_registry import unregister_vault
    from ..config import Config

    vault_id = vault_entry["id"]
    vault_name = vault_entry["name"]
    vault_path = Path(vault_entry["path"])

    click.echo(f"\n⚠️  This will permanently delete vault '{vault_name}':")
    if vault_path.exists():
        click.echo(f"  • Vault folder: {vault_path}")
    # Resolve services path
    services_path = None
    if vault_path.exists():
        try:
            cfg = Config(vault_path=vault_path)
            services_path = Path(cfg.get_services_path())
            if services_path.exists():
                click.echo(f"  • Services folder: {services_path}")
        except Exception:
            pass
    click.echo(f"  • Registry entry in vaults.json")

    try:
        confirm = input(f"\nType '{vault_id}' to confirm deletion: ").strip()
    except (EOFError, KeyboardInterrupt):
        click.echo("\n  Cancelled.")
        return

    if confirm != vault_id:
        click.echo("  Cancelled — input did not match vault ID.")
        return

    # Stop orchestrator if running
    from .orch_cmd import _read_pid, _stop_single_vault
    pid, alive = _read_pid(vault_path)
    if alive:
        click.echo("  Stopping orchestrator...")
        _stop_single_vault(vault_path, vault_name)

    # Delete vault folder (includes .duckyai/ runtime data)
    if vault_path.exists():
        shutil.rmtree(vault_path, ignore_errors=True)
        click.echo(f"  ✓ Deleted vault folder")

    # Delete services folder
    if services_path and services_path.exists():
        shutil.rmtree(services_path, ignore_errors=True)
        click.echo(f"  ✓ Deleted services folder")

    # Remove from registry
    unregister_vault(vault_id)
    click.echo(f"  ✓ Removed from vault registry")

    click.echo(f"\n🗑️  Vault '{vault_name}' has been deleted.")


def _orchestrator_menu(vault_path: Path, vault_name: str) -> None:
    """Show orchestrator status, then offer Start or Stop depending on state."""
    from .orch_cmd import _read_pid, _stop_single_vault
    from .cli import ensure_orchestrator_running

    pid, alive = _read_pid(vault_path)

    if alive:
        click.echo(f"\n  ⚙️  Orchestrator — {vault_name}")
        click.echo(f"  ✅ Running (PID: {pid})\n")
        items = [
            {"name": "Stop", "path": "Stop the orchestrator daemon"},
        ]
        choice = _interactive_select(items, default_index=0)
        if choice is None:
            return
        result = _stop_single_vault(vault_path, vault_name)
        if result.get("status") == "stopped":
            click.echo(f"\n  ✅ Orchestrator stopped (was PID: {result.get('pid', '?')})")
        else:
            click.echo(f"\n  ⚠️  {result.get('error', 'Unknown error')}")
    else:
        click.echo(f"\n  ⚙️  Orchestrator — {vault_name}")
        click.echo(f"  ⏹️  Not running\n")
        items = [
            {"name": "Start", "path": "Start the orchestrator daemon"},
        ]
        choice = _interactive_select(items, default_index=0)
        if choice is None:
            return
        freshly_started = ensure_orchestrator_running(vault_path)
        if freshly_started:
            pid, _ = _read_pid(vault_path)
            click.echo(f"\n  ✅ Orchestrator started (PID: {pid})")
            _prompt_teams_sync(vault_path)
        else:
            click.echo(f"\n  ⚠️  Failed to start orchestrator")


def _prompt_teams_sync(vault_path: Path) -> None:
    """Prompt user to sync Teams chats & meetings after orchestrator start."""
    from .trigger_agent import _prompt_yn, _prompt_teams_sync_lookback
    from .cli import _enqueue_tcs_task, _enqueue_tms_task

    try:
        if _prompt_yn("\n🔄 Sync Teams chats & meetings now?"):
            from rich.console import Console
            console = Console()

            override = _prompt_teams_sync_lookback(vault_path, console)
            lbh = override.get('lookback_hours') if override else None
            _enqueue_tcs_task(vault_path, lookback_hours=lbh)
            _enqueue_tms_task(vault_path, lookback_hours=lbh)
            click.echo("✓ TCS & TMS queued — orchestrator will pick them up shortly")
    except (EOFError, KeyboardInterrupt):
        pass
