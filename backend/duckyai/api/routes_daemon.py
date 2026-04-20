"""Daemon process lifecycle routes — health, shutdown."""

import os
import signal
import threading
from pathlib import Path

from flask import Blueprint, current_app, jsonify

bp = Blueprint("daemon", __name__)


@bp.route("/health")
def health():
    """GET /api/daemon/health — check if the daemon process is alive."""
    return jsonify({"status": "ok", "pid": os.getpid()})


@bp.route("/shutdown", methods=["POST"])
def shutdown():
    """POST /api/daemon/shutdown — cleanly shut down the daemon process.

    Stops the orchestrator event loop, cleans up discovery/PID files, and exits.
    This kills the entire daemon process — use orchestrator /stop to pause only.
    """
    orch = current_app.config["orchestrator"]
    vault_path = current_app.config["vault_path"]

    try:
        orch.stop()
    except Exception:
        pass

    # Clean up discovery and PID files
    from .server import cleanup_discovery_file

    vault = Path(vault_path)
    cleanup_discovery_file(vault)
    pid_file = vault / ".duckyai" / ".orchestrator.pid"
    pid_file.unlink(missing_ok=True)

    # Send response before exiting
    response = jsonify({"status": "shutdown", "pid": os.getpid()})

    # Schedule process exit after response is sent
    def _exit():
        import time

        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_exit, daemon=True).start()

    return response


@bp.route("/start", methods=["POST"])
def start():
    """POST /api/daemon/start — resume the orchestrator event loop."""
    orch = current_app.config["orchestrator"]
    try:
        orch.start()
        return jsonify({"status": "started"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/stop", methods=["POST"])
def stop():
    """POST /api/daemon/stop — pause the orchestrator event loop.

    The daemon process stays alive; only the event loop pauses.
    Use /shutdown to kill the daemon entirely.
    """
    orch = current_app.config["orchestrator"]
    try:
        orch.stop()
        return jsonify({"status": "stopped"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
