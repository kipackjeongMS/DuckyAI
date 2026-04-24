"""
Standalone WebSocket PTY terminal server for DuckyAI.

Spawns a pseudo-terminal, bridges stdin/stdout over WebSocket.
Runs independently of the orchestrator daemon on its own port.

Usage:
    duckyai terminal start       # Start terminal server (background)
    duckyai terminal stop        # Stop terminal server
    duckyai terminal status      # Check if running

Architecture:
    ┌───────────┐  WebSocket  ┌──────────────┐  PTY   ┌──────────┐
    │  xterm.js │────────────▶│  Terminal     │───────▶│  Shell / │
    │  (any UI) │  :52847     │  Server       │       │  CLI     │
    └───────────┘             └──────────────┘       └──────────┘

Protocol:
    Client → Server:
        - Binary/text frames: raw terminal input (keystrokes)
        - JSON: {"type":"resize","cols":80,"rows":24}

    Server → Client:
        - Binary frames: raw terminal output (PTY stdout)
"""

import asyncio
import json
import os
import signal
import sys
import struct
from pathlib import Path
from typing import Optional

from .logger import Logger

log = Logger()

DEFAULT_PORT = 52847
PID_FILENAME = "terminal.pid"
LOG_FILENAME = "terminal-server.log"
DEFAULT_SHELL = None  # auto-detect


def _get_default_shell() -> str:
    """Return platform-appropriate default shell, or configured shell."""
    try:
        from .config import Config
        cfg = Config.get_instance()
        configured = cfg.get("orchestrator.terminal.shell")
        if configured:
            return configured
    except Exception:
        pass
    if sys.platform == "win32":
        return os.environ.get("COMSPEC", "cmd.exe")
    return os.environ.get("SHELL", "/bin/bash")


def _get_configured_port() -> int:
    """Return configured terminal port, or default."""
    try:
        from .config import Config
        cfg = Config.get_instance()
        port = cfg.get("orchestrator.terminal.port")
        if port:
            return int(port)
    except Exception:
        pass
    return DEFAULT_PORT


# ── PID file helpers (mirrors chat_server.py pattern) ──────────────

def _get_pid_file(vault_path: str) -> Path:
    pid_dir = Path(vault_path) / ".duckyai"
    pid_dir.mkdir(parents=True, exist_ok=True)
    return pid_dir / PID_FILENAME


def _write_pid(vault_path: str, pid: int):
    _get_pid_file(vault_path).write_text(str(pid))


def _read_pid(vault_path: str) -> Optional[int]:
    pf = _get_pid_file(vault_path)
    if pf.exists():
        try:
            return int(pf.read_text().strip())
        except (ValueError, OSError):
            pass
    return None


def _clear_pid(vault_path: str):
    pf = _get_pid_file(vault_path)
    if pf.exists():
        pf.unlink(missing_ok=True)


# ── Win32 input mode translator ────────────────────────────────────

# Maps printable ASCII characters → (VirtualKey, ScanCode) using US QWERTY layout.
# Used to convert xterm.js VT input to Win32 input mode format when ConPTY's picker
# activates \x1b[?9001h (Win32 input mode), which causes ConPTY to stop translating
# plain chars into KEY_EVENTs — only Win32-format \x1b[..._] sequences are accepted.
_VK_TABLE: dict[str, tuple[int, int]] = {
    # Lowercase letters: VK=uppercase ordinal, SC=US QWERTY scan code
    'a':(65,30),'b':(66,48),'c':(67,46),'d':(68,32),'e':(69,18),
    'f':(70,33),'g':(71,34),'h':(72,35),'i':(73,23),'j':(74,36),
    'k':(75,37),'l':(76,38),'m':(77,50),'n':(78,49),'o':(79,24),
    'p':(80,25),'q':(81,16),'r':(82,19),'s':(83,31),'t':(84,20),
    'u':(85,22),'v':(86,47),'w':(87,17),'x':(88,45),'y':(89,21),'z':(90,44),
    # Digits
    '0':(48,11),'1':(49,2),'2':(50,3),'3':(51,4),'4':(52,5),
    '5':(53,6),'6':(54,7),'7':(55,8),'8':(56,9),'9':(57,10),
    # Common punctuation (unshifted)
    ' ':(32,57),'\r':(13,28),'\n':(13,28),'\t':(9,15),'\x1b':(27,1),
    '\x7f':(8,14),'\x08':(8,14),  # Backspace
    '-':(189,12),'=':(187,13),'[':(219,26),']':(221,27),'\\':(220,43),
    ';':(186,39),"'":(222,40),',':(188,51),'.':(190,52),'/':(191,53),'`':(192,41),
}

# Maps shifted printable ASCII → (VirtualKey, ScanCode); modifier = SHIFT_PRESSED
_VK_SHIFTED: dict[str, tuple[int, int]] = {
    'A':(65,30),'B':(66,48),'C':(67,46),'D':(68,32),'E':(69,18),
    'F':(70,33),'G':(71,34),'H':(72,35),'I':(73,23),'J':(74,36),
    'K':(75,37),'L':(76,38),'M':(77,50),'N':(78,49),'O':(79,24),
    'P':(80,25),'Q':(81,16),'R':(82,19),'S':(83,31),'T':(84,20),
    'U':(85,22),'V':(86,47),'W':(87,17),'X':(88,45),'Y':(89,21),'Z':(90,44),
    '!':(49,2),'@':(50,3),'#':(51,4),'$':(52,5),'%':(53,6),
    '^':(54,7),'&':(55,8),'*':(56,9),'(':(57,10),')':(48,11),
    '_':(189,12),'+':(187,13),'{':(219,26),'}':(221,27),'|':(220,43),
    ':':(186,39),'"':(222,40),'<':(188,51),'>':(190,52),'?':(191,53),'~':(192,41),
}

_SHIFT_PRESSED = 0x0010
_LEFT_CTRL_PRESSED = 0x0008


def _win32_key(vk: int, sc: int, uc: int, mods: int) -> bytes:
    """Build Win32 input mode key-down + key-up sequence pair."""
    down = f'\x1b[1;1;{vk};{sc};{uc};{mods}_'.encode()
    up   = f'\x1b[0;1;{vk};{sc};{uc};{mods}_'.encode()
    return down + up


def _vt_to_win32_input(data: bytes) -> bytes:
    """Translate xterm.js VT bytes to Win32 input mode sequences for ConPTY.

    In Win32 input mode (\x1b[?9001h) ConPTY expects escape sequences of the
    form \x1b[<down>;<rep>;<vk>;<sc>;<uc>;<mods>_ for each key event.
    Plain printable bytes are silently ignored in this mode.
    """
    s = data.decode("utf-8", errors="replace")

    # VT escape sequences for navigation keys
    _nav = {
        '\x1b[A': (38, 72),   # Up
        '\x1b[B': (40, 80),   # Down
        '\x1b[C': (39, 77),   # Right
        '\x1b[D': (37, 75),   # Left
        '\x1b[H': (36, 71),   # Home
        '\x1b[F': (35, 79),   # End
        '\x1b[5~': (33, 73),  # Page Up
        '\x1b[6~': (34, 81),  # Page Down
    }
    if s in _nav:
        vk, sc = _nav[s]
        return _win32_key(vk, sc, 0, 0)

    result = bytearray()
    for ch in s:
        if ch in _VK_TABLE:
            vk, sc = _VK_TABLE[ch]
            uc = ord(ch) if ord(ch) >= 0x20 else 0
            result += _win32_key(vk, sc, uc, 0)
        elif ch in _VK_SHIFTED:
            vk, sc = _VK_SHIFTED[ch]
            result += _win32_key(vk, sc, ord(ch), _SHIFT_PRESSED)
        elif '\x01' <= ch <= '\x1a':
            # Ctrl+A..Z: map to VK_A..Z with LEFT_CTRL
            vk = ord(ch) + 64
            result += _win32_key(vk, 0, 0, _LEFT_CTRL_PRESSED)
        # Ignore unrecognised sequences (e.g. unknown ESC combos)
    return bytes(result)


# ── PTY abstraction ────────────────────────────────────────────────

class PtyProcess:
    """Cross-platform PTY process wrapper."""

    def __init__(self, command: str, cols: int = 120, rows: int = 30, cwd: str | None = None):
        self.command = command
        self.cols = cols
        self.rows = rows
        self.cwd = cwd
        self._pty = None
        self._process = None

    async def spawn(self):
        """Spawn the PTY process."""
        if sys.platform == "win32":
            await self._spawn_windows()
        else:
            await self._spawn_unix()

    async def _spawn_windows(self):
        """Spawn PTY on Windows using pywinpty ConPTY backend.

        ConPTY (Windows 10 1903+) is the native Windows PTY implementation and
        correctly handles all Console APIs (SetConsoleMode, ReadConsoleInput, etc.)
        that interactive TUI apps like the Copilot CLI picker rely on.
        WinPTY (the legacy PtyProcess backend) emulates these and silently hangs
        on apps that call SetConsoleMode / ReadConsoleInput directly.
        """
        import winpty  # pywinpty

        # Inject terminal environment so TUI libraries can detect capabilities
        env = os.environ.copy()
        # Remove Windows Terminal identity vars — apps check WT_SESSION to decide
        # whether to request Win32 input mode (\x1b[?9001h). In Win32 input mode,
        # ConPTY stops translating plain printable chars to KEY_EVENTs, which
        # causes the Copilot CLI @ / # picker to freeze after typing a letter.
        # Without WT_SESSION the app stays in VT input mode where plain chars work.
        env.pop("WT_SESSION", None)
        env.pop("WT_PROFILE_ID", None)
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        env.setdefault("TERM_PROGRAM", "DuckyAI")

        # Use ConPTY backend — Microsoft's native PTY (Windows 10 1903+).
        # ConPTY correctly handles SetConsoleMode / ReadConsoleInput calls that
        # interactive TUI apps like the Copilot CLI @ / # pickers rely on.
        # WinPTY (the default backend) emulates these APIs and silently hangs.
        self._pty = winpty.PtyProcess.spawn(
            self.command,
            cwd=self.cwd,
            dimensions=(self.rows, self.cols),
            env=env,
            backend=winpty.Backend.ConPTY,
        )

    async def _spawn_unix(self):
        """Spawn PTY on Unix using stdlib pty."""
        import pty as pty_mod
        import fcntl
        import termios

        pid, fd = pty_mod.fork()
        if pid == 0:
            # Child — set working dir then exec the shell
            if self.cwd:
                os.chdir(self.cwd)
            os.execvp(self.command, [self.command])
        else:
            # Parent — store fd and pid
            self._process = pid
            self._pty = fd
            # Set initial size
            winsize = struct.pack("HHHH", self.rows, self.cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def read(self, size: int = 4096) -> bytes:
        """Read from PTY (non-blocking on Windows, blocking on Unix)."""
        if sys.platform == "win32":
            try:
                data = self._pty.read(size)
                return data.encode("utf-8") if isinstance(data, str) else data
            except Exception:
                return b""
        else:
            try:
                return os.read(self._pty, size)
            except OSError:
                return b""

    def write(self, data: bytes):
        """Write to PTY stdin."""
        if sys.platform == "win32":
            text = data.decode("utf-8", errors="replace")
            self._pty.write(text)
        else:
            os.write(self._pty, data)

    def resize(self, cols: int, rows: int):
        """Resize the PTY."""
        self.cols = cols
        self.rows = rows
        if sys.platform == "win32":
            try:
                self._pty.setwinsize(rows, cols)
            except Exception:
                pass
        else:
            import fcntl
            import termios
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            try:
                fcntl.ioctl(self._pty, termios.TIOCSWINSZ, winsize)
            except Exception:
                pass

    def is_alive(self) -> bool:
        """Check if the PTY process is still running."""
        if sys.platform == "win32":
            return self._pty is not None and self._pty.isalive()
        else:
            if self._process is None:
                return False
            try:
                pid, status = os.waitpid(self._process, os.WNOHANG)
                return pid == 0
            except ChildProcessError:
                return False

    def kill(self):
        """Terminate the PTY process."""
        if sys.platform == "win32":
            if self._pty:
                try:
                    self._pty.close()
                except Exception:
                    pass
        else:
            if self._process:
                try:
                    os.kill(self._process, signal.SIGTERM)
                except OSError:
                    pass
            if self._pty:
                try:
                    os.close(self._pty)
                except OSError:
                    pass


# ── WebSocket handler ──────────────────────────────────────────────

async def _handle_terminal(websocket, vault_path: str | None = None):
    """Handle a single terminal WebSocket connection."""
    import websockets

    shell = _get_default_shell()
    pty = PtyProcess(shell, cwd=vault_path)

    try:
        await pty.spawn()
        log.info(f"[terminal] PTY spawned: {shell} (cwd={vault_path})")
    except Exception as e:
        log.error(f"[terminal] Failed to spawn PTY: {e}")
        await websocket.close(1011, f"PTY spawn failed: {e}")
        return

    stop_event = asyncio.Event()
    win32_input_mode = [False]  # mutable flag shared between pty_reader and ws_reader

    async def pty_reader():
        """Read PTY output → send to WebSocket."""
        loop = asyncio.get_event_loop()
        try:
            while not stop_event.is_set():
                data = await loop.run_in_executor(None, pty.read, 4096)
                if not data:
                    if not pty.is_alive():
                        break
                    await asyncio.sleep(0.01)
                    continue

                # Strip sequences that must NOT be forwarded to xterm.js:
                #
                # \x1b[c — ConPTY's DA1 capability query directed at our terminal.
                #   If xterm.js sees it, it auto-responds with \x1b[?1;2c via onData
                #   → WebSocket → pty.write(). But ConPTY does NOT intercept that
                #   response on its input pipe; it forwards it to cmd.exe's stdin as
                #   raw bytes → echoed as ^[[?1;2c → corrupts the cmd.exe prompt.
                #   Stripping prevents the xterm.js auto-response entirely.
                #
                # \x1b[?9001h — Win32 input mode enable (app called SetConsoleMode).
                #   ConPTY has already switched its INPUT translation before emitting
                #   this sequence. In Win32 mode, ConPTY ignores plain bytes; only
                #   \x1b[<kd>;<rep>;<vk>;<sc>;<uc>;<mods>_ sequences are accepted.
                #   Arrow keys still work because ConPTY has a VT fallback for them.
                #   Fix: strip from output (xterm.js stays in normal VT mode) and
                #   flip win32_input_mode so ws_reader translates future keypresses.
                data = data.replace(b"\x1b[c", b"")
                if b"\x1b[?9001h" in data:
                    data = data.replace(b"\x1b[?9001h", b"")
                    # Switch to Win32 input translation — ws_reader will now
                    # convert xterm.js VT keypresses to Win32 \x1b[..._] format.
                    win32_input_mode[0] = True

                if not data:
                    continue

                try:
                    await websocket.send(data)
                except websockets.ConnectionClosed:
                    break
        finally:
            stop_event.set()

    async def ws_reader():
        """Read WebSocket input → write to PTY."""
        loop = asyncio.get_event_loop()
        try:
            async for message in websocket:
                if isinstance(message, str):
                    # Could be a JSON control message
                    try:
                        msg = json.loads(message)
                        if msg.get("type") == "resize":
                            cols = msg.get("cols", 120)
                            rows = msg.get("rows", 30)
                            pty.resize(cols, rows)
                            continue
                    except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
                        pass
                    # Plain text input — translate to Win32 format if ConPTY's picker
                    # activated Win32 input mode; otherwise send raw VT bytes.
                    # Run in executor so pty.write() never blocks the event loop.
                    if win32_input_mode[0]:
                        input_data = _vt_to_win32_input(message.encode("utf-8"))
                    else:
                        input_data = message.encode("utf-8")
                    await loop.run_in_executor(None, pty.write, input_data)
                elif isinstance(message, bytes):
                    if win32_input_mode[0]:
                        input_data = _vt_to_win32_input(message)
                    else:
                        input_data = message
                    await loop.run_in_executor(None, pty.write, input_data)
        except Exception:
            pass
        finally:
            stop_event.set()

    async def auto_command():
        """Send initial command after shell fully initializes."""
        delay = 2.0 if sys.platform == "win32" else 0.5
        await asyncio.sleep(delay)
        if not stop_event.is_set():
            pty.write(b"copilot\r")
            log.info("[terminal] Auto-executed: copilot")

    try:
        await asyncio.gather(pty_reader(), ws_reader(), auto_command())
    finally:
        pty.kill()
        log.info("[terminal] PTY session closed")


# ── Server lifecycle ───────────────────────────────────────────────

async def _run_server(host: str, port: int, vault_path: str | None = None):
    """Run the WebSocket terminal server."""
    import websockets
    from functools import partial

    handler = partial(_handle_terminal, vault_path=vault_path)
    async with websockets.serve(
        handler,
        host,
        port,
        ping_interval=20,
        ping_timeout=60,
        max_size=1024 * 1024,  # 1MB max message
    ) as server:
        log.info(f"[terminal] WebSocket server listening on ws://{host}:{port}")
        await asyncio.Future()  # run forever


def start_terminal_server(vault_path: str, port: int = DEFAULT_PORT, host: str = "127.0.0.1"):
    """Start the terminal server (blocking)."""
    log.reconfigure(vault_path)

    existing_pid = _read_pid(vault_path)
    if existing_pid:
        try:
            os.kill(existing_pid, 0)
            log.info(f"Terminal server already running (PID {existing_pid})")
            return
        except OSError:
            _clear_pid(vault_path)

    _write_pid(vault_path, os.getpid())

    def cleanup(*_):
        _clear_pid(vault_path)
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    log.info(f"[terminal] Starting on {host}:{port} for vault: {vault_path}")

    try:
        asyncio.run(_run_server(host, port, vault_path=vault_path))
    finally:
        _clear_pid(vault_path)


def stop_terminal_server(vault_path: str) -> bool:
    """Stop a running terminal server. Returns True if stopped."""
    pid = _read_pid(vault_path)
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        _clear_pid(vault_path)
        return True
    except OSError:
        _clear_pid(vault_path)
        return False


def terminal_server_status(vault_path: str) -> dict:
    """Check terminal server status."""
    pid = _read_pid(vault_path)
    if not pid:
        return {"running": False}
    try:
        os.kill(pid, 0)
        return {"running": True, "pid": pid, "port": DEFAULT_PORT}
    except OSError:
        _clear_pid(vault_path)
        return {"running": False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DuckyAI Terminal Server")
    parser.add_argument("--vault", required=True, help="Vault path")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port number")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    args = parser.parse_args()
    start_terminal_server(args.vault, port=args.port, host=args.host)
