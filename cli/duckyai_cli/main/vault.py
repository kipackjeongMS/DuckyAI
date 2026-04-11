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
      2. If CWD is inside a vault, use that vault.
      3. If a home vault is configured, use that vault.
      4. Otherwise, return CWD (setup/init will handle first-time use).
    """
    from ..vault_registry import get_home_vault, touch_vault

    # 1. Explicit working dir
    if working_dir:
        return find_vault_root(Path(working_dir))

    # 2. CWD is inside a vault
    if is_inside_vault():
        vault_root = find_vault_root()
        home_vault = get_home_vault()
        if home_vault and str(Path(home_vault["path"]).resolve()) == str(vault_root.resolve()):
            touch_vault(home_vault["id"])
        return vault_root

    # 3. Use the configured home vault when available
    home_vault = get_home_vault()
    if home_vault:
        vault_path = Path(home_vault["path"])
        if vault_path.exists():
            touch_vault(home_vault["id"])
            return vault_path

    # 4. No configured vault — return CWD for setup/init flows
    return Path.cwd()
