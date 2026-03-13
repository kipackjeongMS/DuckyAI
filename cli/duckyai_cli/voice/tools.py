"""Tool bridge — single mega-tool that delegates to Copilot SDK for full DuckyAI capabilities."""

import asyncio
import json
import subprocess
import shutil
import sys
import os
from pathlib import Path
from typing import List, Dict, Any


def get_vault_tools() -> List[Dict[str, Any]]:
    """Return tool definitions for Voice Live function calling.
    
    Single tool that delegates everything to the Copilot SDK,
    giving voice the same capabilities as the text CLI.
    """
    return [
        {
            "type": "function",
            "name": "duckyai_agent",
            "description": (
                "Execute any DuckyAI request through the full agent system. "
                "This tool has access to the user's entire knowledge vault, "
                "Microsoft Teams data (chats, meetings, emails via WorkIQ), "
                "task management, orchestrator control (trigger agents, check status), "
                "and all vault operations. Use this for ANY request that needs "
                "vault access, Teams data, task creation, agent triggers, or knowledge queries. "
                "Pass the user's request as-is."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "The user's request in natural language, forwarded to the DuckyAI agent",
                    },
                },
                "required": ["request"],
            },
        },
    ]


def _find_vault_root() -> Path:
    """Find the vault root directory."""
    cwd = Path.cwd()
    for p in [cwd] + list(cwd.parents):
        if (p / "duckyai.yml").exists():
            return p
    return cwd


def _get_copilot_sdk_python() -> str:
    """Find Python 3.10+ for the Copilot SDK."""
    uv_dir = Path(os.environ.get("APPDATA", "")) / "uv" / "python"
    if uv_dir.exists():
        for ver_dir in sorted(uv_dir.iterdir(), reverse=True):
            if "cpython-3.1" in ver_dir.name:
                py = ver_dir / "python.exe" if os.name == "nt" else ver_dir / "bin" / "python3"
                if py.exists():
                    return str(py)
    for ver in ["3.14", "3.13", "3.12", "3.11", "3.10"]:
        py = shutil.which(f"python{ver}")
        if py:
            return py
    return shutil.which("python3") or shutil.which("python") or "python"


async def handle_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    """Execute a tool call via the Copilot SDK."""
    if name != "duckyai_agent":
        return f"Unknown tool: {name}"

    request = arguments.get("request", "")
    if not request:
        return "No request provided."

    try:
        return await _run_copilot_agent(request)
    except Exception as e:
        return f"Agent error: {e}"


async def _run_copilot_agent(request: str) -> str:
    """Run a request through the Copilot SDK and return the text response."""
    vault_root = _find_vault_root()
    sdk_python = _get_copilot_sdk_python()
    # Check CLI package first, then vault
    cli_runner = Path(__file__).parent.parent / "scripts" / "copilot_sdk_runner.py"
    vault_runner = vault_root / "scripts" / "copilot_sdk_runner.py"
    runner = cli_runner if cli_runner.exists() else vault_runner

    if not runner.exists():
        return "Copilot SDK runner not found. Run duckyai setup."

    # Build MCP config for the runner
    from duckyai_cli.main.cli import get_mcp_config
    mcp_config = get_mcp_config(vault_root)

    # Prefix the request with voice context
    prompt = (
        f"You are responding to a voice request. Be concise and conversational — "
        f"this will be spoken aloud. Avoid markdown formatting, bullet lists, or long text. "
        f"Summarize key points in natural speech.\n\n"
        f"User request: {request}"
    )

    cmd = [
        sdk_python, str(runner),
        "--prompt", prompt,
        "--cwd", str(vault_root),
    ]
    if mcp_config:
        cmd.extend(["--mcp-config", mcp_config])

    # Run async subprocess
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(vault_root),
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        return "Agent timed out after 2 minutes."

    output = stdout.decode("utf-8", errors="replace")

    # Extract the SDK result if present
    marker = "__COPILOT_SDK_RESULT__"
    if marker in output:
        result_json = output.split(marker)[-1].strip()
        try:
            result = json.loads(result_json)
            if result.get("status") == "completed" and result.get("output"):
                return result["output"]
            elif result.get("errors"):
                return f"Agent encountered errors: {'; '.join(result['errors'])}"
        except json.JSONDecodeError:
            pass

    # Fall back to raw output (strip the marker line)
    lines = [l for l in output.strip().split("\n") if marker not in l]
    text = "\n".join(lines).strip()
    return text if text else "No response from agent."

