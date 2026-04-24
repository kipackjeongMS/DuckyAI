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
                # ConPTY sends \x1b[c (DA1 terminal capability query) at startup.
                # cmd.exe blocks waiting for a response before outputting anything.
                # Respond immediately from the server side so the client doesn't
                # have to establish the full WebSocket echo cycle first.
                if b"\x1b[c" in data:
                    pty.write(b"\x1b[?1;2c")
                try:
                    await websocket.send(data)
                except websockets.ConnectionClosed:
                    break
        finally:
            stop_event.set()

    async def ws_reader():
        """Read WebSocket input → write to PTY."""
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
                    except (json.JSONDecodeError, KeyError):
                        pass
                    # Plain text input
                    pty.write(message.encode("utf-8"))
                elif isinstance(message, bytes):
                    pty.write(message)
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
