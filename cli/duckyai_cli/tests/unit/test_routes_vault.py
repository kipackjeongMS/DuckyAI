"""Unit tests for native vault API routing."""

from pathlib import Path
from unittest.mock import MagicMock

from duckyai_cli.api.server import create_app


def _make_app(vault_path: Path):
    orchestrator = MagicMock()
    orchestrator.vault_path = vault_path
    config = MagicMock()
    app = create_app(orchestrator, config)
    app.config["TESTING"] = True
    return app


def test_vault_tool_uses_native_service_for_implemented_tool(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    app = _make_app(vault)

    with app.test_client() as client:
        response = client.post(
            "/api/vault/tool",
            json={"tool": "convertUtcToLocalDate", "arguments": {"utcTimestamp": "2026-03-19T01:30:00Z"}},
        )

    assert response.status_code == 200
    assert response.get_json()["content"][0]["text"]


def test_vault_tool_uses_native_service_for_create_task(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    app = _make_app(vault)

    with app.test_client() as client:
        response = client.post(
            "/api/vault/tool",
            json={"tool": "createTask", "arguments": {"title": "Write tests"}},
        )

    assert response.status_code == 200
    assert response.get_json() == {"content": [{"type": "text", "text": "Created task: Write tests (P2)"}]}


def test_vault_tool_uses_native_service_for_create_meeting(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    app = _make_app(vault)

    with app.test_client() as client:
        response = client.post(
            "/api/vault/tool",
            json={"tool": "createMeeting", "arguments": {"title": "Sprint Planning", "date": "2026-03-26"}},
        )

    assert response.status_code == 200
    assert response.get_json() == {"content": [{"type": "text", "text": "Created meeting: 2026-03-26 Sprint Planning.md"}]}


def test_vault_tool_uses_native_service_for_chat_sync_state(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    app = _make_app(vault)

    with app.test_client() as client:
        response = client.post(
            "/api/vault/tool",
            json={"tool": "getTeamsChatSyncState", "arguments": {}},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "content": [{"type": "text", "text": '{"lastSynced": null, "processedThreads": [], "syncCount": 0}'}]
    }


def test_vault_tool_uses_native_service_for_weekly_review(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    app = _make_app(vault)

    with app.test_client() as client:
        response = client.post(
            "/api/vault/tool",
            json={"tool": "prepareWeeklyReview", "arguments": {"week": "2026-W13"}},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "content": [{"type": "text", "text": "Created 2026-W13.md (2026-03-23 to 2026-03-27) with 0 completed tasks aggregated"}]
    }


def test_vault_tool_uses_native_service_for_generate_roundup(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    daily_dir = vault / "04-Periodic" / "Daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    (daily_dir / "2026-03-26.md").write_text("## Tasks\n- [x] shipped feature\n", encoding="utf-8")
    app = _make_app(vault)

    with app.test_client() as client:
        response = client.post(
            "/api/vault/tool",
            json={"tool": "generateRoundup", "arguments": {"date": "2026-03-26"}},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "content": [{"type": "text", "text": "Generated roundup for 2026-03-26: 1 completed tasks, 0 meetings, 0 tasks updated, 0 items to carry forward"}]
    }


def test_vault_tool_uses_native_service_for_triage_inbox(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    inbox = vault / "00-Inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "Fix bug.md").write_text("bug", encoding="utf-8")
    app = _make_app(vault)

    with app.test_client() as client:
        response = client.post(
            "/api/vault/tool",
            json={"tool": "triageInbox", "arguments": {}},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "content": [{"type": "text", "text": 'Triage preview (dry run):\n📋 "Fix bug.md" → task (01-Work/Tasks/)'}]
    }


def test_vault_tool_rejects_unknown_tool(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    app = _make_app(vault)

    with app.test_client() as client:
        response = client.post(
            "/api/vault/tool",
            json={"tool": "doesNotExist", "arguments": {}},
        )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Unknown tool: doesNotExist"}


def test_vault_tool_rejects_non_object_arguments(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    app = _make_app(vault)

    with app.test_client() as client:
        response = client.post(
            "/api/vault/tool",
            json={"tool": "getCurrentDate", "arguments": []},
        )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Field 'arguments' must be an object"}