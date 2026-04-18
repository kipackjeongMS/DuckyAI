"""Python MCP server exposing vault tools through VaultService."""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .api.vault_service import VaultService


mcp = FastMCP(
    "duckyai-vault",
    instructions="DuckyAI Vault MCP server backed by native Python VaultService tools.",
)


def _vault_root() -> Path:
    raw = os.environ.get("DUCKYAI_VAULT_ROOT")
    return Path(raw).resolve() if raw else Path.cwd().resolve()


def _call(tool_name: str, arguments: dict) -> str:
    result = VaultService(_vault_root()).call_tool(tool_name, arguments)
    content = result.get("content") or []
    if content and isinstance(content[0], dict):
        text = content[0].get("text")
        if isinstance(text, str):
            return text
    return ""


@mcp.tool(name="getCurrentDate", description="Get the current date and time in the user's configured timezone.")
def get_current_date() -> str:
    return _call("getCurrentDate", {})


@mcp.tool(name="prepareDailyNote", description="Create today's daily note from template and carry forward open items.")
def prepare_daily_note(date: str | None = None) -> str:
    arguments = {} if date is None else {"date": date}
    return _call("prepareDailyNote", arguments)


@mcp.tool(name="createTask", description="Create a task file in 01-Work/Tasks/.")
def create_task(
    title: str,
    description: str | None = None,
    priority: str = "P2",
    project: str | None = None,
    due: str | None = None,
) -> str:
    return _call(
        "createTask",
        {
            "title": title,
            "description": description,
            "priority": priority,
            "project": project,
            "due": due,
        },
    )


@mcp.tool(name="logTask", description="Append a task link to today's daily note Tasks section.")
def log_task(title: str) -> str:
    return _call("logTask", {"title": title})


@mcp.tool(name="updateTaskStatus", description="Update a task status in YAML frontmatter.")
def update_task_status(title: str, status: str) -> str:
    return _call("updateTaskStatus", {"title": title, "status": status})


@mcp.tool(name="archiveTask", description="Archive a task by moving it into 05-Archive/.")
def archive_task(title: str, status: str = "done") -> str:
    return _call("archiveTask", {"title": title, "status": status})


@mcp.tool(name="logAction", description="Append a completed action to today's daily note Tasks section.")
def log_action(action: str, addToCarryForward: str | None = None) -> str:
    arguments = {"action": action}
    if addToCarryForward is not None:
        arguments["addToCarryForward"] = addToCarryForward
    return _call("logAction", arguments)


@mcp.tool(name="logPRReview", description="Create or update a PR review record and daily log entry.")
def log_pr_review(person: str, description: str, action: str, prNumber: str = "", prUrl: str = "") -> str:
    return _call(
        "logPRReview",
        {
            "person": person,
            "prNumber": prNumber,
            "prUrl": prUrl,
            "description": description,
            "action": action,
        },
    )


@mcp.tool(name="createMeeting", description="Create a meeting note from the meeting template.")
def create_meeting(
    title: str,
    date: str | None = None,
    time: str | None = None,
    attendees: list[str] | None = None,
    project: str | None = None,
) -> str:
    return _call(
        "createMeeting",
        {
            "title": title,
            "date": date,
            "time": time,
            "attendees": attendees,
            "project": project,
        },
    )


@mcp.tool(name="create1on1", description="Create a 1:1 meeting note from the 1:1 template.")
def create_1on1(person: str, date: str | None = None) -> str:
    arguments = {"person": person}
    if date is not None:
        arguments["date"] = date
    return _call("create1on1", arguments)


@mcp.tool(name="triageInbox", description="Inspect and categorize items under 00-Inbox/.")
def triage_inbox(dryRun: bool = True) -> str:
    return _call("triageInbox", {"dryRun": dryRun})


@mcp.tool(name="enrichNote", description="Enrich a note with structure, links, and frontmatter.")
def enrich_note(filePath: str) -> str:
    return _call("enrichNote", {"filePath": filePath})


@mcp.tool(name="updateTopicIndex", description="Update topic index files in 03-Knowledge/Topics/.")
def update_topic_index(topic: str) -> str:
    return _call("updateTopicIndex", {"topic": topic})


@mcp.tool(name="generateRoundup", description="Generate the daily roundup.")
def generate_roundup(date: str | None = None) -> str:
    arguments = {} if date is None else {"date": date}
    return _call("generateRoundup", arguments)


@mcp.tool(name="prepareWeeklyReview", description="Create the weekly review note.")
def prepare_weekly_review(week: str | None = None) -> str:
    arguments = {} if week is None else {"week": week}
    return _call("prepareWeeklyReview", arguments)


@mcp.tool(name="getTeamsChatSyncState", description="Read Teams chat sync watermark state.")
def get_teams_chat_sync_state() -> str:
    return _call("getTeamsChatSyncState", {})


@mcp.tool(name="updateTeamsChatSyncState", description="Write Teams chat sync watermark state.")
def update_teams_chat_sync_state(
    lastSynced: str,
    processedThreadIds: list[str] | None = None,
    processedDates: list[str] | None = None,
) -> str:
    return _call(
        "updateTeamsChatSyncState",
        {
            "lastSynced": lastSynced,
            "processedThreadIds": processedThreadIds,
            "processedDates": processedDates,
        },
    )


@mcp.tool(name="appendTeamsChatHighlights", description="Append Teams chat highlights to today's daily note.")
def append_teams_chat_highlights(
    highlights: str,
    date: str | None = None,
    people: list[str] | None = None,
    personNotes: list[dict[str, str]] | None = None,
) -> str:
    return _call(
        "appendTeamsChatHighlights",
        {
            "highlights": highlights,
            "date": date,
            "people": people,
            "personNotes": personNotes,
        },
    )


@mcp.tool(name="getTeamsMeetingSyncState", description="Read Teams meeting sync watermark state.")
def get_teams_meeting_sync_state() -> str:
    return _call("getTeamsMeetingSyncState", {})


@mcp.tool(name="updateTeamsMeetingSyncState", description="Write Teams meeting sync watermark state.")
def update_teams_meeting_sync_state(
    lastSynced: str,
    processedMeetingIds: list[str] | None = None,
    processedDates: list[str] | None = None,
) -> str:
    return _call(
        "updateTeamsMeetingSyncState",
        {
            "lastSynced": lastSynced,
            "processedMeetingIds": processedMeetingIds,
            "processedDates": processedDates,
        },
    )


@mcp.tool(name="appendTeamsMeetingHighlights", description="Append Teams meeting highlights to today's daily note.")
def append_teams_meeting_highlights(
    highlights: str,
    date: str | None = None,
    people: list[str] | None = None,
    personNotes: list[dict[str, str]] | None = None,
) -> str:
    return _call(
        "appendTeamsMeetingHighlights",
        {
            "highlights": highlights,
            "date": date,
            "people": people,
            "personNotes": personNotes,
        },
    )


@mcp.tool(name="updateDailyNoteSection", description="Update a specific H2 section in today's daily note.")
def update_daily_note_section(date: str, sectionHeader: str, content: str) -> str:
    return _call(
        "updateDailyNoteSection",
        {"date": date, "sectionHeader": sectionHeader, "content": content},
    )


@mcp.tool(name="convertUtcToLocalDate", description="Convert a UTC timestamp to the user's local date and time.")
def convert_utc_to_local_date(utcTimestamp: str) -> str:
    return _call("convertUtcToLocalDate", {"utcTimestamp": utcTimestamp})


# ── Orchestrator tools (proxy to daemon HTTP API) ──────────────

_DAEMON_URL = "http://127.0.0.1:52845"


def _daemon_get(path: str) -> str:
    """GET request to the daemon API."""
    import urllib.request
    import json
    try:
        req = urllib.request.Request(f"{_DAEMON_URL}{path}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        return json.dumps({"error": str(e)})


def _daemon_post(path: str, data: dict | None = None) -> str:
    """POST request to the daemon API."""
    import urllib.request
    import json
    try:
        body = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(
            f"{_DAEMON_URL}{path}",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(
    name="orchestratorStatus",
    description="Check if the DuckyAI orchestrator daemon is running and get agent counts.",
)
def orchestrator_status() -> str:
    return _daemon_get("/api/orchestrator/status")


@mcp.tool(
    name="listAgents",
    description="List all available DuckyAI orchestrator agents with their abbreviations, schedules, and status.",
)
def list_agents() -> str:
    return _daemon_get("/api/orchestrator/agents")


@mcp.tool(
    name="triggerAgent",
    description=(
        "Trigger a DuckyAI agent by abbreviation (e.g. TCS, TMS, PRS, EIC, TM). "
        "The agent runs in the background via the orchestrator daemon. "
        "For TCS/TMS: set lookback_hours for a time window, or omit for since-last-sync."
    ),
)
def trigger_agent(
    agent: str,
    file: str | None = None,
    lookback_hours: int | None = None,
    sinceLastSync: bool | None = None,
) -> str:
    import json
    body: dict = {"agent": agent}
    agent_params: dict = {}
    if file:
        body["input_file"] = file
    if lookback_hours is not None:
        agent_params["lookback_hours"] = lookback_hours
    if sinceLastSync is not None:
        agent_params["sinceLastSync"] = sinceLastSync
    if agent_params:
        body["agent_params"] = agent_params
    return _daemon_post("/api/orchestrator/trigger", body)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()