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

    # Hide cursor
    sys.stdout.write('\033[?25l')
    sys.stdout.flush()

    def _render(first: bool = False):
        if not first:
            # Move cursor back to the first menu line.
            # After rendering, the cursor sits on the last item (no trailing \n),
            # so we only need to go up (count - 1) lines.
            sys.stdout.write(f'\033[{count - 1}F')
        for i, v in enumerate(items):
            if i == cursor:
                line = f'  \033[36;1m❯ {v["name"]}\033[0m \033[2m— {v["path"]}\033[0m'
            else:
                line = f'    {v["name"]} \033[2m— {v["path"]}\033[0m'
            # Move to column 0, clear line, print, move to next line
            sys.stdout.write(f'\r\033[2K{line}')
            if i < count - 1:
                sys.stdout.write('\n')
        # Clear any leftover lines below
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
            click.echo(f"🗂️  Using vault: {vault['name']} ({vault['path']})")
            touch_vault(vault["id"])
            return vault_path

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
    click.echo(f"\n  ✓ Using: {selected['name']}\n")
    return vault_path
