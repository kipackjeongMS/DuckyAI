"""Unit tests for terminal_server.py.

Tests cover:
- PID file helpers (_get_pid_file, _write_pid, _read_pid, _clear_pid)
- PtyProcess construction (cwd param, default cols/rows)
- _handle_terminal initial command injection
- _get_default_shell platform detection
- _get_configured_port fallback
- stop_terminal_server / terminal_server_status logic
- start_terminal_server skip when already running
"""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, call

import pytest

import duckyai.terminal_server as ts_mod
from duckyai.terminal_server import (
    DEFAULT_PORT,
    PID_FILENAME,
    PtyProcess,
    _get_pid_file,
    _write_pid,
    _read_pid,
    _clear_pid,
    _get_default_shell,
    _get_configured_port,
    stop_terminal_server,
    terminal_server_status,
)


class AsyncIteratorMock:
    """Mock async iterator for WebSocket message stream."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


# ── PID file helpers ───────────────────────────────────────────────


class TestPidFileHelpers:
    """Tests for PID file read/write/clear helpers."""

    def test_get_pid_file_creates_duckyai_dir(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        pid_file = _get_pid_file(str(vault))
        assert pid_file == vault / ".duckyai" / PID_FILENAME
        assert (vault / ".duckyai").is_dir()

    def test_write_and_read_pid(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_pid(str(vault), 12345)
        assert _read_pid(str(vault)) == 12345

    def test_read_pid_missing_file(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        assert _read_pid(str(vault)) is None

    def test_read_pid_corrupt_file(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        pid_file = _get_pid_file(str(vault))
        pid_file.write_text("not-a-number")
        assert _read_pid(str(vault)) is None

    def test_clear_pid(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_pid(str(vault), 99)
        assert _read_pid(str(vault)) == 99
        _clear_pid(str(vault))
        assert _read_pid(str(vault)) is None

    def test_clear_pid_when_no_file(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        # Should not raise
        _clear_pid(str(vault))


# ── PtyProcess construction ────────────────────────────────────────


class TestPtyProcess:
    """Tests for PtyProcess initialization and cwd parameter."""

    def test_default_cols_rows(self):
        pty = PtyProcess("bash")
        assert pty.cols == 120
        assert pty.rows == 30
        assert pty.cwd is None

    def test_cwd_parameter_stored(self, tmp_path):
        cwd = str(tmp_path)
        pty = PtyProcess("bash", cwd=cwd)
        assert pty.cwd == cwd

    def test_custom_cols_rows(self):
        pty = PtyProcess("bash", cols=80, rows=24)
        assert pty.cols == 80
        assert pty.rows == 24

    def test_resize_updates_dimensions(self):
        pty = PtyProcess("bash", cols=80, rows=24)
        # No actual PTY, so _pty is None — resize should not raise
        pty.resize(100, 50)
        assert pty.cols == 100
        assert pty.rows == 50

    def test_is_alive_false_when_not_spawned(self):
        pty = PtyProcess("bash")
        assert pty.is_alive() is False

    def test_kill_safe_when_not_spawned(self):
        pty = PtyProcess("bash")
        # Should not raise when nothing spawned
        pty.kill()


# ── Shell / port detection ─────────────────────────────────────────


class TestGetDefaultShell:
    """Tests for _get_default_shell() platform logic."""

    def test_windows_uses_comspec(self):
        """On win32, falls back to COMSPEC env var."""
        with patch("sys.platform", "win32"):
            with patch.dict(os.environ, {"COMSPEC": r"C:\Windows\System32\cmd.exe"}):
                result = _get_default_shell()
        assert "cmd" in result.lower()

    def test_unix_uses_shell_env(self):
        """On Unix, uses SHELL env var."""
        with patch("sys.platform", "linux"):
            with patch.dict(os.environ, {"SHELL": "/bin/zsh"}):
                result = _get_default_shell()
        assert result == "/bin/zsh"

    def test_unix_fallback_to_bash(self):
        """On Unix without SHELL set, defaults to /bin/bash."""
        with patch("sys.platform", "linux"):
            with patch.dict(os.environ, {}, clear=True):
                result = _get_default_shell()
        assert result == "/bin/bash"


class TestGetConfiguredPort:
    """Tests for _get_configured_port() fallback."""

    def test_default_port_value(self):
        assert DEFAULT_PORT == 52847

    def test_returns_default_port_on_config_failure(self):
        """Config.get_instance() doesn't exist, so fallback is always used."""
        assert _get_configured_port() == DEFAULT_PORT

    def test_default_port_constant(self):
        assert DEFAULT_PORT == 52847


# ── stop / status ──────────────────────────────────────────────────


class TestStopTerminalServer:
    """Tests for stop_terminal_server()."""

    def test_stop_returns_false_when_no_pid(self, tmp_path):
        vault = str(tmp_path / "vault")
        os.makedirs(vault, exist_ok=True)
        assert stop_terminal_server(vault) is False

    def test_stop_kills_process_and_clears_pid(self, tmp_path):
        vault = str(tmp_path / "vault")
        os.makedirs(vault, exist_ok=True)
        _write_pid(vault, 99999)
        with patch("os.kill") as mock_kill:
            result = stop_terminal_server(vault)
        assert result is True
        mock_kill.assert_called_once_with(99999, signal.SIGTERM)
        assert _read_pid(vault) is None

    def test_stop_clears_pid_on_os_error(self, tmp_path):
        vault = str(tmp_path / "vault")
        os.makedirs(vault, exist_ok=True)
        _write_pid(vault, 99999)
        with patch("os.kill", side_effect=OSError("no such process")):
            result = stop_terminal_server(vault)
        assert result is False
        assert _read_pid(vault) is None


class TestTerminalServerStatus:
    """Tests for terminal_server_status()."""

    def test_status_not_running_when_no_pid(self, tmp_path):
        vault = str(tmp_path / "vault")
        os.makedirs(vault, exist_ok=True)
        status = terminal_server_status(vault)
        assert status == {"running": False}

    def test_status_running_when_process_alive(self, tmp_path):
        vault = str(tmp_path / "vault")
        os.makedirs(vault, exist_ok=True)
        _write_pid(vault, 12345)
        with patch("os.kill"):  # no exception = process alive
            status = terminal_server_status(vault)
        assert status["running"] is True
        assert status["pid"] == 12345
        assert status["port"] == DEFAULT_PORT

    def test_status_clears_stale_pid(self, tmp_path):
        vault = str(tmp_path / "vault")
        os.makedirs(vault, exist_ok=True)
        _write_pid(vault, 99999)
        with patch("os.kill", side_effect=OSError("gone")):
            status = terminal_server_status(vault)
        assert status == {"running": False}
        assert _read_pid(vault) is None


# ── _handle_terminal (initial command injection) ───────────────────


class TestHandleTerminal:
    """Tests for WebSocket handler: cwd pass-through + auto-execute."""

    def test_pty_spawned_with_vault_cwd(self):
        """PTY should be spawned with cwd=vault_path."""
        from duckyai.terminal_server import _handle_terminal

        mock_ws = AsyncMock()
        # Make async-for immediately stop (empty iterator)
        mock_ws.__aiter__ = MagicMock(return_value=AsyncIteratorMock([]))
        mock_ws.send = AsyncMock()

        mock_pty = MagicMock()
        mock_pty.spawn = AsyncMock()
        mock_pty.is_alive.return_value = False
        mock_pty.read.return_value = b""
        mock_pty.write = MagicMock()
        mock_pty.kill = MagicMock()

        async def run():
            with patch("duckyai.terminal_server.PtyProcess", return_value=mock_pty) as mock_cls:
                with patch("duckyai.terminal_server._get_default_shell", return_value="bash"):
                    try:
                        await asyncio.wait_for(
                            _handle_terminal(mock_ws, vault_path="/test/vault"),
                            timeout=0.5,
                        )
                    except asyncio.TimeoutError:
                        pass
                mock_cls.assert_called_once_with("bash", cwd="/test/vault")

        asyncio.run(run())

    def test_initial_command_sent_after_spawn(self):
        """After PTY spawn, 'copilot\\n' should be written to PTY via auto_command task."""
        from duckyai.terminal_server import _handle_terminal

        # WebSocket that stays open long enough for auto_command to fire
        async def slow_ws_iter():
            await asyncio.sleep(5.0)  # Keep WS alive; test timeout will cancel
            return
            yield  # make it an async generator

        mock_ws = AsyncMock()
        mock_ws.__aiter__ = MagicMock(return_value=slow_ws_iter())
        mock_ws.send = AsyncMock()

        mock_pty = MagicMock()
        mock_pty.spawn = AsyncMock()
        mock_pty.is_alive.return_value = True
        mock_pty.read.return_value = b""
        mock_pty.write = MagicMock()
        mock_pty.kill = MagicMock()

        async def run():
            with patch("duckyai.terminal_server.PtyProcess", return_value=mock_pty):
                with patch("duckyai.terminal_server._get_default_shell", return_value="bash"):
                    try:
                        await asyncio.wait_for(
                            _handle_terminal(mock_ws, vault_path="/vault"),
                            timeout=3.0,
                        )
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
            mock_pty.write.assert_any_call(b"copilot\n")

        asyncio.run(run())


# ── start_terminal_server (skip-if-running) ────────────────────────


class TestStartTerminalServer:
    """Tests for start_terminal_server early-exit logic."""

    def test_skips_when_already_running(self, tmp_path):
        """Should return early if PID file points to a live process."""
        vault = str(tmp_path / "vault")
        os.makedirs(vault, exist_ok=True)
        _write_pid(vault, 12345)

        with patch("os.kill"):  # process alive
            with patch("duckyai.terminal_server.log"):
                from duckyai.terminal_server import start_terminal_server
                # Should return without calling asyncio.run
                with patch("asyncio.run") as mock_run:
                    start_terminal_server(vault)
                mock_run.assert_not_called()

    def test_clears_stale_pid_and_starts(self, tmp_path):
        """Should clear stale PID and proceed to start."""
        vault = str(tmp_path / "vault")
        os.makedirs(vault, exist_ok=True)
        _write_pid(vault, 99999)

        pid_written = []

        original_write_pid = ts_mod._write_pid

        def capture_write_pid(vp, pid):
            pid_written.append(pid)
            original_write_pid(vp, pid)

        with patch("os.kill", side_effect=OSError("gone")):
            with patch("duckyai.terminal_server.log"):
                with patch("duckyai.terminal_server._write_pid", side_effect=capture_write_pid):
                    from duckyai.terminal_server import start_terminal_server
                    with patch("asyncio.run") as mock_run:
                        with patch("signal.signal"):
                            start_terminal_server(vault)
                    mock_run.assert_called_once()
        # Verify _write_pid was called with current PID
        assert os.getpid() in pid_written
