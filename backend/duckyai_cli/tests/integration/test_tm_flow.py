"""Integration tests for the Task Manager (TM) agent tool chain.

Simulates the full flow that TM performs: reading a daily note with
Teams highlights, then calling createTask/logTask/logPRReview to
create files and update the daily note.
"""

from pathlib import Path

import pytest

from duckyai_cli.api.vault_service import VaultService


def _setup_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "duckyai.yml").write_text('id: v1\nuser:\n  timezone: "UTC"\n', encoding="utf-8")
    return vault


def _write_daily_note(vault: Path, date: str, content: str) -> Path:
    daily_dir = vault / "04-Periodic" / "Daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_path = daily_dir / f"{date}.md"
    daily_path.write_text(content, encoding="utf-8")
    return daily_path


DAILY_NOTE_WITH_HIGHLIGHTS = """\
---
created: 2026-03-26
type: daily
date: 2026-03-26
tags:
  - daily
---

## Focus Today

## Carried from yesterday

## Tasks
- [ ]

## PRs & Code Reviews
- [ ]

## Notes

## Teams Meeting Highlights
### Sprint Planning
- **Attendees**: [[Alice]], [[Bob]]
- Action: Me to update deployment config for staging by Friday
- Action: Me to review [[Bob]]'s PR #54321 — fix caching layer

## Teams Chat Highlights
### DM with Alice
- Alice asked Me to investigate flaky test in CI pipeline
- Me said "I'll take care of the flaky test investigation"

## End of Day
### Carry forward to tomorrow
- [ ]
"""


class TestTMFlow:
    """Simulate the TM agent's tool calls end to end."""

    @pytest.fixture
    def vault_with_highlights(self, monkeypatch, tmp_path):
        vault = _setup_vault(tmp_path)
        _write_daily_note(vault, "2026-03-26", DAILY_NOTE_WITH_HIGHLIGHTS)
        service = VaultService(vault)
        monkeypatch.setattr(service, "_get_today_date", lambda: "2026-03-26")
        return vault, service

    def test_create_task_and_log_task(self, vault_with_highlights):
        """TM creates a general task from meeting highlights and logs it in the daily note."""
        vault, service = vault_with_highlights

        # Step 1: createTask
        result = service.call_tool("createTask", {
            "title": "Update deployment config for staging",
            "description": "From Sprint Planning — update deployment config for staging by Friday",
            "priority": "P1",
        })
        assert "Created task" in result["content"][0]["text"]

        # Step 2: logTask
        result = service.call_tool("logTask", {
            "title": "Update deployment config for staging",
        })
        assert "Added to ## Tasks" in result["content"][0]["text"]

        # Verify task file exists
        task_path = vault / "01-Work" / "Tasks" / "Update deployment config for staging.md"
        assert task_path.exists()
        task_content = task_path.read_text(encoding="utf-8")
        assert "priority: P1" in task_content
        assert "status: todo" in task_content

        # Verify daily note updated
        daily = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")
        assert "[Update deployment config for staging](../../01-Work/Tasks/Update%20deployment%20config%20for%20staging.md)" in daily

    def test_log_pr_review_from_highlights(self, vault_with_highlights):
        """TM creates a PR review from meeting highlights."""
        vault, service = vault_with_highlights

        result = service.call_tool("logPRReview", {
            "person": "Bob",
            "prNumber": "54321",
            "prUrl": "",
            "description": "Fix caching layer",
            "action": "todo",
        })
        assert "Logged queued for review" in result["content"][0]["text"]

        # Verify PR review file exists
        pr_path = vault / "01-Work" / "PRReviews" / "Review PR 54321 - Fix caching layer.md"
        assert pr_path.exists()
        pr_content = pr_path.read_text(encoding="utf-8")
        assert "[Bob](../../02-People/Contacts/Bob.md)" in pr_content
        assert "status: todo" in pr_content
        # Empty URL should not produce a broken hyperlink
        assert "]()" not in pr_content

        # Verify daily note updated
        daily = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")
        assert "[PR 54321](../../01-Work/PRReviews/Review%20PR%2054321%20-%20Fix%20caching%20layer.md)" in daily

    def test_chat_highlight_task_creation(self, vault_with_highlights):
        """TM creates a task from chat highlights."""
        vault, service = vault_with_highlights

        result = service.call_tool("createTask", {
            "title": "Investigate flaky test in CI pipeline",
            "description": "Alice asked to investigate flaky test in CI pipeline (from Teams chat)",
            "priority": "P2",
        })
        assert "Created task" in result["content"][0]["text"]

        result = service.call_tool("logTask", {
            "title": "Investigate flaky test in CI pipeline",
        })
        assert "Added to ## Tasks" in result["content"][0]["text"]

        task_path = vault / "01-Work" / "Tasks" / "Investigate flaky test in CI pipeline.md"
        assert task_path.exists()

    def test_full_tm_flow_end_to_end(self, vault_with_highlights):
        """Full TM flow: extract all action items and process them sequentially."""
        vault, service = vault_with_highlights

        # --- General task 1 (from meeting) ---
        service.call_tool("createTask", {
            "title": "Update deployment config for staging",
            "description": "Sprint Planning — update deployment config by Friday",
            "priority": "P1",
        })
        service.call_tool("logTask", {"title": "Update deployment config for staging"})

        # --- PR review (from meeting) ---
        service.call_tool("logPRReview", {
            "person": "Bob",
            "prNumber": "54321",
            "prUrl": "",
            "description": "Fix caching layer",
            "action": "todo",
        })

        # --- General task 2 (from chat) ---
        service.call_tool("createTask", {
            "title": "Investigate flaky test in CI pipeline",
            "description": "Alice asked to investigate in Teams chat",
            "priority": "P2",
        })
        service.call_tool("logTask", {"title": "Investigate flaky test in CI pipeline"})

        # --- Verify final state ---
        daily = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")

        # Tasks section has 2 deep-linked entries
        assert daily.count("01-Work/Tasks/") == 2
        assert "[Update deployment config for staging](../../01-Work/Tasks/Update%20deployment%20config%20for%20staging.md)" in daily
        assert "[Investigate flaky test in CI pipeline](../../01-Work/Tasks/Investigate%20flaky%20test%20in%20CI%20pipeline.md)" in daily

        # PRs section has 1 entry
        assert "[PR 54321](../../01-Work/PRReviews/Review%20PR%2054321%20-%20Fix%20caching%20layer.md)" in daily

        # Files exist
        assert (vault / "01-Work" / "Tasks" / "Update deployment config for staging.md").exists()
        assert (vault / "01-Work" / "Tasks" / "Investigate flaky test in CI pipeline.md").exists()
        assert (vault / "01-Work" / "PRReviews" / "Review PR 54321 - Fix caching layer.md").exists()
        # Contact created for Bob
        assert (vault / "02-People" / "Contacts" / "Bob.md").exists()

    def test_idempotent_duplicate_calls(self, vault_with_highlights):
        """Repeated TM calls should be idempotent — no duplicate entries."""
        vault, service = vault_with_highlights

        # First run
        service.call_tool("createTask", {"title": "Same task", "priority": "P2"})
        service.call_tool("logTask", {"title": "Same task"})

        # Second run (simulates TM re-execution)
        dup_create = service.call_tool("createTask", {"title": "Same task", "priority": "P2"})
        dup_log = service.call_tool("logTask", {"title": "Same task"})

        assert "already exists" in dup_create["content"][0]["text"]
        assert "already in daily note" in dup_log["content"][0]["text"].lower()

        daily = (vault / "04-Periodic" / "Daily" / "2026-03-26.md").read_text(encoding="utf-8")
        assert daily.count("[Same task](../../01-Work/Tasks/Same%20task.md)") == 1
