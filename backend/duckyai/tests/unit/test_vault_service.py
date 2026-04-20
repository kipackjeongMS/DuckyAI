"""Unit tests for the Phase 3 native VaultService."""

from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from duckyai.api.vault_service import VaultService, UnknownVaultToolError


def _write_daily_note(vault: Path, date: str, content: str) -> Path:
    daily_dir = vault / "04-Periodic" / "Daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_path = daily_dir / f"{date}.md"
    daily_path.write_text(content, encoding="utf-8")
    return daily_path


def _write_task(vault: Path, title: str, content: str) -> Path:
    tasks_dir = vault / "01-Work" / "Tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_path = tasks_dir / f"{title}.md"
    task_path.write_text(content, encoding="utf-8")
    return task_path


def test_get_current_date_formats_using_user_timezone(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text(
        'id: v1\nuser:\n  timezone: "America/Los_Angeles"\n',
        encoding="utf-8",
    )

    service = VaultService(vault)
    fixed_now = datetime(2026, 3, 26, 8, 9, 10, tzinfo=ZoneInfo("America/Los_Angeles"))
    monkeypatch.setattr(service, "_now_in_user_timezone", lambda: fixed_now)

    result = service.call_tool("getCurrentDate", {})

    assert result == {
        "content": [
            {"type": "text", "text": "Date: 2026-03-26\nTime: 08:09:10\nTimezone: America/Los_Angeles"}
        ]
    }


def test_convert_utc_to_local_date_converts_across_day_boundary(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text(
        'id: v1\nuser:\n  timezone: "America/Los_Angeles"\n',
        encoding="utf-8",
    )

    service = VaultService(vault)

    result = service.call_tool("convertUtcToLocalDate", {"utcTimestamp": "2026-03-19T01:30:00Z"})

    assert result == {"content": [{"type": "text", "text": "2026-03-18 18:30"}]}


def test_convert_utc_to_local_date_rejects_invalid_timestamp(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\n', encoding="utf-8")

    service = VaultService(vault)

    result = service.call_tool("convertUtcToLocalDate", {"utcTimestamp": "not-a-timestamp"})

    assert result == {"content": [{"type": "text", "text": "Invalid timestamp: not-a-timestamp"}]}


def test_call_tool_rejects_unknown_tool(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\n', encoding="utf-8")

    service = VaultService(vault)

    with pytest.raises(UnknownVaultToolError):
        service.call_tool("doesNotExist", {})


def test_create_task_creates_task_file_from_template(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")

    result = service.call_tool(
        "createTask",
        {
            "title": "Write tests",
            "description": "Add coverage for Group 3",
            "priority": "P1",
            "project": "Migration",
            "due": "2026-03-30",
        },
    )
    created = (vault / "01-Work" / "Tasks" / "Write tests.md").read_text(encoding="utf-8")

    assert result == {"content": [{"type": "text", "text": "Created task: Write tests (P1)"}]}
    assert "created: 2026-03-26" in created
    assert "modified: 2026-03-26" in created
    assert "priority: P1" in created
    assert "due: 2026-03-30" in created
    assert "project: Migration" in created
    assert "## Description\nAdd coverage for Group 3" in created


def test_create_task_deduplicates_case_insensitive_and_fuzzy_titles(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\n', encoding="utf-8")
    _write_task(vault, "Write Tests", "existing")

    service = VaultService(vault)

    exact = service.call_tool("createTask", {"title": "write tests"})
    fuzzy = service.call_tool("createTask", {"title": "Write   tests!!!"})

    assert exact == {
        "content": [{"type": "text", "text": 'Task "Write Tests" already exists (case-insensitive match). Skipped.'}]
    }
    assert fuzzy == {
        "content": [{"type": "text", "text": 'Task "Write Tests" already exists (similar title). Skipped.'}]
    }


def test_update_task_status_updates_frontmatter(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_task(
        vault,
        "Write tests",
        "---\ncreated: 2026-03-20\nmodified: 2026-03-20\nstatus: todo\n---\n",
    )

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
    result = service.call_tool("updateTaskStatus", {"title": "Write tests", "status": "blocked"})
    updated = (vault / "01-Work" / "Tasks" / "Write tests.md").read_text(encoding="utf-8")

    assert result == {"content": [{"type": "text", "text": 'Updated "Write tests" status to blocked'}]}
    assert "status: blocked" in updated
    assert "modified: 2026-03-26" in updated


def test_archive_task_moves_file_and_updates_frontmatter(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_task(
        vault,
        "Write tests",
        "---\ncreated: 2026-03-20\nmodified: 2026-03-20\nstatus: todo\n---\n",
    )

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
    result = service.call_tool("archiveTask", {"title": "Write tests", "status": "cancelled"})

    archived_path = vault / "05-Archive" / "Write tests.md"
    assert result == {"content": [{"type": "text", "text": 'Archived "Write tests" as cancelled'}]}
    assert not (vault / "01-Work" / "Tasks" / "Write tests.md").exists()
    assert archived_path.exists()
    archived = archived_path.read_text(encoding="utf-8")
    assert "status: cancelled" in archived
    assert "modified: 2026-03-26" in archived


def test_log_pr_review_creates_pr_note_updates_daily_note_and_contact(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-26",
        "## PRs & Code Reviews\n- [ ]\n\n## Notes\n\n",
    )

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")

    result = service.call_tool(
        "logPRReview",
        {
            "person": "Shi Chen",
            "prNumber": "14653251",
            "prUrl": "https://example/pr/14653251",
            "description": "Add migration tests",
            "action": "todo",
        },
    )

    daily = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")
    pr_review = (vault / "01-Work" / "PRReviews" / "Review PR 14653251 - Add migration tests.md").read_text(encoding="utf-8")
    contact = (vault / "02-People" / "Contacts" / "Shi Chen.md").read_text(encoding="utf-8")

    assert result == {
        "content": [{"type": "text", "text": "Logged queued for review on Shi Chen's PR review: Add migration tests (created contact for Shi Chen)"}]
    }
    assert "[PR 14653251](../../01-Work/PRReviews/Review%20PR%2014653251%20-%20Add%20migration%20tests.md) - Add migration tests" in daily
    assert "status: todo" in pr_review
    assert "[Shi Chen](../../02-People/Contacts/Shi%20Chen.md)" in pr_review
    assert "First referenced in [PR 14653251](https://example/pr/14653251) - Add migration tests" in contact


def test_log_pr_review_empty_pr_url_accepted(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-26",
        "## PRs & Code Reviews\n- [ ]\n\n## Notes\n\n",
    )

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")

    # prUrl is empty string — should not raise
    result = service.call_tool(
        "logPRReview",
        {
            "person": "Shi Chen",
            "prNumber": "99999",
            "prUrl": "",
            "description": "No URL available",
            "action": "todo",
        },
    )

    pr_review = (vault / "01-Work" / "PRReviews" / "Review PR 99999 - No URL available.md").read_text(encoding="utf-8")

    assert "Logged queued for review" in result["content"][0]["text"]
    # Without a URL, the PR line should show plain text, not a broken hyperlink
    assert "- **PR**: PR 99999" in pr_review
    assert "]()" not in pr_review


def test_log_pr_review_no_pr_number_uses_description_as_title(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-27",
        "## PRs & Code Reviews\n- [ ]\n\n## Notes\n\n",
    )

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-27")

    result = service.call_tool(
        "logPRReview",
        {
            "person": "Richard Muniu",
            "prNumber": "",
            "description": "Review and approve cherry-pick PRs",
            "action": "todo",
        },
    )

    daily = (vault / "04-Periodic" / "Daily" / "2026-03-27.md").read_text(encoding="utf-8")
    pr_file = vault / "01-Work" / "PRReviews" / "Review and approve cherry-pick PRs.md"
    assert pr_file.exists()
    pr_review = pr_file.read_text(encoding="utf-8")

    assert "Logged queued for review" in result["content"][0]["text"]
    # File uses description as title (no "Review PR X -" prefix)
    assert "status: todo" in pr_review
    assert "- **Description**: Review and approve cherry-pick PRs" in pr_review
    # Daily note entry lands in PRs & Code Reviews, not Tasks
    assert "PRs & Code Reviews" in daily
    assert "[Review and approve cherry-pick PRs](../../01-Work/PRReviews/Review%20and%20approve%20cherry-pick%20PRs.md)" in daily


def test_log_pr_review_completed_adds_tasks_completed_and_reuses_existing_pr_file(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-26",
        "## PRs & Code Reviews\n- [ ]\n\n## Notes\n\n",
    )
    pr_reviews_dir = vault / "01-Work" / "PRReviews"
    pr_reviews_dir.mkdir(parents=True, exist_ok=True)
    existing = pr_reviews_dir / "Review PR 14653251 - Original description.md"
    existing.write_text("existing", encoding="utf-8")

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")

    result = service.call_tool(
        "logPRReview",
        {
            "person": "Shi Chen",
            "prNumber": "14653251",
            "prUrl": "https://example/pr/14653251",
            "description": "Updated description",
            "action": "reviewed",
        },
    )
    daily = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")

    assert result == {
        "content": [{"type": "text", "text": "Logged reviewed on Shi Chen's PR review: Updated description (created contact for Shi Chen)"}]
    }
    assert "Reviewed [Shi Chen](../../02-People/Contacts/Shi%20Chen.md)'s PR - [PR 14653251](../../01-Work/PRReviews/Review%20PR%2014653251%20-%20Original%20description.md) - Updated description" in daily
    assert existing.read_text(encoding="utf-8") == "existing"


def test_create_meeting_creates_note_and_contacts(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
    result = service.call_tool(
        "createMeeting",
        {
            "title": "Sprint Planning",
            "date": "2026-03-27",
            "time": "10:30",
            "attendees": ["Aarti Shah", "AL Bara"],
            "project": "Migration",
        },
    )

    meeting = (vault / "02-People" / "Meetings" / "2026-03-27 Sprint Planning.md").read_text(encoding="utf-8")
    aarti = (vault / "02-People" / "Contacts" / "Aarti Shah.md").read_text(encoding="utf-8")
    al_bara = (vault / "02-People" / "Contacts" / "AL Bara.md").read_text(encoding="utf-8")

    assert result == {
        "content": [{"type": "text", "text": "Created meeting: 2026-03-27 Sprint Planning.md (created contacts: Aarti Shah, AL Bara)"}]
    }
    assert "time: 10:30" in meeting
    assert 'attendees: ["Aarti Shah", "AL Bara"]' in meeting
    assert "project: Migration" in meeting
    assert "## Attendees\n- [Aarti Shah](../Contacts/Aarti%20Shah.md)\n- [AL Bara](../Contacts/AL%20Bara.md)" in meeting
    assert "First met in meeting: Sprint Planning" in aarti
    assert "First met in meeting: Sprint Planning" in al_bara


def test_create_1on1_creates_note_and_contact(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
    result = service.call_tool("create1on1", {"person": "Aarti Shah"})

    one_on_one = (vault / "02-People" / "1-on-1s" / "2026-03-26 Aarti Shah.md").read_text(encoding="utf-8")
    contact = (vault / "02-People" / "Contacts" / "Aarti Shah.md").read_text(encoding="utf-8")

    assert result == {
        "content": [{"type": "text", "text": "Created 1:1: 2026-03-26 Aarti Shah.md (created contact for Aarti Shah)"}]
    }
    assert "person: Aarti Shah" in one_on_one or 'person: "Aarti Shah"' in one_on_one
    assert "# 1:1 with [Aarti Shah](../Contacts/Aarti%20Shah.md) - 2026-03-26" in one_on_one
    assert "## Notes\n- 1:1 partner" in contact or "## Notes\n- 1:1 partner\n" in contact


def test_prepare_daily_note_creates_note_with_carry_forward(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-25",
        "## Focus Today\n- [ ] keep this\n- [x] done\n\n## Carried from yesterday\n- (none)\n\n## Tasks\n- [ ] \n\n## End of Day\n### Carry forward to tomorrow\n- [ ] follow up\n",
    )

    service = VaultService(vault)
    result = service.call_tool("prepareDailyNote", {"date": "2026-03-26"})
    created = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")

    assert result == {"content": [{"type": "text", "text": "Created 2026-03-26.md with 2 carried items from 2026-03-25.md"}]}
    assert "## Carried from yesterday\n- [ ] keep this\n- [ ] follow up" in created
    assert "# Thursday, March 26, 2026" in created


def test_prepare_daily_note_reports_existing_file(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(vault, "2026-03-26", "existing")

    service = VaultService(vault)

    result = service.call_tool("prepareDailyNote", {"date": "2026-03-26"})

    assert result == {"content": [{"type": "text", "text": "Daily note for 2026-03-26 already exists."}]}


def test_log_action_appends_completed_and_carry_forward(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-26",
        "## Tasks\n- [ ]\n\n## End of Day\n### Carry forward to tomorrow\n- [ ]\n",
    )

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
    service.call_tool("logAction", {"action": "shipped feature", "addToCarryForward": "follow up tomorrow"})
    updated = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")

    assert "## Tasks\n- [x] shipped feature" in updated
    assert "### Carry forward to tomorrow\n- [ ] follow up tomorrow" in updated


def test_log_task_appends_and_deduplicates(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-26",
        "## Tasks\n- [ ]\n\n## Notes\n\n",
    )

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
    first = service.call_tool("logTask", {"title": "Write tests"})
    second = service.call_tool("logTask", {"title": "Write tests"})
    updated = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")

    assert first == {"content": [{"type": "text", "text": "Added to ## Tasks: Write tests"}]}
    assert second == {"content": [{"type": "text", "text": 'Task "Write tests" already in daily note. Skipped.'}]}
    assert updated.count("[Write tests](../../01-Work/Tasks/Write%20tests.md)") == 1


def test_update_daily_note_section_creates_note_and_replaces_section(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")

    service = VaultService(vault)
    result = service.call_tool(
        "updateDailyNoteSection",
        {
            "date": "2026-03-26",
            "sectionHeader": "Teams Chat Highlights",
            "content": "### Chat A\n- summary",
        },
    )
    created = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")

    assert result == {"content": [{"type": "text", "text": "✅ Updated section '## Teams Chat Highlights' in 2026-03-26.md"}]}
    assert "## Teams Chat Highlights" in created
    assert "### Chat A\n- summary" in created
    assert created.index("## Teams Chat Highlights") < created.index("## End of Day")


def test_get_teams_chat_sync_state_defaults_to_empty(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")

    service = VaultService(vault)
    result = service.call_tool("getTeamsChatSyncState", {})

    payload = json.loads(result["content"][0]["text"])
    assert payload == {"lastSynced": None, "processedThreads": [], "syncCount": 0}


def test_update_teams_chat_sync_state_tracks_pending_dates(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(vault, "2026-03-26", "## Teams Chat Highlights\n### Chat A\n- hello\n")

    service = VaultService(vault)
    monkeypatch.setattr(service, "_utc_now_iso", lambda: "2026-03-26T12:00:00Z")
    result = service.call_tool(
        "updateTeamsChatSyncState",
        {
            "lastSynced": "2026-03-26T11:00:00Z",
            "processedThreadIds": ["thread-a", "thread-b"],
            "processedDates": ["2026-03-26", "2026-03-25"],
        },
    )

    state = json.loads((vault / ".duckyai" / "state" / "tcs-last-sync.json").read_text(encoding="utf-8"))
    assert result == {
        "content": [{"type": "text", "text": "✅ Sync state updated. Last synced: 2026-03-26T11:00:00Z (sync #1) ⚠️ 1 date(s) missing chat highlights: 2026-03-25"}]
    }
    assert state["processedThreads"] == ["thread-a", "thread-b"]
    assert state["pendingHighlightDates"] == ["2026-03-25"]
    assert state["updatedAt"] == "2026-03-26T12:00:00Z"


def test_append_teams_chat_highlights_merges_and_updates_contacts(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-26",
        "## Teams Chat Highlights\n### Chat A\n- [Topic One](https://example/1)\n\n## End of Day\n",
    )

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
    result = service.call_tool(
        "appendTeamsChatHighlights",
        {
            "highlights": "### Chat A\n- [Topic One](https://example/1)\n- [Topic Two](https://example/2)\n\n### Chat B\n- [Topic Three](https://example/3)",
            "people": ["Aarti Shah"],
            "personNotes": [{"name": "Aarti Shah", "note": "Needs follow-up"}],
        },
    )

    daily = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")
    contact = (vault / "02-People" / "Contacts" / "Aarti Shah.md").read_text(encoding="utf-8")

    assert result == {
        "content": [{"type": "text", "text": "✅ Updated daily note 2026-03-26; created contacts: Aarti Shah; updated notes for: Aarti Shah"}]
    }
    assert daily.count("Topic One") == 1
    assert "Topic Two" in daily
    assert "### Chat B" in daily
    assert "Referenced in Teams chat on 2026-03-26" in contact
    assert "- [2026-03-26] Needs follow-up" in contact


def test_get_teams_meeting_sync_state_defaults_to_empty(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")

    service = VaultService(vault)
    result = service.call_tool("getTeamsMeetingSyncState", {})

    payload = json.loads(result["content"][0]["text"])
    assert payload == {"lastSynced": None, "processedMeetings": [], "syncCount": 0}


def test_update_teams_meeting_sync_state_tracks_pending_dates(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(vault, "2026-03-26", "## Teams Meeting Highlights\n### Meeting A\n- summary\n")

    service = VaultService(vault)
    monkeypatch.setattr(service, "_utc_now_iso", lambda: "2026-03-26T12:30:00Z")
    result = service.call_tool(
        "updateTeamsMeetingSyncState",
        {
            "lastSynced": "2026-03-26T11:30:00Z",
            "processedMeetingIds": ["meeting-a", "meeting-b"],
            "processedDates": ["2026-03-26", "2026-03-24"],
        },
    )

    state = json.loads((vault / ".duckyai" / "state" / "tms-last-sync.json").read_text(encoding="utf-8"))
    assert result == {
        "content": [{"type": "text", "text": "✅ Meeting sync state updated. Last synced: 2026-03-26T11:30:00Z (sync #1) ⚠️ 1 date(s) missing meeting highlights: 2026-03-24"}]
    }
    assert state["processedMeetings"] == ["meeting-a", "meeting-b"]
    assert state["pendingHighlightDates"] == ["2026-03-24"]
    assert state["updatedAt"] == "2026-03-26T12:30:00Z"


def test_append_teams_meeting_highlights_merges_and_updates_contacts(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-26",
        "## Teams Meeting Highlights\n### [Design Review](https://example/design)\n- item one\n\n## End of Day\n",
    )

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
    result = service.call_tool(
        "appendTeamsMeetingHighlights",
        {
            "highlights": "### [Design Review](https://example/design)\n- item one\n\n### [Sprint Retro](https://example/retro)\n- item two",
            "people": ["AL Bara"],
            "personNotes": [{"name": "AL Bara", "note": "Raised deployment concern"}],
        },
    )

    daily = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")
    contact = (vault / "02-People" / "Contacts" / "AL Bara.md").read_text(encoding="utf-8")

    assert result == {
        "content": [{"type": "text", "text": "✅ Updated daily note 2026-03-26 with meeting highlights; created contacts: AL Bara; updated notes for: AL Bara"}]
    }
    assert daily.count("Design Review") == 1
    assert "Sprint Retro" in daily
    assert "Attended meeting on 2026-03-26" in contact
    assert "- [2026-03-26] Raised deployment concern" in contact


def test_prepare_weekly_review_aggregates_completed_tasks(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-23",
        "## Tasks\n- [x] shipped API\n- [x]\n\n## End of Day\n",
    )
    _write_daily_note(
        vault,
        "2026-03-25",
        "## Tasks\n- [x] reviewed PR\n\n## End of Day\n",
    )
    _write_daily_note(
        vault,
        "2026-03-28",
        "## Tasks\n- [x] weekend task\n\n## End of Day\n",
    )

    service = VaultService(vault)
    result = service.call_tool("prepareWeeklyReview", {"week": "2026-W13"})
    created = (vault / "04-Periodic" / "Weekly" / "2026-W13.md").read_text(encoding="utf-8")

    assert result == {
        "content": [{"type": "text", "text": "Created 2026-W13.md (2026-03-23 to 2026-03-27) with 2 completed tasks aggregated"}]
    }
    assert "week: 2026-W13" in created
    assert "start: 2026-03-23" in created
    assert "end: 2026-03-27" in created
    assert "## Key Accomplishments\n- [x] shipped API\n- [x] reviewed PR" in created
    assert "weekend task" not in created


def test_prepare_weekly_review_reports_existing_file(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    weekly_dir = vault / "04-Periodic" / "Weekly"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    (weekly_dir / "2026-W13.md").write_text("existing", encoding="utf-8")

    service = VaultService(vault)
    result = service.call_tool("prepareWeeklyReview", {"week": "2026-W13"})

    assert result == {"content": [{"type": "text", "text": "Weekly review 2026-W13.md already exists."}]}


def test_prepare_weekly_review_defaults_to_current_week(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_current_week_id", lambda: "2026-W13")

    result = service.call_tool("prepareWeeklyReview", {})

    assert result["content"][0]["text"].startswith("Created 2026-W13.md (2026-03-23 to 2026-03-27)")


def test_generate_roundup_appends_summary_and_uses_modified_tasks(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-26",
        "## Tasks\n- [x] shipped feature\n\n## Notes\n- debugged issue\n\n## End of Day\n### Carry forward to tomorrow\n- [ ] follow up\n",
    )
    _write_task(
        vault,
        "Write tests",
        "---\ncreated: 2026-03-20\nmodified: 2026-03-26\nstatus: in-progress\n---\n",
    )
    meetings_dir = vault / "02-People" / "Meetings"
    meetings_dir.mkdir(parents=True, exist_ok=True)
    (meetings_dir / "2026-03-26 Sprint Planning.md").write_text("meeting", encoding="utf-8")

    service = VaultService(vault)
    result = service.call_tool("generateRoundup", {"date": "2026-03-26"})
    updated = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")

    assert result == {
        "content": [{"type": "text", "text": "Generated roundup for 2026-03-26: 1 completed tasks, 1 meetings, 1 tasks updated, 0 items to carry forward"}]
    }
    assert "# Daily Roundup — Thursday, March 26, 2026" in updated
    assert "## Accomplishments\n- [x] shipped feature" in updated
    assert "## Meetings\n- [2026-03-26 Sprint Planning](../../02-People/Meetings/2026-03-26%20Sprint%20Planning.md)" in updated
    assert "## Tasks Updated\n- [Write tests](../../01-Work/Tasks/Write%20tests.md) (in-progress)" in updated
    assert "## Notes & Context\n- debugged issue" in updated
    assert "## Carry Forward\n*Nothing to carry forward.*" in updated


def test_generate_roundup_replaces_existing_roundup(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    _write_daily_note(
        vault,
        "2026-03-26",
        "## Tasks\n- [x] shipped feature\n\n---\n\n# Daily Roundup — Old\nold content\n",
    )

    service = VaultService(vault)
    service.call_tool("generateRoundup", {"date": "2026-03-26"})
    updated = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")

    assert updated.count("# Daily Roundup") == 1
    assert "old content" not in updated


def test_generate_roundup_reports_missing_daily_note(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")

    service = VaultService(vault)
    result = service.call_tool("generateRoundup", {"date": "2026-03-26"})

    assert result == {
        "content": [{"type": "text", "text": "No daily note found for 2026-03-26. Create one first with prepareDailyNote."}]
    }


def test_triage_inbox_preview_and_move(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    inbox = vault / "00-Inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "Fix bug.md").write_text("Implement bug fix", encoding="utf-8")
    (inbox / "Architecture.md").write_text("type: documentation\nReference doc", encoding="utf-8")

    service = VaultService(vault)
    preview = service.call_tool("triageInbox", {})
    moved = service.call_tool("triageInbox", {"dryRun": False})

    assert "Triage preview (dry run):" in preview["content"][0]["text"]
    assert '"Fix bug.md" → task (01-Work/Tasks/)' in preview["content"][0]["text"]
    assert '"Architecture.md" → documentation (03-Knowledge/Documentation/)' in preview["content"][0]["text"]
    assert "Triage complete:" in moved["content"][0]["text"]
    assert (vault / "01-Work" / "Tasks" / "Fix bug.md").exists()
    assert (vault / "03-Knowledge" / "Documentation" / "Architecture.md").exists()


def test_enrich_note_adds_frontmatter_and_summary(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    doc_dir = vault / "03-Knowledge" / "Documentation"
    doc_dir.mkdir(parents=True, exist_ok=True)
    note = doc_dir / "Runbook.md"
    note.write_text("This is a doc with [[Existing Link]].", encoding="utf-8")

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
    result = service.call_tool("enrichNote", {"filePath": "03-Knowledge/Documentation/Runbook.md"})
    updated = note.read_text(encoding="utf-8")

    assert result == {
        "content": [{"type": "text", "text": 'Enriched "03-Knowledge/Documentation/Runbook.md":\n- Added frontmatter\n- Added Summary section placeholder\n- Found 1 existing links'}]
    }
    assert updated.startswith("---\ncreated: 2026-03-26\nmodified: 2026-03-26")
    assert "## Summary\n\n*Summary to be written.*" in updated


def test_update_topic_index_creates_topic_file(monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    tasks_dir = vault / "01-Work" / "Tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "Managed Identity Task.md").write_text("Managed Identity rollout", encoding="utf-8")
    docs_dir = vault / "03-Knowledge" / "Documentation"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "Identity Guide.md").write_text("Reference for managed identity auth", encoding="utf-8")

    service = VaultService(vault)
    monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
    result = service.call_tool("updateTopicIndex", {"topic": "Managed Identity"})
    topic_file = (vault / "03-Knowledge" / "Topics" / "Managed Identity.md").read_text(encoding="utf-8")

    assert result == {
        "content": [{"type": "text", "text": "Updated topic index: Managed Identity — found 2 related notes across the vault"}]
    }
    assert "created: 2026-03-26" in topic_file
    assert "modified: 2026-03-26" in topic_file
    assert "- [Managed Identity Task](../../01-Work/Tasks/Managed%20Identity%20Task.md)" in topic_file
    assert "- [Identity Guide](../Documentation/Identity%20Guide.md)" in topic_file