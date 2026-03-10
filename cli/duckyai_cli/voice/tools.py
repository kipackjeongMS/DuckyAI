"""Tool bridge — maps DuckyAI MCP tools to Azure Voice Live function calls."""

import json
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional


def get_vault_tools() -> List[Dict[str, Any]]:
    """Return tool definitions for Voice Live function calling."""
    return [
        {
            "type": "function",
            "name": "search_vault",
            "description": "Search the user's knowledge vault for notes, documents, and topics by keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (keywords or phrase)"},
                },
                "required": ["query"],
            },
        },
        {
            "type": "function",
            "name": "get_today_meetings",
            "description": "Get today's meetings from the daily note.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "type": "function",
            "name": "get_today_tasks",
            "description": "Get today's tasks and action items from the daily note.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "type": "function",
            "name": "create_task",
            "description": "Create a new task in the vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task title"},
                    "description": {"type": "string", "description": "Task description"},
                    "priority": {"type": "string", "enum": ["P1", "P2", "P3"], "description": "Priority level"},
                },
                "required": ["title"],
            },
        },
        {
            "type": "function",
            "name": "trigger_teams_sync",
            "description": "Trigger Teams chat and meeting sync agents (TCS and TMS).",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "type": "function",
            "name": "read_note",
            "description": "Read the content of a specific note from the vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Note filename (e.g., '2026-03-10 Ki-JM 1-1.md')"},
                },
                "required": ["filename"],
            },
        },
        {
            "type": "function",
            "name": "get_recent_chats",
            "description": "Get recent Teams chat highlights from the daily note.",
            "parameters": {"type": "object", "properties": {}},
        },
    ]


def _find_vault_root() -> Path:
    """Find the vault root directory."""
    cwd = Path.cwd()
    for p in [cwd] + list(cwd.parents):
        if (p / "orchestrator.yaml").exists():
            return p
    return cwd


def _read_daily_note_section(section: str) -> str:
    """Read a section from today's daily note."""
    from datetime import datetime
    vault = _find_vault_root()
    today = datetime.now().strftime("%Y-%m-%d")
    daily = vault / "04-Periodic" / "Daily" / f"{today}.md"

    if not daily.exists():
        return f"No daily note found for {today}."

    content = daily.read_text(encoding="utf-8")
    lines = content.split("\n")

    in_section = False
    result = []
    for line in lines:
        if line.startswith(f"## {section}"):
            in_section = True
            continue
        elif line.startswith("## ") and in_section:
            break
        elif in_section:
            result.append(line)

    text = "\n".join(result).strip()
    return text if text else f"No {section} section found in today's daily note."


def _search_vault(query: str) -> str:
    """Search vault files for a query string."""
    vault = _find_vault_root()
    results = []

    for ext in ["*.md"]:
        for f in vault.rglob(ext):
            # Skip hidden dirs and archives
            parts = f.relative_to(vault).parts
            if any(p.startswith(".") or p == "05-Archive" for p in parts):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if query.lower() in content.lower():
                    rel = str(f.relative_to(vault))
                    # Extract a snippet around the match
                    idx = content.lower().index(query.lower())
                    start = max(0, idx - 100)
                    end = min(len(content), idx + 200)
                    snippet = content[start:end].replace("\n", " ").strip()
                    results.append(f"**{rel}**: ...{snippet}...")
            except Exception:
                continue

            if len(results) >= 5:
                break
        if len(results) >= 5:
            break

    if results:
        return f"Found {len(results)} results for '{query}':\n\n" + "\n\n".join(results)
    return f"No results found for '{query}' in the vault."


def _read_note(filename: str) -> str:
    """Read a note from the vault."""
    vault = _find_vault_root()

    # Search common locations
    for subdir in ["02-People/Meetings", "04-Periodic/Daily", "03-Knowledge", "01-Work", "00-Inbox", ""]:
        path = vault / subdir / filename if subdir else vault / filename
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="ignore")
            # Truncate for voice (keep first 2000 chars)
            if len(content) > 2000:
                content = content[:2000] + "\n\n...(truncated for voice)"
            return content

    return f"Note '{filename}' not found in the vault."


def _trigger_teams_sync() -> str:
    """Trigger TCS and TMS agents."""
    duckyai = shutil.which("duckyai")
    if not duckyai:
        return "duckyai CLI not found."

    try:
        subprocess.Popen(
            [duckyai, "orchestrator", "trigger", "TCS"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        subprocess.Popen(
            [duckyai, "orchestrator", "trigger", "TMS"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return "TCS and TMS agents triggered. They'll run in the background."
    except Exception as e:
        return f"Failed to trigger sync: {e}"


def _create_task(title: str, description: str = "", priority: str = "P2") -> str:
    """Create a task by writing to the tasks directory."""
    from datetime import datetime
    vault = _find_vault_root()
    tasks_dir = vault / "01-Work" / "Tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today} {title}.md"
    task_path = tasks_dir / filename

    if task_path.exists():
        return f"Task '{title}' already exists."

    content = f"""---
created: {today}
type: task
priority: {priority}
status: open
tags:
  - task
---

# {title}

{description}
"""
    task_path.write_text(content, encoding="utf-8")
    return f"Created task: {title} ({priority})"


async def handle_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    """Execute a tool call and return the result as text."""
    try:
        if name == "search_vault":
            return _search_vault(arguments.get("query", ""))
        elif name == "get_today_meetings":
            return _read_daily_note_section("Teams Meeting Highlights")
        elif name == "get_today_tasks":
            return _read_daily_note_section("Focus Today")
        elif name == "get_recent_chats":
            return _read_daily_note_section("Teams Chat Highlights")
        elif name == "create_task":
            return _create_task(
                arguments.get("title", "Untitled"),
                arguments.get("description", ""),
                arguments.get("priority", "P2"),
            )
        elif name == "trigger_teams_sync":
            return _trigger_teams_sync()
        elif name == "read_note":
            return _read_note(arguments.get("filename", ""))
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool error: {e}"
