"""Smoke tests for the DuckyAI HTTP API server."""

import json
import os
import sys
import threading
import time

# Add cli/ to path so we can import duckyai_cli
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def make_mock_orchestrator(vault_path: Path):
    """Create a mock Orchestrator with the methods the API routes call."""
    orch = MagicMock()
    orch.vault_path = vault_path
    orch.get_status.return_value = {
        "running": True,
        "vault_path": str(vault_path),
        "agents_loaded": 2,
        "pollers_loaded": 1,
        "running_executions": 0,
        "max_concurrent": 3,
        "agent_list": [
            {"abbreviation": "TCS", "name": "Teams Chat Summary",
             "category": "cron", "running": 0},
            {"abbreviation": "GDR", "name": "Generate Daily Roundup",
             "category": "cron", "running": 0},
        ],
    }

    # Mock agent_registry.agents
    mock_agent_tcs = MagicMock()
    mock_agent_tcs.abbreviation = "TCS"
    mock_agent_tcs.name = "Teams Chat Summary"
    mock_agent_tcs.category = "cron"
    mock_agent_tcs.cron = "0 * * * *"

    mock_agent_gdr = MagicMock()
    mock_agent_gdr.abbreviation = "GDR"
    mock_agent_gdr.name = "Generate Daily Roundup"
    mock_agent_gdr.category = "cron"
    mock_agent_gdr.cron = "0 18 * * 1-5"

    orch.agent_registry.agents = {"TCS": mock_agent_tcs, "GDR": mock_agent_gdr}
    orch.execution_manager.get_agent_running_count.return_value = 0

    return orch


@pytest.fixture
def client():
    from duckyai_cli.api.server import create_app

    vault_path = Path(__file__).resolve().parent.parent
    mock_config = MagicMock()
    mock_config.get.return_value = 52845

    orch = make_mock_orchestrator(vault_path)
    app = create_app(orch, mock_config)
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        yield test_client


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "pid" in data
    print("  PASS: GET /api/health")


def test_orchestrator_status(client):
    resp = client.get("/api/orchestrator/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["running"] is True
    assert data["agents_loaded"] == 2
    print("  PASS: GET /api/orchestrator/status")


def test_orchestrator_agents(client):
    resp = client.get("/api/orchestrator/agents")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2
    abbrs = {a["abbreviation"] for a in data}
    assert "TCS" in abbrs
    assert "GDR" in abbrs
    print("  PASS: GET /api/orchestrator/agents")


def test_orchestrator_trigger(client):
    resp = client.post(
        "/api/orchestrator/trigger",
        data=json.dumps({"agent": "TCS"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "triggered"
    assert data["agent"] == "TCS"
    print("  PASS: POST /api/orchestrator/trigger (TCS)")


def test_orchestrator_trigger_tm(client):
    mock_agent_tm = MagicMock()
    mock_agent_tm.abbreviation = "TM"
    mock_agent_tm.name = "Task Manager"
    mock_agent_tm.category = "cron"
    mock_agent_tm.cron = None
    client.application.config["orchestrator"].agent_registry.agents["TM"] = mock_agent_tm

    resp = client.post(
        "/api/orchestrator/trigger/tm",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "triggered"
    assert data["agent"] == "TM"
    print("  PASS: POST /api/orchestrator/trigger/tm")


def test_orchestrator_trigger_missing_agent(client):
    resp = client.post(
        "/api/orchestrator/trigger",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    print("  PASS: POST /api/orchestrator/trigger (missing agent → 400)")


def test_orchestrator_trigger_unknown_agent(client):
    resp = client.post(
        "/api/orchestrator/trigger",
        data=json.dumps({"agent": "FAKE"}),
        content_type="application/json",
    )
    assert resp.status_code == 404
    print("  PASS: POST /api/orchestrator/trigger (unknown agent → 404)")


def test_vault_tools_list(client):
    resp = client.get("/api/vault/tools")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "prepareDailyNote" in data
    assert "createTask" in data
    assert len(data) >= 20
    print(f"  PASS: GET /api/vault/tools ({len(data)} tools)")


def test_vault_tool_call_missing_tool(client):
    resp = client.post(
        "/api/vault/tool",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    print("  PASS: POST /api/vault/tool (missing tool → 400)")


def main():
    from duckyai_cli.api.server import create_app

    vault_path = Path(__file__).resolve().parent.parent
    mock_config = MagicMock()
    mock_config.get.return_value = 52845

    orch = make_mock_orchestrator(vault_path)
    app = create_app(orch, mock_config)
    app.config["TESTING"] = True

    with app.test_client() as client:
        print("Running DuckyAI HTTP API smoke tests...\n")

        test_health(client)
        test_orchestrator_status(client)
        test_orchestrator_agents(client)
        test_orchestrator_trigger(client)
        test_orchestrator_trigger_missing_agent(client)
        test_orchestrator_trigger_unknown_agent(client)
        test_vault_tools_list(client)
        test_vault_tool_call_missing_tool(client)

        print(f"\nAll 8 tests passed!")


if __name__ == "__main__":
    main()
