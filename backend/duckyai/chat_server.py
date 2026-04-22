"""
Lightweight chat runtime server for DuckyAI.

A standalone HTTP service that wraps the Copilot SDK to provide
a persistent conversational interface. Runs independently of the
orchestrator daemon.

Usage:
    duckyai chat start          # Start chat server (background)
    duckyai chat stop           # Stop chat server
    duckyai chat status         # Check if running

Architecture:
    ┌───────────┐  HTTP   ┌──────────────┐  SDK   ┌──────────┐
    │ Obsidian  │───────▶│  Chat Server  │──────▶│ Copilot  │
    │ Plugin    │  :52846 │  (this file)  │       │ CLI      │
    └───────────┘         └──────────────┘       └──────────┘
                                │
                           MCP Tools ──▶ Vault daemon (:52845)
"""

import asyncio
import json
import os
import signal
import sys
import threading
import time
import shutil
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

from .logger import Logger

log = Logger()

DEFAULT_PORT = 52846
PID_FILENAME = "chat.pid"
LOG_FILENAME = "chat-server.log"
SEND_TIMEOUT = 180  # 3 minutes

SYSTEM_MESSAGE = """You are DuckyAI, a personal knowledge management assistant.
You help the user manage their Obsidian vault: daily notes, tasks, meetings, PR reviews, and more.
When the user asks about their work, tasks, schedule, or vault content, use the available vault tools.
Be concise and helpful. Respond in a friendly, professional tone."""


class ChatRuntime:
    """Manages a persistent Copilot SDK session for interactive chat."""

    def __init__(self, vault_path: str, daemon_url: str = "http://127.0.0.1:52845"):
        self.vault_path = vault_path
        self.daemon_url = daemon_url
        self._client = None
        self._session = None
        self._started = False
        self._send_lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def _resolve_cli_path(self) -> str:
        """Find the Copilot CLI binary."""
        try:
            from copilot import __file__ as copilot_init
            binary = "copilot.exe" if os.name == "nt" else "copilot"
            bundled = Path(copilot_init).resolve().parent / "bin" / binary
            if bundled.exists():
                return str(bundled)
        except ImportError:
            pass
        return shutil.which("copilot") or "copilot"

    def _build_mcp_config(self) -> dict:
        """Build MCP server config pointing to the vault daemon's MCP tools."""
        return {
            "duckyai-vault": {
                "command": shutil.which("duckyai-vault-mcp") or "duckyai-vault-mcp",
                "args": [],
                "env": {"DUCKYAI_VAULT_ROOT": self.vault_path},
            }
        }

    async def start(self):
        """Start the Copilot SDK client."""
        if self._started:
            return

        from copilot import CopilotClient

        cli_path = self._resolve_cli_path()

        try:
            from copilot import SubprocessConfig
            config = SubprocessConfig(
                cli_path=cli_path,
                cwd=self.vault_path,
                log_level="warning",
                use_logged_in_user=True,
            )
            github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            if github_token:
                config.github_token = github_token
            self._client = CopilotClient(config, auto_start=True)
        except ImportError:
            self._client = CopilotClient({
                "auto_start": True,
                "log_level": "warning",
                "cli_path": cli_path,
                "cwd": self.vault_path,
            })

        await self._client.start()
        self._started = True

    async def stop(self):
        """Stop the client and session."""
        if self._session:
            try:
                await self._session.disconnect()
            except Exception:
                pass
            self._session = None

        if self._client:
            try:
                await self._client.stop()
            except Exception:
                pass
            self._client = None
            self._started = False

    async def _ensure_session(self):
        """Create a session if one doesn't exist."""
        if self._session:
            return self._session

        if not self._started:
            await self.start()

        from copilot import PermissionHandler

        mcp_servers = self._build_mcp_config()
        session_opts = {
            "model": "claude-sonnet-4",
            "on_permission_request": PermissionHandler.approve_all,
            "mcp_servers": mcp_servers,
        }

        try:
            self._session = await self._client.create_session(**session_opts)
        except TypeError:
            self._session = await self._client.create_session(session_opts)

        return self._session

    async def _discard_session(self):
        """Drop current session so next send creates a fresh one."""
        if not self._session:
            return
        try:
            await self._session.disconnect()
        except Exception:
            pass
        self._session = None

    async def send_message(self, text: str) -> str:
        """Send a message and return the assistant's response."""
        async with self._send_lock:
            return await self._do_send(text)

    async def _do_send(self, text: str, is_retry: bool = False) -> str:
        try:
            session = await self._ensure_session()
        except Exception as e:
            if not is_retry:
                await self.stop()
                return await self._do_send(text, is_retry=True)
            raise

        try:
            # Use the same send pattern as copilot_sdk_runner
            done = asyncio.Event()
            content_parts = []
            errors = []

            def on_event(event):
                event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)
                if event_type == "assistant.message":
                    if hasattr(event.data, 'content') and event.data.content:
                        content_parts.append(event.data.content)
                elif event_type in {"error", "session.error"}:
                    errors.append(str(event.data) if hasattr(event, 'data') else str(event))
                elif event_type == "session.idle":
                    done.set()

            session.on(on_event)

            try:
                await session.send(text)
            except TypeError:
                await session.send({"prompt": text})

            await asyncio.wait_for(done.wait(), timeout=SEND_TIMEOUT)

            if errors:
                return f"Error: {'; '.join(errors)}"
            return "\n".join(content_parts) or "No response."

        except asyncio.TimeoutError:
            await self._discard_session()
            return "Response timed out."
        except Exception as e:
            await self._discard_session()
            if not is_retry:
                return await self._do_send(text, is_retry=True)
            raise

    async def reset_session(self):
        """Reset the conversation (new session)."""
        await self._discard_session()


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


def create_chat_app(vault_path: str) -> Flask:
    """Create the Flask app for the chat server."""
    app = Flask(__name__)
    CORS(app)

    runtime = ChatRuntime(vault_path)
    loop = asyncio.new_event_loop()

    # Run the async event loop in a background thread
    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    loop_thread = threading.Thread(target=run_loop, daemon=True)
    loop_thread.start()

    def run_async(coro):
        """Schedule a coroutine on the background loop and wait for result."""
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=SEND_TIMEOUT + 10)

    # Start the SDK client eagerly
    try:
        run_async(runtime.start())
    except Exception as e:
        log.warning(f"SDK client start failed (will retry on first message): {e}")

    @app.route("/api/chat/send", methods=["POST"])
    def chat_send():
        data = request.get_json(silent=True) or {}
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "Empty message"}), 400

        log.info(f"Chat send: {message[:80]}...")
        try:
            response = run_async(runtime.send_message(message))
            log.info(f"Chat response: {response[:80]}...")
            return jsonify({"response": response})
        except Exception as e:
            log.error(f"Chat send error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/chat/reset", methods=["POST"])
    def chat_reset():
        try:
            run_async(runtime.reset_session())
            return jsonify({"status": "ok", "message": "Session reset"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/chat/health")
    def chat_health():
        return jsonify({
            "status": "ok",
            "pid": os.getpid(),
            "started": runtime._started,
            "has_session": runtime._session is not None,
        })

    return app


def start_chat_server(vault_path: str, port: int = DEFAULT_PORT, host: str = "127.0.0.1"):
    """Start the chat server (blocking)."""
    log.reconfigure(vault_path)

    # Check if already running
    existing_pid = _read_pid(vault_path)
    if existing_pid:
        try:
            os.kill(existing_pid, 0)
            log.info(f"Chat server already running (PID {existing_pid})")
            return
        except OSError:
            _clear_pid(vault_path)

    _write_pid(vault_path, os.getpid())

    def cleanup(*_):
        _clear_pid(vault_path)
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    app = create_chat_app(vault_path)
    log.info(f"[chat-server] Starting on {host}:{port} for vault: {vault_path}")

    try:
        from waitress import serve
        serve(app, host=host, port=port, _quiet=True)
    except ImportError:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    finally:
        _clear_pid(vault_path)


def stop_chat_server(vault_path: str) -> bool:
    """Stop a running chat server. Returns True if stopped."""
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


def chat_server_status(vault_path: str) -> dict:
    """Check chat server status."""
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
    parser = argparse.ArgumentParser(description="DuckyAI Chat Server")
    parser.add_argument("--vault", required=True, help="Vault path")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port number")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    args = parser.parse_args()
    start_chat_server(args.vault, port=args.port, host=args.host)
