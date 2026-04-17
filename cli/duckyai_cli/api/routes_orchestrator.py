"""Orchestrator API routes — status, trigger, agents, history."""

import threading
from pathlib import Path
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


@bp.route("/history")
def history():
    """GET /api/orchestrator/history — execution history for a given day.

    Query params:
      date   — YYYY-MM-DD (defaults to today)
      agent  — filter by agent abbreviation (optional)
      status — filter by status (optional)
    """
    orch = current_app.config["orchestrator"]
    config = current_app.config["duckyai_config"]
    vault_path = Path(current_app.config["vault_path"])

    date_str = request.args.get("date")
    if not date_str:
        date_str = config.user_now().strftime("%Y-%m-%d")

    # Validate date format
    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    task_mgr = orch.execution_manager.task_manager
    if task_mgr is None:
        return jsonify([])

    daily_log = task_mgr._get_daily_log(date_str)
    entries = daily_log._read_entries()

    # Apply filters
    agent_filter = request.args.get("agent")
    status_filter = request.args.get("status")
    if agent_filter:
        entries = [e for e in entries if e.get("agent") == agent_filter]
    if status_filter:
        status_upper = status_filter.upper()
        entries = [e for e in entries if e.get("status", "").upper() == status_upper]

    return jsonify(entries)


@bp.route("/log/<execution_id>")
def execution_log(execution_id: str):
    """GET /api/orchestrator/log/<execution_id> — detailed log for one execution.

    Looks up the log_path from today's (or specified date's) entries,
    then reads and returns the log file content.

    Query params:
      date — YYYY-MM-DD (defaults to today)
    """
    import re

    config = current_app.config["duckyai_config"]
    orch = current_app.config["orchestrator"]
    vault_path = Path(current_app.config["vault_path"])

    date_str = request.args.get("date")
    if not date_str:
        date_str = config.user_now().strftime("%Y-%m-%d")

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Validate execution_id format (alphanumeric, max 64 chars)
    if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", execution_id):
        return jsonify({"error": "Invalid execution_id format."}), 400

    task_mgr = orch.execution_manager.task_manager
    if task_mgr is None:
        return jsonify({"error": "Task manager not available."}), 404

    daily_log = task_mgr._get_daily_log(date_str)
    entries = daily_log._read_entries()

    # Find the entry with matching execution_id
    entry = None
    for e in entries:
        if e.get("id") == execution_id:
            entry = e
            break

    if entry is None:
        return jsonify({"error": f"Execution '{execution_id}' not found."}), 404

    log_path_str = entry.get("log_path", "")

    # Fallback: construct log path from agent + created timestamp
    # Pattern: YYYY-MM-DD-HHMMSS-{AGENT}.log
    if not log_path_str:
        agent = entry.get("agent", "")
        created = entry.get("created", "")
        if agent and created:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(created)
                filename = f"{dt.strftime('%Y-%m-%d-%H%M%S')}-{agent}.log"
                # Check .duckyai/logs/ first, then legacy _Settings_/Logs/
                for logs_dir in [".duckyai/logs", "_Settings_/Logs"]:
                    candidate = vault_path / logs_dir / filename
                    if candidate.exists():
                        log_path_str = str(candidate.relative_to(vault_path))
                        break
            except (ValueError, TypeError):
                pass

    if not log_path_str:
        return jsonify({"error": "No log file recorded for this execution."}), 404

    # Resolve and validate path is under vault/.duckyai/logs/ or vault/_Settings_/Logs/
    log_path = (vault_path / log_path_str).resolve()
    allowed_dirs = [
        (vault_path / ".duckyai" / "logs").resolve(),
        (vault_path / "_Settings_" / "Logs").resolve(),
    ]
    if not any(str(log_path).startswith(str(d)) for d in allowed_dirs):
        return jsonify({"error": "Log path outside allowed directory."}), 403

    if not log_path.exists():
        return jsonify({"error": "Log file no longer exists."}), 404

    content = log_path.read_text(encoding="utf-8", errors="replace")
    return jsonify({
        "execution_id": execution_id,
        "log_path": log_path_str,
        "content": content,
    })
