"""Embedded MCP server assets for DuckyAI CLI."""
from pathlib import Path


def get_mcp_index_js() -> Path:
    """Return the path to the embedded MCP server dist/index.js."""
    return Path(__file__).parent / "dist" / "index.js"
