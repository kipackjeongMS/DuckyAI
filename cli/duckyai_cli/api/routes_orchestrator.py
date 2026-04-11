"""Orchestrator API routes — status, trigger, agents."""

import threading
from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("orchestrator", __name__)


def _trigger_agent_in_background(orch, agent_abbr, input_file=None, agent_params=None):
    """Trigger an agent on a background thread and return a standard response."""
    if agent_abbr not in orch.agent_registry.agents:
        return jsonify({"error": f"Agent '{agent_abbr}' not found"}), 404

    def _run():
        orch.trigger_agent_once(
            agent_abbr,
            input_file=input_file,
            agent_params_override=agent_params,
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({
        "status": "triggered",
        "agent": agent_abbr,
    })


@bp.route("/status")
def status():
    """GET /api/orchestrator/status — current orchestrator status."""
    orch = current_app.config["orchestrator"]
    return jsonify(orch.get_status())


@bp.route("/agents")
def agents():
    """GET /api/orchestrator/agents — list loaded agents."""
    orch = current_app.config["orchestrator"]
    agent_list = []
    for agent in orch.agent_registry.agents.values():
        agent_list.append({
            "abbreviation": agent.abbreviation,
            "name": agent.name,
            "category": agent.category,
            "cron": agent.cron,
            "running": orch.execution_manager.get_agent_running_count(agent.abbreviation),
        })
    return jsonify(agent_list)


@bp.route("/trigger", methods=["POST"])
def trigger():
    """POST /api/orchestrator/trigger — trigger an agent.

    Body: { "agent": "TCS", "input_file": "...", "agent_params": {...} }
    """
    orch = current_app.config["orchestrator"]
    data = request.get_json(silent=True) or {}

    agent_abbr = data.get("agent")
    if not agent_abbr:
        return jsonify({"error": "Missing required field: agent"}), 400

    input_file = data.get("input_file")
    agent_params = data.get("agent_params")

    return _trigger_agent_in_background(
        orch,
        agent_abbr,
        input_file=input_file,
        agent_params=agent_params,
    )


@bp.route("/trigger/tm", methods=["POST"])
def trigger_tm():
    """POST /api/orchestrator/trigger/tm — trigger Task Manager explicitly."""
    orch = current_app.config["orchestrator"]
    data = request.get_json(silent=True) or {}

    return _trigger_agent_in_background(
        orch,
        "TM",
        input_file=data.get("input_file"),
        agent_params=data.get("agent_params"),
    )


@bp.route("/start", methods=["POST"])
def start():
    """POST /api/orchestrator/start — resume the orchestrator event loop.

    Note: This resumes an already-running daemon's event loop.
    To spawn a new daemon process, clients should use subprocess.
    """
    orch = current_app.config["orchestrator"]
    try:
        orch.start()
        return jsonify({"status": "started", "running": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/stop", methods=["POST"])
def stop():
    """POST /api/orchestrator/stop — stop the orchestrator event loop."""
    orch = current_app.config["orchestrator"]
    try:
        orch.stop()
        return jsonify({"status": "stopped", "running": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/shutdown", methods=["POST"])
def shutdown():
    """POST /api/orchestrator/shutdown — cleanly shut down the daemon process.

    Stops the event loop, cleans up discovery/PID files, and exits.
    """
    import os
    import signal

    orch = current_app.config["orchestrator"]
    vault_path = current_app.config["vault_path"]

    try:
        orch.stop()
    except Exception:
        pass

    # Clean up discovery and PID files
    from .server import cleanup_discovery_file
    from pathlib import Path
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

    exit_thread = threading.Thread(target=_exit, daemon=True)
    exit_thread.start()

    return response
