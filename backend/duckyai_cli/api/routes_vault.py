"""Vault API routes backed by the native Python VaultService."""

from flask import Blueprint, current_app, jsonify, request

from .vault_service import UnknownVaultToolError, VaultService

bp = Blueprint("vault", __name__)


@bp.route("/tools")
def list_tools():
    """GET /api/vault/tools — list available vault tools."""
    vault_path = current_app.config["vault_path"]
    return jsonify(VaultService(vault_path).list_tools())


@bp.route("/tool", methods=["POST"])
def call_tool():
    """POST /api/vault/tool — call a vault MCP tool.

    Body: { "tool": "prepareDailyNote", "arguments": {...} }
    """
    data = request.get_json(silent=True) or {}

    tool_name = data.get("tool")
    if not tool_name:
        return jsonify({"error": "Missing required field: tool"}), 400

    arguments = data.get("arguments", {})
    if not isinstance(arguments, dict):
        return jsonify({"error": "Field 'arguments' must be an object"}), 400

    vault_path = current_app.config["vault_path"]
    vault_svc = VaultService(vault_path)

    if not vault_svc.is_known_tool(tool_name):
        return jsonify({"error": f"Unknown tool: {tool_name}"}), 400

    try:
        result = vault_svc.call_tool(tool_name, arguments)
    except UnknownVaultToolError as exc:
        return jsonify({"error": str(exc)}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if "error" in result:
        return jsonify(result), 500

    return jsonify(result)
