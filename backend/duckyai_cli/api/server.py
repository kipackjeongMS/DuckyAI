"""Flask application factory for the DuckyAI HTTP API."""

import json
import os
import threading
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify
from flask_cors import CORS

from ..logger import Logger

logger = Logger()

DEFAULT_PORT = 52845


def create_app(orchestrator, config) -> Flask:
    """Create and configure the Flask application.

    Args:
        orchestrator: Running Orchestrator instance
        config: Config instance
    """
    app = Flask(__name__)
    CORS(app)

    # Store references for route handlers
    app.config["orchestrator"] = orchestrator
    app.config["duckyai_config"] = config
    app.config["vault_path"] = str(orchestrator.vault_path)

    # Register route blueprints
    from .routes_daemon import bp as daemon_bp
    from .routes_orchestrator import bp as orch_bp
    from .routes_vault import bp as vault_bp

    app.register_blueprint(daemon_bp, url_prefix="/api/daemon")
    app.register_blueprint(orch_bp, url_prefix="/api/orchestrator")
    app.register_blueprint(vault_bp, url_prefix="/api/vault")

    # Top-level /api/health so clients don't need the /daemon prefix
    @app.route("/api/health")
    def top_level_health():
        return jsonify({"status": "ok", "pid": os.getpid()})

    return app


def start_api_server(
    orchestrator,
    config,
    port: Optional[int] = None,
    host: str = "127.0.0.1",
) -> threading.Thread:
    """Start the Flask API server in a background daemon thread.

    Args:
        orchestrator: Running Orchestrator instance
        config: Config instance
        port: Port number (defaults to config api.port or 52845)
        host: Bind address (defaults to localhost only)

    Returns:
        The daemon thread running the server
    """
    port = port or config.get("api.port", DEFAULT_PORT)

    app = create_app(orchestrator, config)

    def _run():
        # Suppress Flask's default startup banner in daemon mode
        import logging as stdlib_logging
        stdlib_logging.getLogger("werkzeug").setLevel(stdlib_logging.WARNING)

        app.run(host=host, port=port, threaded=True, use_reloader=False)

    thread = threading.Thread(target=_run, name="duckyai-api", daemon=True)
    thread.start()

    logger.info(f"HTTP API server started on http://{host}:{port}")

    # Write service discovery file
    _write_discovery_file(orchestrator.vault_path, host, port)

    return thread


def _write_discovery_file(vault_path: Path, host: str, port: int):
    """Write .duckyai/api.json so clients can discover the running API."""
    discovery_dir = vault_path / ".duckyai"
    discovery_dir.mkdir(parents=True, exist_ok=True)
    discovery_file = discovery_dir / "api.json"

    discovery = {
        "host": host,
        "port": port,
        "pid": os.getpid(),
        "url": f"http://{host}:{port}",
    }

    discovery_file.write_text(json.dumps(discovery, indent=2), encoding="utf-8")
    logger.info(f"Service discovery written to {discovery_file}")


def cleanup_discovery_file(vault_path: Path):
    """Remove the service discovery file on shutdown."""
    discovery_file = vault_path / ".duckyai" / "api.json"
    if discovery_file.exists():
        discovery_file.unlink(missing_ok=True)
