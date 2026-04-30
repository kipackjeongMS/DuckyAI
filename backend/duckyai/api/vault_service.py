"""Native Python implementation of vault tools for the HTTP API."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from zoneinfo import ZoneInfo

from ..config import Config
from ..markdown_utils import md_link


class UnknownVaultToolError(ValueError):
    """Raised when a caller requests a tool that does not exist."""


class VaultToolNotImplementedError(NotImplementedError):
    """Raised when a known tool has not been ported to Python yet."""


@dataclass(frozen=True)
class ToolDefinition:
    """Metadata describing a vault tool exposed through the HTTP API."""

    name: str
    description: str
    implemented: bool = False


class VaultService:
    """Dispatch native vault tool calls for a specific vault root."""

    TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
        ToolDefinition(
            name="getCurrentDate",
            description="Get the current date and time in the user's configured timezone.",
            implemented=True,
        ),
        ToolDefinition(
            name="prepareDailyNote",
            description="Create today's daily note from template and carry forward open items.",
            implemented=True,
        ),
        ToolDefinition(
            name="createTask",
            description="Create a task file in 01-Work/Tasks/.",
            implemented=True,
        ),
        ToolDefinition(
            name="logTask",
            description="Append a task link to today's daily note Tasks section.",
            implemented=True,
        ),
        ToolDefinition(
            name="updateTaskStatus",
            description="Update a task status in YAML frontmatter.",
            implemented=True,
        ),
        ToolDefinition(
            name="archiveTask",
            description="Archive a task by moving it into 05-Archive/.",
            implemented=True,
        ),
        ToolDefinition(
            name="logAction",
            description="Append a completed action to today's daily note Tasks section.",
            implemented=True,
        ),
        ToolDefinition(
            name="logPRReview",
            description="Create or update a PR review record and daily log entry.",
            implemented=True,
        ),
        ToolDefinition(
            name="createMeeting",
            description="Create a meeting note from the meeting template.",
            implemented=True,
        ),
        ToolDefinition(
            name="create1on1",
            description="Create a 1:1 meeting note from the 1:1 template.",
            implemented=True,
        ),
        ToolDefinition(
            name="triageInbox",
            description="Inspect and categorize items under 00-Inbox/.",
            implemented=True,
        ),
        ToolDefinition(
            name="enrichNote",
            description="Enrich a note with structure, links, and frontmatter.",
            implemented=True,
        ),
        ToolDefinition(
            name="updateTopicIndex",
            description="Update topic index files in 03-Knowledge/Topics/.",
            implemented=True,
        ),
        ToolDefinition(
            name="prepareWeeklyReview",
            description="Create the weekly review note.",
            implemented=True,
        ),
        ToolDefinition(
            name="getTeamsChatSyncState",
            description="Read Teams chat sync watermark state.",
            implemented=True,
        ),
        ToolDefinition(
            name="updateTeamsChatSyncState",
            description="Write Teams chat sync watermark state.",
            implemented=True,
        ),
        ToolDefinition(
            name="appendTeamsChatHighlights",
            description="Append Teams chat highlights to today's daily note.",
            implemented=True,
        ),
        ToolDefinition(
            name="getTeamsMeetingSyncState",
            description="Read Teams meeting sync watermark state.",
            implemented=True,
        ),
        ToolDefinition(
            name="updateTeamsMeetingSyncState",
            description="Write Teams meeting sync watermark state.",
            implemented=True,
        ),
        ToolDefinition(
            name="appendTeamsMeetingHighlights",
            description="Append Teams meeting highlights to today's daily note.",
            implemented=True,
        ),
        ToolDefinition(
            name="updateDailyNoteSection",
            description="Update a specific H2 section in today's daily note.",
            implemented=True,
        ),
        ToolDefinition(
            name="convertUtcToLocalDate",
            description="Convert a UTC timestamp to the user's local date and time.",
            implemented=True,
        ),
        ToolDefinition(
            name="generateRoundup",
            description="Generate the daily roundup.",
            implemented=True,
        ),
        ToolDefinition(
            name="gatherOpenItems",
            description="Gather all open tasks, PRs, and carried items from vault. Returns structured JSON.",
            implemented=True,
        ),
        ToolDefinition(
            name="writeDailyNoteFromPlan",
            description="Write today's daily note from a structured plan (JSON with focus_today, carried_items, context_note, at_risk).",
            implemented=True,
        ),
    )

    _TOOL_MAP: dict[str, ToolDefinition] = {tool.name: tool for tool in TOOL_DEFINITIONS}

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path).resolve()
        self.config = Config(vault_path=self.vault_path)
        self.tasks_dir = self.vault_path / "01-Work" / "Tasks"
        self.pr_reviews_dir = self.vault_path / "01-Work" / "PRReviews"
        self.archive_dir = self.vault_path / "05-Archive"
        self.contacts_dir = self.vault_path / "02-People" / "Contacts"
        self.meetings_dir = self.vault_path / "02-People" / "Meetings"
        self.one_on_ones_dir = self.vault_path / "02-People" / "1-on-1s"
        self.inbox_dir = self.vault_path / "00-Inbox"
        self.documentation_dir = self.vault_path / "03-Knowledge" / "Documentation"
        self.topics_dir = self.vault_path / "03-Knowledge" / "Topics"
        self.investigations_dir = self.vault_path / "01-Work" / "Investigations"
        self.projects_dir = self.vault_path / "01-Work" / "Projects"
        self.daily_dir = self.vault_path / "04-Periodic" / "Daily"
        self.weekly_dir = self.vault_path / "04-Periodic" / "Weekly"
        self.state_dir = self.vault_path / ".duckyai" / "state"
        self.templates_dir = self.vault_path / "Templates"
        self.playbook_templates_dir = Path(__file__).resolve().parent.parent / ".playbook" / "templates"

    def list_tools(self) -> list[str]:
        """Return the public tool list in the same order as the MCP server."""
        return [tool.name for tool in self.TOOL_DEFINITIONS]

    def is_known_tool(self, tool_name: str) -> bool:
        return tool_name in self._TOOL_MAP

    def is_native_tool(self, tool_name: str) -> bool:
        tool = self._TOOL_MAP.get(tool_name)
        return bool(tool and tool.implemented)

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch a tool call to the native Python implementation."""
        tool = self._TOOL_MAP.get(tool_name)
        if tool is None:
            raise UnknownVaultToolError(f"Unknown tool: {tool_name}")
        if not tool.implemented:
            raise VaultToolNotImplementedError(f"Tool not yet implemented in Python: {tool_name}")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object")

        handler_name = f"tool_{tool_name}"
        handler = getattr(self, handler_name, None)
        if handler is None:
            raise VaultToolNotImplementedError(f"Missing handler for tool: {tool_name}")
        return handler(arguments)

    def tool_getCurrentDate(self, _: dict[str, Any]) -> dict[str, Any]:
        tz = self._get_timezone_name()
        local_now = self._now_in_user_timezone()
        local_date = local_now.strftime("%Y-%m-%d")
        local_time = local_now.strftime("%H:%M:%S")
        return self._text_response(f"Date: {local_date}\nTime: {local_time}\nTimezone: {tz}")

    def tool_convertUtcToLocalDate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_timestamp = arguments.get("utcTimestamp")
        if not isinstance(raw_timestamp, str):
            return self._text_response(f"Invalid timestamp: {raw_timestamp}")

        try:
            parsed = self._parse_timestamp(raw_timestamp)
        except (TypeError, ValueError):
            return self._text_response(f"Invalid timestamp: {raw_timestamp}")

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        local_dt = parsed.astimezone(self._get_timezone())
        return self._text_response(local_dt.strftime("%Y-%m-%d %H:%M"))

    def tool_prepareDailyNote(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_date = arguments.get("date")
        target_date = self._get_today_date() if raw_date is None else self._coerce_target_date(raw_date)
        target_path = self._daily_note_path(target_date)

        if target_path.exists():
            return self._text_response(f"Daily note for {target_date} already exists.")

        previous_note = self._find_previous_daily_note(target_date)
        carry_forward: list[str] = []
        if previous_note is not None:
            carry_forward = self._extract_carry_forward(previous_note)

        carry_section = "\n".join(carry_forward) if carry_forward else "- (none)"
        note_content = self._build_daily_note_from_template(target_date, carry_section)
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_text(note_content, encoding="utf-8")

        previous_label = previous_note.name if previous_note is not None else "nowhere"
        return self._text_response(
            f"Created {target_date}.md with {len(carry_forward)} carried items from {previous_label}"
        )

    # ------------------------------------------------------------------
    # gatherOpenItems / writeDailyNoteFromPlan — Daily Note Prep agent
    # ------------------------------------------------------------------

    def tool_gatherOpenItems(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Deterministically collect all open tasks, PRs, and carry-forward items."""
        today = self._get_today_date()

        # 1. Open tasks (status != done/cancelled)
        open_tasks: list[dict[str, str]] = []
        if self.tasks_dir.exists():
            for task_file in sorted(self.tasks_dir.iterdir()):
                if not task_file.is_file() or task_file.suffix != ".md":
                    continue
                content = self._read_text(task_file)
                status = self._read_frontmatter_field(content, "status") or "todo"
                if status in ("done", "cancelled"):
                    continue
                priority = self._read_frontmatter_field(content, "priority") or "P2"
                project = self._read_frontmatter_field(content, "project") or ""
                due = self._read_frontmatter_field(content, "due") or ""
                created = self._read_frontmatter_field(content, "created") or ""
                open_tasks.append({
                    "title": task_file.stem,
                    "status": status,
                    "priority": priority,
                    "project": project,
                    "due": due,
                    "created": created,
                })

        # 2. Open PR reviews (status != done/cancelled)
        open_prs: list[dict[str, str]] = []
        if self.pr_reviews_dir.exists():
            for pr_file in sorted(self.pr_reviews_dir.iterdir()):
                if not pr_file.is_file() or pr_file.suffix != ".md":
                    continue
                content = self._read_text(pr_file)
                status = self._read_frontmatter_field(content, "status") or "todo"
                if status in ("done", "cancelled"):
                    continue
                priority = self._read_frontmatter_field(content, "priority") or "P2"
                created = self._read_frontmatter_field(content, "created") or ""
                open_prs.append({
                    "title": pr_file.stem,
                    "status": status,
                    "priority": priority,
                    "created": created,
                })

        # 3. Carry-forward from recent daily notes (look back up to 7 days)
        carried_items: list[str] = []
        prev_note = self._find_previous_daily_note(today)
        if prev_note is not None:
            carried_items = self._extract_carry_forward(prev_note)

        # 4. Uncompleted items from recent notes beyond yesterday (deep lookback)
        deep_items: list[str] = []
        if self.daily_dir.exists():
            recent_notes = sorted(
                (p for p in self.daily_dir.iterdir()
                 if p.is_file() and p.suffix == ".md" and p.name < f"{today}.md"),
                reverse=True,
            )
            # Scan last 7 notes (skip first — already handled by carry_forward)
            for note_path in recent_notes[1:7]:
                try:
                    content = self._read_text(note_path)
                except OSError:
                    continue
                # Extract unchecked items from Focus Today that aren't already carried
                focus_match = re.search(
                    r"## Focus Today\n([\s\S]*?)(?=\n## )", content
                )
                if focus_match:
                    for line in focus_match.group(1).split("\n"):
                        stripped = line.strip()
                        if re.match(r"^- \[ \]", stripped) and stripped not in carried_items and stripped not in deep_items:
                            deep_items.append(stripped)

        result = {
            "date": today,
            "open_tasks": open_tasks,
            "open_prs": open_prs,
            "carried_from_yesterday": carried_items,
            "forgotten_items": deep_items,
        }
        return self._text_response(json.dumps(result, indent=2))

    def tool_writeDailyNoteFromPlan(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Write today's daily note using AI-generated plan (structured JSON)."""
        plan_raw = arguments.get("plan")
        if not plan_raw:
            raise ValueError("Field 'plan' is required (JSON object with focus_today, carried_items, etc.)")

        # Accept plan as dict or JSON string
        if isinstance(plan_raw, str):
            try:
                plan = json.loads(plan_raw)
            except json.JSONDecodeError:
                raise ValueError("Field 'plan' must be valid JSON")
        else:
            plan = plan_raw

        raw_date = arguments.get("date")
        target_date = self._get_today_date() if raw_date is None else self._coerce_target_date(raw_date)
        target_path = self._daily_note_path(target_date)

        if target_path.exists():
            return self._text_response(f"Daily note for {target_date} already exists. Skipped.")

        # Extract plan fields
        focus_today: list[str] = plan.get("focus_today", [])
        carried_items: list[str] = plan.get("carried_items", [])
        context_note: str = plan.get("context_note", "")
        at_risk: list[str] = plan.get("at_risk", [])
        pr_items: list[str] = plan.get("pr_items", [])

        # Build sections
        focus_section = "\n".join(f"- [ ] {item}" for item in focus_today) if focus_today else "- [ ]"
        carry_section = "\n".join(f"- [ ] {item}" if not item.startswith("- ") else item for item in carried_items) if carried_items else "- (none)"
        pr_section = "\n".join(f"- [ ] {item}" for item in pr_items) if pr_items else ""

        # Build note from template
        note_content = self._build_daily_note_from_template(target_date, carry_section)

        # Replace Focus Today section with AI-prioritized items
        note_content = self._replace_or_append_h2_section(
            note_content, section_header="Focus Today", new_content=focus_section
        )

        # Add PR items if provided
        if pr_section:
            note_content = self._replace_or_append_h2_section(
                note_content, section_header="PRs & Code Reviews", new_content=pr_section
            )

        # Add context note and at-risk items to Notes section
        notes_content = ""
        if context_note:
            notes_content += f"> {context_note}\n"
        if at_risk:
            notes_content += "\n**⚠️ At Risk:**\n"
            notes_content += "\n".join(f"- {item}" for item in at_risk)
        if notes_content:
            note_content = self._replace_or_append_h2_section(
                note_content, section_header="Notes", new_content=notes_content.strip()
            )

        self.daily_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_text(note_content, encoding="utf-8")

        return self._text_response(
            f"Created {target_date}.md — Focus: {len(focus_today)} items, "
            f"Carried: {len(carried_items)}, At-risk: {len(at_risk)}"
        )

    @staticmethod
    def _read_frontmatter_field(content: str, field_name: str) -> str | None:
        """Read a single field value from YAML frontmatter."""
        if not content.startswith("---\n"):
            return None
        closing = content.find("\n---\n", 4)
        if closing == -1:
            closing = content.find("\n---", 4)
        if closing == -1:
            return None
        frontmatter = content[4:closing]
        match = re.search(rf"^{re.escape(field_name)}:\s*(.*)$", frontmatter, re.MULTILINE)
        if match:
            val = match.group(1).strip().strip('"').strip("'")
            return val if val else None
        return None

    def tool_createTask(self, arguments: dict[str, Any]) -> dict[str, Any]:
        title = self._sanitize_filename(self._require_non_empty_string(arguments, "title"))
        description = self._optional_string(arguments, "description")
        priority = arguments.get("priority", "P2")
        project = self._optional_string(arguments, "project")
        due = self._optional_string(arguments, "due")

        if priority not in {"P0", "P1", "P2", "P3"}:
            raise ValueError("Field 'priority' must be one of: P0, P1, P2, P3")

        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        duplicate = self._find_existing_task_title(title)
        if duplicate is not None:
            existing_title, match_kind = duplicate
            if match_kind == "case-insensitive":
                return self._text_response(f'Task "{existing_title}" already exists (case-insensitive match). Skipped.')
            return self._text_response(f'Task "{existing_title}" already exists (similar title). Skipped.')

        today = self._get_today_date()
        content = self._load_task_template()
        content = self._normalize_line_endings(content)
        content = content.replace("{{title}}", title)
        content = content.replace("{{date:YYYY-MM-DD}}", today)
        content = self._set_frontmatter_field(content, "priority", priority)

        if project:
            content = self._set_frontmatter_field(content, "project", project)
        if due:
            content = self._set_frontmatter_field(content, "due", due)
        if description:
            content = self._insert_after_heading(content, "Description", description)

        task_path = self.tasks_dir / f"{title}.md"
        self._write_text(task_path, content)
        return self._text_response(f"Created task: {title} ({priority})")

    def tool_updateTaskStatus(self, arguments: dict[str, Any]) -> dict[str, Any]:
        title = self._require_non_empty_string(arguments, "title")
        status = arguments.get("status")
        if status not in {"todo", "in-progress", "blocked", "done", "cancelled"}:
            raise ValueError("Field 'status' must be one of: todo, in-progress, blocked, done, cancelled")

        task_path = self.tasks_dir / f"{title}.md"
        if not task_path.exists():
            return self._text_response(f'Task "{title}" not found.')

        today = self._get_today_date()
        content = self._read_text(task_path)
        content = self._set_frontmatter_field(content, "status", status)
        content = self._set_frontmatter_field(content, "modified", today)
        self._write_text(task_path, content)
        return self._text_response(f'Updated "{title}" status to {status}')

    def tool_archiveTask(self, arguments: dict[str, Any]) -> dict[str, Any]:
        title = self._require_non_empty_string(arguments, "title")
        status = arguments.get("status", "done")
        if status not in {"done", "cancelled"}:
            raise ValueError("Field 'status' must be one of: done, cancelled")

        source_path = self.tasks_dir / f"{title}.md"
        if not source_path.exists():
            return self._text_response(f'Task "{title}" not found in Tasks folder.')

        today = self._get_today_date()
        content = self._read_text(source_path)
        content = self._set_frontmatter_field(content, "status", status)
        content = self._set_frontmatter_field(content, "modified", today)

        destination_path = self.archive_dir / f"{title}.md"
        self._write_text(destination_path, content)
        source_path.unlink()
        return self._text_response(f'Archived "{title}" as {status}')

    def tool_logPRReview(self, arguments: dict[str, Any]) -> dict[str, Any]:
        person = self._require_non_empty_string(arguments, "person")
        pr_number = (self._optional_string(arguments, "prNumber") or "").strip()
        pr_url = self._optional_string(arguments, "prUrl") or ""
        description = self._require_non_empty_string(arguments, "description")
        action = arguments.get("action")
        if action not in {"discovered", "requested", "reviewed", "commented"}:
            raise ValueError("Field 'action' must be one of: discovered, requested, reviewed, commented")

        # Subsection derived from action; explicit override still accepted for "my_prs"
        subsection = arguments.get("subsection")
        if subsection is None:
            subsection = "discovered" if action == "discovered" else "requested"
        if subsection not in {"requested", "discovered", "my_prs"}:
            subsection = "requested"

        today = self._get_today_date()
        daily_path = self._daily_note_path(today)
        if not daily_path.exists():
            return self._text_response(f"Daily note for {today} doesn't exist. Run prepareDailyNote first.")

        # Build PR review title — with or without a PR number
        if pr_number:
            pr_title = self._sanitize_filename(f"Review PR {pr_number} - {description}")
        else:
            pr_title = self._sanitize_filename(description)

        # Display label for the PR in notes
        pr_display = f"PR {pr_number}" if pr_number else description

        # "my_prs" = user is the author; skip PR file creation entirely
        # so the PR Review agent never picks these up.
        is_my_pr = subsection == "my_prs"

        final_pr_title = pr_title
        if not is_my_pr:
            self.pr_reviews_dir.mkdir(parents=True, exist_ok=True)
            existing_pr_title = self._find_existing_pr_review_title(pr_number) if pr_number else None
            final_pr_title = existing_pr_title or pr_title
            final_pr_path = self.pr_reviews_dir / f"{final_pr_title}.md"

            if existing_pr_title is None and not final_pr_path.exists():
                status = "done" if action == "reviewed" else "in-progress" if action == "commented" else "todo"
                if pr_url:
                    pr_link = f"[{pr_display}]({pr_url})"
                else:
                    pr_link = pr_display
                pr_note_source = f"01-Work/PRReviews/{final_pr_title}.md"
                person_link = md_link(person, f"02-People/Contacts/{person}.md", pr_note_source)
                pr_note = (
                    f"---\ncreated: {today}\ntype: task\nstatus: {status}\npriority: P2\ntags:\n  - pr-review\n---\n\n"
                    "## PR Details\n\n"
                    f"- **Author**: {person_link}\n"
                    f"- **PR**: {pr_link}\n"
                    f"- **Description**: {description}\n"
                    f"- **Action**: {self._pr_action_label(action)}\n"
                )
                self._write_text(final_pr_path, pr_note)

        content = self._read_text(daily_path)
        content_lower = content.lower()

        # Dedup marker: use PR number if available, otherwise lowercase description
        pr_marker = f"pr {pr_number.lower()}" if pr_number else description.lower()

        daily_source = f"04-Periodic/Daily/{today}.md"
        if pr_marker not in content_lower:
            if action in {"discovered", "requested"}:
                if is_my_pr:
                    # My PRs: link directly to ADO URL (no PR file exists)
                    if pr_url:
                        pr_entry_link = f"[{pr_display}]({pr_url})"
                    else:
                        pr_entry_link = pr_display
                else:
                    pr_entry_link = md_link(pr_display, f"01-Work/PRReviews/{final_pr_title}.md", daily_source)
                pending_entry = f"- [ ] {pr_entry_link} - {description}"

                # Determine target H3 subsection
                target_h3 = (
                    "My PRs" if subsection == "my_prs"
                    else "Requested" if subsection == "requested"
                    else "Discovered"
                )

                # Ensure subsections exist under ## PRs & Code Reviews
                content = self._ensure_pr_subsections(content)

                content = self._replace_or_append_section(
                    content,
                    section_header=target_h3,
                    new_content=pending_entry,
                    level=3,
                    append_mode=True,
                    empty_markers={"- [ ]", "", "-"},
                    append_if_missing=True,
                    parent_section="PRs & Code Reviews",
                )
            else:
                action_text = "Reviewed" if action == "reviewed" else "Commented on"
                person_md = md_link(person, f"02-People/Contacts/{person}.md", daily_source)
                pr_review_md = md_link(pr_display, f"01-Work/PRReviews/{final_pr_title}.md", daily_source)
                log_entry = (
                    f"- [x] {action_text} {person_md}'s PR - {pr_review_md} - {description}"
                )
                # Completed reviews go under the parent H2 (no subsection needed)
                content = self._append_to_h2_section(
                    content,
                    section_header="PRs & Code Reviews",
                    entry=log_entry,
                    empty_markers={"- [ ]", "- [x]", "", "-"},
                    append_if_missing=False,
                )
        else:
            # PR marker already exists — check if we need to move between subsections
            if action in {"discovered", "requested"} and subsection == "requested":
                content = self._promote_pr_to_requested(content, pr_marker)

        self._write_text(daily_path, content)
        contact_ref = f"[{pr_display}]({pr_url})" if pr_url else pr_display
        created_contact = self._ensure_contact_exists(person, f"First referenced in {contact_ref} - {description}")
        contact_msg = f" (created contact for {person})" if created_contact else ""
        action_label = "tracked (my PR)" if is_my_pr else "queued for review" if action in {"discovered", "requested"} else action
        return self._text_response(f"Logged {action_label} on {person}'s PR review: {description}{contact_msg}")

    def tool_createMeeting(self, arguments: dict[str, Any]) -> dict[str, Any]:
        title = self._require_non_empty_string(arguments, "title")
        raw_date = arguments.get("date")
        meeting_date = self._get_today_date() if raw_date is None else self._coerce_target_date(raw_date)
        time = self._optional_string(arguments, "time")
        attendees = self._optional_string_list(arguments, "attendees")
        project = self._optional_string(arguments, "project")

        filename = f"{meeting_date} {title}.md"
        meeting_path = self.meetings_dir / filename
        if meeting_path.exists():
            return self._text_response(f'Meeting note "{filename}" already exists.')

        template = self._load_named_template(
            "Meeting",
            (
                "---\ncreated: {{date:YYYY-MM-DD}}\ntype: meeting\ndate: {{date:YYYY-MM-DD}}\ntime: \nattendees: []\nproject: \n"
                "tags:\n  - meeting\n---\n\n# {{title}}\n\n## Attendees\n- \n\n## Agenda\n1. \n\n## Discussion\n\n\n## Decisions\n- \n\n## Action Items\n- [ ] @: \n\n## Next Meeting\n"
            ),
        )
        template = self._normalize_line_endings(template)
        template = template.replace("{{title}}", title)
        template = template.replace("{{date:YYYY-MM-DD}}", meeting_date)

        if time:
            template = self._set_frontmatter_field(template, "time", time)
        if attendees:
            attendee_names = ", ".join(f'"{attendee}"' for attendee in attendees)
            template = self._set_frontmatter_field(template, "attendees", f"[{attendee_names}]")
            meeting_source = f"02-People/Meetings/{filename}"
            attendee_list = "\n".join(
                f"- {md_link(attendee, f'02-People/Contacts/{attendee}.md', meeting_source)}"
                for attendee in attendees
            )
            template = self._replace_or_append_h2_section(template, "Attendees", attendee_list)
        if project:
            template = self._set_frontmatter_field(template, "project", project)

        self._write_text(meeting_path, template)

        created_contacts: list[str] = []
        for attendee in attendees or []:
            if self._ensure_contact_exists(attendee, f"First met in meeting: {title}"):
                created_contacts.append(attendee)
        contact_msg = f" (created contacts: {', '.join(created_contacts)})" if created_contacts else ""
        return self._text_response(f"Created meeting: {filename}{contact_msg}")

    def tool_create1on1(self, arguments: dict[str, Any]) -> dict[str, Any]:
        person = self._require_non_empty_string(arguments, "person")
        raw_date = arguments.get("date")
        meeting_date = self._get_today_date() if raw_date is None else self._coerce_target_date(raw_date)
        filename = f"{meeting_date} {person}.md"
        file_path = self.one_on_ones_dir / filename

        if file_path.exists():
            return self._text_response(f'1:1 note "{filename}" already exists.')

        template = self._load_named_template(
            "1-on-1",
            (
                "---\ncreated: {{date:YYYY-MM-DD}}\ntype: 1-on-1\nperson: \ndate: {{date:YYYY-MM-DD}}\ntags:\n  - 1-on-1\n---\n\n"
                "# 1:1 - {{date:YYYY-MM-DD}}\n\n## Their Updates\n- \n\n## My Updates\n- \n\n## Discussion Topics\n- \n\n"
                "## Action Items\n- [ ] Them: \n- [ ] Me: \n\n## Notes\n\n\n## Follow-up\n- \n"
            ),
        )
        template = self._normalize_line_endings(template)
        template = template.replace("{{date:YYYY-MM-DD}}", meeting_date)
        template = self._set_frontmatter_field(template, "person", person)
        oneonone_source = f"02-People/1-on-1s/{filename}"
        person_md = md_link(person, f"02-People/Contacts/{person}.md", oneonone_source)
        template = re.sub(r"^# 1:1 - .*?$", f"# 1:1 with {person_md} - {meeting_date}", template, count=1, flags=re.MULTILINE)

        self._write_text(file_path, template)
        created_contact = self._ensure_contact_exists(person, "1:1 partner")
        contact_msg = f" (created contact for {person})" if created_contact else ""
        return self._text_response(f"Created 1:1: {filename}{contact_msg}")

    def tool_getTeamsChatSyncState(self, _: dict[str, Any]) -> dict[str, Any]:
        state = self._read_sync_state(
            self.state_dir / "tcs-last-sync.json",
            {"lastSynced": None, "processedThreads": [], "syncCount": 0},
        )
        return self._text_response(
            json.dumps(
                {
                    "lastSynced": state.get("lastSynced") or None,
                    "processedThreads": state.get("processedThreads") or [],
                    "syncCount": state.get("syncCount") or 0,
                }
            )
        )

    def tool_updateTeamsChatSyncState(self, arguments: dict[str, Any]) -> dict[str, Any]:
        last_synced = self._require_non_empty_string(arguments, "lastSynced")
        processed_thread_ids = self._optional_string_list(arguments, "processedThreadIds") or []
        processed_dates = self._optional_string_list(arguments, "processedDates") or []

        state_file = self.state_dir / "tcs-last-sync.json"
        existing = self._read_sync_state(state_file, {"processedThreads": [], "syncCount": 0})
        unique_threads = self._merge_unique_recent(processed_thread_ids, existing.get("processedThreads") or [], limit=500)
        pending_dates = self._verify_highlight_dates(
            existing.get("pendingHighlightDates") or [],
            processed_dates,
            section_header="Teams Chat Highlights",
        )

        new_state = {
            "lastSynced": last_synced,
            "previousSynced": existing.get("lastSynced") or None,
            "processedThreads": unique_threads,
            "syncCount": int(existing.get("syncCount") or 0) + 1,
            "updatedAt": self._utc_now_iso(),
            "pendingHighlightDates": pending_dates[-14:],
        }
        self._write_sync_state(state_file, new_state)

        pending_msg = (
            f" ⚠️ {len(pending_dates)} date(s) missing chat highlights: {', '.join(pending_dates)}"
            if pending_dates
            else ""
        )
        return self._text_response(
            f"✅ Sync state updated. Last synced: {last_synced} (sync #{new_state['syncCount']}){pending_msg}"
        )

    def tool_appendTeamsChatHighlights(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_date = arguments.get("date")
        target_date = self._get_today_date() if raw_date is None else self._coerce_target_date(raw_date)
        highlights = arguments.get("highlights")
        if not isinstance(highlights, str):
            raise ValueError("Field 'highlights' must be a string")
        people = self._optional_string_list(arguments, "people") or []
        person_notes = self._optional_person_notes(arguments, "personNotes") or []

        self._ensure_daily_note(target_date)
        daily_path = self._daily_note_path(target_date)
        content = self._read_text(daily_path)
        content = self._merge_highlight_section(
            content,
            section_header="Teams Chat Highlights",
            incoming=highlights,
        )
        self._write_text(daily_path, content)

        created_contacts, updated_contacts = self._update_contact_mentions(
            target_date=target_date,
            context_template="Referenced in Teams chat on {date}",
            people=people,
            person_notes=person_notes,
        )
        stats = self._build_stats_message(
            [
                f"Updated daily note {target_date}",
                f"created contacts: {', '.join(created_contacts)}" if created_contacts else None,
                f"updated notes for: {', '.join(updated_contacts)}" if updated_contacts else None,
            ]
        )
        return self._text_response(f"✅ {stats}")

    def tool_getTeamsMeetingSyncState(self, _: dict[str, Any]) -> dict[str, Any]:
        state = self._read_sync_state(
            self.state_dir / "tms-last-sync.json",
            {"lastSynced": None, "processedMeetings": [], "syncCount": 0},
        )
        return self._text_response(
            json.dumps(
                {
                    "lastSynced": state.get("lastSynced") or None,
                    "processedMeetings": state.get("processedMeetings") or [],
                    "syncCount": state.get("syncCount") or 0,
                }
            )
        )

    def tool_updateTeamsMeetingSyncState(self, arguments: dict[str, Any]) -> dict[str, Any]:
        last_synced = self._require_non_empty_string(arguments, "lastSynced")
        processed_meeting_ids = self._optional_string_list(arguments, "processedMeetingIds") or []
        processed_dates = self._optional_string_list(arguments, "processedDates") or []

        state_file = self.state_dir / "tms-last-sync.json"
        existing = self._read_sync_state(state_file, {"processedMeetings": [], "syncCount": 0})
        unique_meetings = self._merge_unique_recent(processed_meeting_ids, existing.get("processedMeetings") or [], limit=500)
        pending_dates = self._verify_highlight_dates(
            existing.get("pendingHighlightDates") or [],
            processed_dates,
            section_header="Teams Meeting Highlights",
        )

        new_state = {
            "lastSynced": last_synced,
            "previousSynced": existing.get("lastSynced") or None,
            "processedMeetings": unique_meetings,
            "syncCount": int(existing.get("syncCount") or 0) + 1,
            "updatedAt": self._utc_now_iso(),
            "pendingHighlightDates": pending_dates[-14:],
        }
        self._write_sync_state(state_file, new_state)

        pending_msg = (
            f" ⚠️ {len(pending_dates)} date(s) missing meeting highlights: {', '.join(pending_dates)}"
            if pending_dates
            else ""
        )
        return self._text_response(
            f"✅ Meeting sync state updated. Last synced: {last_synced} (sync #{new_state['syncCount']}){pending_msg}"
        )

    def tool_appendTeamsMeetingHighlights(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_date = arguments.get("date")
        target_date = self._get_today_date() if raw_date is None else self._coerce_target_date(raw_date)
        highlights = arguments.get("highlights")
        if not isinstance(highlights, str):
            raise ValueError("Field 'highlights' must be a string")
        people = self._optional_string_list(arguments, "people") or []
        person_notes = self._optional_person_notes(arguments, "personNotes") or []

        self._ensure_daily_note(target_date)
        daily_path = self._daily_note_path(target_date)
        content = self._read_text(daily_path)
        content = self._merge_highlight_section(
            content,
            section_header="Teams Meeting Highlights",
            incoming=highlights,
        )
        self._write_text(daily_path, content)

        created_contacts, updated_contacts = self._update_contact_mentions(
            target_date=target_date,
            context_template="Attended meeting on {date}",
            people=people,
            person_notes=person_notes,
        )
        stats = self._build_stats_message(
            [
                f"Updated daily note {target_date} with meeting highlights",
                f"created contacts: {', '.join(created_contacts)}" if created_contacts else None,
                f"updated notes for: {', '.join(updated_contacts)}" if updated_contacts else None,
            ]
        )
        return self._text_response(f"✅ {stats}")

    def tool_prepareWeeklyReview(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_week = arguments.get("week")
        target_week = self._get_current_week_id() if raw_week is None else self._require_non_empty_string(arguments, "week")

        filename = f"{target_week}.md"
        file_path = self.weekly_dir / filename
        if file_path.exists():
            return self._text_response(f"Weekly review {filename} already exists.")

        monday_str, friday_str = self._week_bounds(target_week)
        completed_tasks = self._collect_completed_tasks(monday_str, friday_str)

        template = self._load_named_template(
            "Weekly Review",
            (
                "---\ncreated: {{date:YYYY-MM-DD}}\ntype: weekly\nweek: {{date:YYYY-[W]ww}}\nstart: {{date:YYYY-MM-DD|monday}}\n"
                "end: {{date:YYYY-MM-DD|friday}}\ntags:\n  - weekly\n---\n\n# Week {{date:ww, YYYY}}\n\n## Sprint Goals\n- [ ] \n\n"
                "## Key Accomplishments\n- \n\n## PRs Shipped\n- \n\n## Code Reviews Done\n- \n\n## Tasks Completed\n```dataview\nTASK\n"
                'FROM "01-Work/Tasks"\nWHERE completed >= this.start AND completed <= this.end\n```\n\n## Meetings & 1:1s\n```dataview\nLIST\n'
                'FROM "02-People"\nWHERE date >= this.start AND date <= this.end\nSORT date ASC\n```\n\n## Incidents / On-Call\n- \n\n'
                "## Blockers / Tech Debt\n- \n\n## Technical Learnings\n- \n\n## Next Week\n- [ ] "
            ),
        )
        template = self._normalize_line_endings(template)
        template = self._process_template(template, {"date": monday_str})
        template = self._set_frontmatter_field(template, "week", target_week)
        template = self._set_frontmatter_field(template, "start", monday_str)
        template = self._set_frontmatter_field(template, "end", friday_str)

        if completed_tasks:
            template = self._replace_or_append_h2_section(template, "Key Accomplishments", "\n".join(completed_tasks))

        self._write_text(file_path, template)
        return self._text_response(
            f"Created {filename} ({monday_str} to {friday_str}) with {len(completed_tasks)} completed tasks aggregated"
        )

    def tool_generateRoundup(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_date = arguments.get("date")
        target_date = self._get_today_date() if raw_date is None else self._coerce_target_date(raw_date)
        daily_path = self._daily_note_path(target_date)
        if not daily_path.exists():
            return self._text_response(f"No daily note found for {target_date}. Create one first with prepareDailyNote.")

        daily_content = self._read_text(daily_path)
        completed_tasks: list[str] = []
        meetings: list[str] = []
        notes: list[str] = []
        carry_forward: list[str] = []

        current_section = ""
        for line in daily_content.split("\n"):
            if re.match(r"^##\s", line):
                heading = re.sub(r"^#+\s*", "", line).lower()
                if "completed" in heading or "done" in heading or "task" in heading:
                    current_section = "completed"
                elif "meeting" in heading:
                    current_section = "meetings"
                elif "note" in heading or "log" in heading:
                    current_section = "notes"
                elif "carry" in heading or "tomorrow" in heading:
                    current_section = "carry"
                else:
                    current_section = ""
                continue

            if line.strip().startswith("-") and current_section:
                item = line.strip()
                if current_section == "completed":
                    if "[x]" in item:
                        completed_tasks.append(item)
                elif current_section == "meetings":
                    meetings.append(item)
                elif current_section == "notes":
                    notes.append(item)
                elif current_section == "carry":
                    carry_forward.append(item)

        tasks_modified_today: list[str] = []
        if self.tasks_dir.exists():
            for task_path in sorted(self.tasks_dir.glob("*.md")):
                try:
                    task_content = self._read_text(task_path)
                except OSError:
                    continue
                if f"modified: {target_date}" in task_content:
                    status_match = re.search(r"^status:\s*(.+)$", task_content, flags=re.MULTILINE)
                    status = status_match.group(1).strip() if status_match else "unknown"
                    daily_note_source = f"04-Periodic/Daily/{target_date}.md"
                    task_link = md_link(task_path.stem, f"01-Work/Tasks/{task_path.name}", daily_note_source)
                    tasks_modified_today.append(f"- {task_link} ({status})")

        meetings_today = []
        daily_roundup_source = f"04-Periodic/Daily/{target_date}.md"
        if self.meetings_dir.exists():
            meetings_today = [
                f"- {md_link(path.stem, f'02-People/Meetings/{path.name}', daily_roundup_source)}"
                for path in sorted(self.meetings_dir.glob(f"{target_date}*.md"))
            ]

        heading = self._format_date_heading(target_date)
        sections = [
            f"# Daily Roundup — {heading}",
            "",
            "## Accomplishments",
            "\n".join(completed_tasks) if completed_tasks else "*None logged yet.*",
            "",
            "## Meetings",
            "\n".join(meetings_today) if meetings_today else "\n".join(meetings) if meetings else "*No meetings.*",
            "",
            "## Tasks Updated",
            "\n".join(tasks_modified_today) if tasks_modified_today else "*No task files modified.*",
            "",
            "## Notes & Context",
            "\n".join(notes) if notes else "*No notes logged.*",
            "",
            "## Carry Forward",
            "\n".join(carry_forward) if carry_forward else "*Nothing to carry forward.*",
        ]
        roundup_content = "\n".join(sections) + "\n"

        separator = "\n---\n\n"
        if "# Daily Roundup" in daily_content:
            updated = re.sub(r"# Daily Roundup[\s\S]*$", roundup_content, daily_content)
            self._write_text(daily_path, updated)
        else:
            self._write_text(daily_path, daily_content.rstrip() + separator + roundup_content)

        stats = ", ".join(
            [
                f"{len(completed_tasks)} completed tasks",
                f"{len(meetings_today) or len(meetings)} meetings",
                f"{len(tasks_modified_today)} tasks updated",
                f"{len(carry_forward)} items to carry forward",
            ]
        )
        return self._text_response(f"Generated roundup for {target_date}: {stats}")

    def tool_triageInbox(self, arguments: dict[str, Any]) -> dict[str, Any]:
        dry_run = arguments.get("dryRun", True)
        if not isinstance(dry_run, bool):
            raise ValueError("Field 'dryRun' must be a boolean")

        if not self.inbox_dir.exists():
            return self._text_response("00-Inbox/ directory not found or empty.")

        files = sorted(path for path in self.inbox_dir.iterdir() if path.is_file() and path.suffix == ".md")
        if not files:
            return self._text_response("Inbox is empty — nothing to triage.")

        results: list[str] = []
        for file_path in files:
            content = self._read_text(file_path)
            destination, category = self._triage_destination(content)
            relative_destination = destination.relative_to(self.vault_path).as_posix()
            if dry_run:
                results.append(f'📋 "{file_path.name}" → {category} ({relative_destination}/)')
            else:
                destination.mkdir(parents=True, exist_ok=True)
                file_path.rename(destination / file_path.name)
                results.append(f'✅ Moved "{file_path.name}" → {category} ({relative_destination}/)')

        header = "Triage preview (dry run):" if dry_run else "Triage complete:"
        return self._text_response(f"{header}\n" + "\n".join(results))

    def tool_enrichNote(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path_arg = self._require_non_empty_string(arguments, "filePath")
        full_path = self.vault_path / Path(file_path_arg)
        if not full_path.exists():
            return self._text_response(f"File not found: {file_path_arg}")

        content = self._read_text(full_path)
        today = self._get_today_date()
        changes: list[str] = []

        if not content.startswith("---"):
            frontmatter = (
                f"---\ncreated: {today}\nmodified: {today}\ntype: documentation\ncategory: reference\ntags:\n  - enriched\n---\n\n"
            )
            content = frontmatter + content
            changes.append("Added frontmatter")
        else:
            if re.search(r"^modified:\s*.+$", content, flags=re.MULTILINE):
                content = re.sub(r"^(modified:\s*).+$", rf"\g<1>{today}", content, count=1, flags=re.MULTILINE)
            if "enriched" not in content:
                content = re.sub(r"^(tags:\s*\n)", r"\1  - enriched\n", content, count=1, flags=re.MULTILINE)
            changes.append("Updated modified date and tags")

        if not re.search(r"^## Summary\s*$", content, flags=re.MULTILINE):
            end_of_frontmatter = content.find("---", 4)
            if end_of_frontmatter != -1:
                insert_pos = content.find("\n", end_of_frontmatter) + 1
                content = content[:insert_pos] + "\n## Summary\n\n*Summary to be written.*\n\n" + content[insert_pos:]
                changes.append("Added Summary section placeholder")

        existing_links = re.findall(r"\[\[.+?\]\]|\[[^\]]+\]\([^)]+\)", content)
        changes.append(f"Found {len(existing_links)} existing links")
        self._write_text(full_path, content)
        return self._text_response(f'Enriched "{file_path_arg}":\n' + "\n".join(f"- {change}" for change in changes))

    def tool_updateTopicIndex(self, arguments: dict[str, Any]) -> dict[str, Any]:
        topic = self._require_non_empty_string(arguments, "topic")
        topic_file = self.topics_dir / f"{topic}.md"
        today = self._get_today_date()
        self.topics_dir.mkdir(parents=True, exist_ok=True)

        dirs_to_scan = [
            (self.tasks_dir, "01-Work/Tasks"),
            (self.investigations_dir, "01-Work/Investigations"),
            (self.projects_dir, "01-Work/Projects"),
            (self.meetings_dir, "02-People/Meetings"),
            (self.documentation_dir, "03-Knowledge/Documentation"),
            (self.daily_dir, "04-Periodic/Daily"),
        ]

        related_notes: list[tuple[str, str]] = []
        topic_lower = topic.lower()
        for directory, relative_dir in dirs_to_scan:
            if not directory.exists():
                continue
            for file_path in sorted(directory.glob("*.md")):
                try:
                    file_content = self._read_text(file_path)
                except OSError:
                    continue
                if topic_lower in file_content.lower():
                    match_line = next((line.strip() for line in file_content.split("\n") if topic_lower in line.lower()), "")
                    related_notes.append((f"{relative_dir}/{file_path.stem}", match_line[:100]))

        topic_source = f"03-Knowledge/Topics/{topic}.md"
        refs_section = (
            "\n".join(
                f"- {md_link(file_ref.split('/')[-1], file_ref + '.md', topic_source)}" + (f" — {context}" if context else "")
                for file_ref, context in related_notes
            )
            if related_notes
            else "*No related notes found yet.*"
        )

        if topic_file.exists():
            new_content = self._read_text(topic_file)
            if re.search(r"^## Related Notes\s*$", new_content, flags=re.MULTILINE):
                new_content = re.sub(
                    r"^## Related Notes[\s\S]*?(?=\n## |\n---|\Z)",
                    f"## Related Notes\n\n{refs_section}\n",
                    new_content,
                    count=1,
                    flags=re.MULTILINE,
                )
            else:
                new_content = new_content.rstrip() + f"\n\n## Related Notes\n\n{refs_section}\n"
            new_content = self._set_frontmatter_field(new_content, "modified", today)
        else:
            tag = re.sub(r"\s+", "-", topic_lower)
            new_content = (
                f"---\ncreated: {today}\nmodified: {today}\ntype: documentation\ncategory: reference\ntags:\n  - topic\n  - {tag}\n---\n\n"
                f"## {topic}\n\n*Topic overview to be written.*\n\n## Related Notes\n\n{refs_section}\n"
            )

        self._write_text(topic_file, new_content)
        return self._text_response(f"Updated topic index: {topic} — found {len(related_notes)} related notes across the vault")

    def tool_logAction(self, arguments: dict[str, Any]) -> dict[str, Any]:
        action = arguments.get("action")
        add_to_carry_forward = arguments.get("addToCarryForward")
        if not isinstance(action, str) or not action.strip():
            raise ValueError("Field 'action' must be a non-empty string")
        if add_to_carry_forward is not None and not isinstance(add_to_carry_forward, str):
            raise ValueError("Field 'addToCarryForward' must be a string when provided")

        today = self._get_today_date()
        daily_path = self._daily_note_path(today)
        if not daily_path.exists():
            return self._text_response(f"Daily note for {today} doesn't exist. Run prepareDailyNote first.")

        content = self._read_text(daily_path)
        log_entry = f"- [x] {action.strip()}"
        content = self._append_to_h2_section(
            content,
            section_header="Tasks",
            entry=log_entry,
            empty_markers={"- [ ]", "- [x]", "", "-"},
            append_if_missing=True,
        )

        carry_msg = ""
        if add_to_carry_forward and add_to_carry_forward.strip():
            carry_entry = f"- [ ] {add_to_carry_forward.strip()}"
            content = self._replace_or_append_h3_section(
                content,
                section_header="Carry forward to tomorrow",
                new_content=carry_entry,
                append_mode=True,
                empty_markers={"- [ ]", "", "-"},
                parent_section="End of Day",
            )
            carry_msg = " + added follow-up to carry forward"

        self._write_text(daily_path, content)
        return self._text_response(f"Logged: {action.strip()}{carry_msg}")

    def tool_logTask(self, arguments: dict[str, Any]) -> dict[str, Any]:
        title = arguments.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Field 'title' must be a non-empty string")

        normalized_title = title.strip()
        today = self._get_today_date()
        daily_path = self._daily_note_path(today)
        if not daily_path.exists():
            return self._text_response(f"Daily note for {today} doesn't exist. Run prepareDailyNote first.")

        content = self._read_text(daily_path)
        marker_plain = f"01-work/tasks/{normalized_title.lower()}"
        marker_encoded = marker_plain.replace(" ", "%20")
        content_lower = content.lower()
        if marker_plain in content_lower or marker_encoded in content_lower:
            return self._text_response(f"Task \"{normalized_title}\" already in daily note. Skipped.")

        daily_source = f"04-Periodic/Daily/{today}.md"
        task_md = md_link(normalized_title, f"01-Work/Tasks/{normalized_title}.md", daily_source)
        log_entry = f"- [ ] {task_md}"
        if not self._has_h2_section(content, "Tasks"):
            return self._text_response('"## Tasks" section not found in daily note. Cannot add task.')

        content = self._append_to_h2_section(
            content,
            section_header="Tasks",
            entry=log_entry,
            empty_markers={"- [ ]", "", "-"},
            append_if_missing=False,
        )
        self._write_text(daily_path, content)
        return self._text_response(f"Added to ## Tasks: {normalized_title}")

    def tool_updateDailyNoteSection(self, arguments: dict[str, Any]) -> dict[str, Any]:
        date = arguments.get("date")
        section_header = arguments.get("sectionHeader")
        new_content = arguments.get("content")
        if not isinstance(date, str) or not date.strip():
            raise ValueError("Field 'date' must be a non-empty string")
        if not isinstance(section_header, str) or not section_header.strip():
            raise ValueError("Field 'sectionHeader' must be a non-empty string")
        if not isinstance(new_content, str):
            raise ValueError("Field 'content' must be a string")

        target_date = self._coerce_target_date(date)
        self._ensure_daily_note(target_date)
        daily_path = self._daily_note_path(target_date)
        file_content = self._read_text(daily_path)
        file_content = self._replace_or_append_h2_section(
            file_content,
            section_header=section_header.strip(),
            new_content=new_content,
        )
        self._write_text(daily_path, file_content)
        return self._text_response(f"✅ Updated section '## {section_header.strip()}' in {target_date}.md")

    def _get_timezone_name(self) -> str:
        configured = self.config.get("user.timezone") or self.config.get("timezone")
        if configured:
            windows_tz_map = getattr(self.config, "_WINDOWS_TZ_MAP", {})
            return windows_tz_map.get(configured, configured)
        return self.config.get_user_timezone()

    def _get_timezone(self):
        tz_name = self._get_timezone_name()
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return timezone.utc

    def _now_in_user_timezone(self) -> datetime:
        return datetime.now(self._get_timezone())

    def _get_today_date(self) -> str:
        return self._now_in_user_timezone().strftime("%Y-%m-%d")

    @staticmethod
    def _coerce_target_date(raw_date: Any) -> str:
        if not isinstance(raw_date, str):
            raise ValueError("Field 'date' must be a string when provided")
        return raw_date.strip()

    def _daily_note_path(self, target_date: str) -> Path:
        return self.daily_dir / f"{target_date}.md"

    def _ensure_daily_note(self, target_date: str) -> None:
        daily_path = self._daily_note_path(target_date)
        if daily_path.exists():
            return
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        content = self._build_daily_note_from_template(target_date, "- (none)")
        self._write_text(daily_path, content)

    def _find_previous_daily_note(self, before_date: str) -> Path | None:
        if not self.daily_dir.exists():
            return None
        candidates = sorted(
            (path for path in self.daily_dir.iterdir() if path.is_file() and path.suffix == ".md" and path.name < f"{before_date}.md"),
            reverse=True,
        )
        return candidates[0] if candidates else None

    def _extract_carry_forward(self, file_path: Path) -> list[str]:
        try:
            content = self._read_text(file_path)
        except OSError:
            return []

        uncompleted: list[str] = []
        focus_match = re.search(r"## Focus Today\n([\s\S]*?)(?=\n## Carried from yesterday|\n## Tasks|$)", content)
        if focus_match:
            for line in focus_match.group(1).split("\n"):
                if re.match(r"^- \[ \]", line):
                    uncompleted.append(line)

        carry_match = re.search(r"### Carry forward to tomorrow\n([\s\S]*?)(?=\n##|$)", content)
        if carry_match:
            for line in carry_match.group(1).strip().split("\n"):
                if re.match(r"^- \[ \]", line) and line not in uncompleted:
                    uncompleted.append(line)
        return uncompleted

    def _build_daily_note_from_template(self, target_date: str, carry_section: str) -> str:
        day_heading = self._format_date_heading(target_date)
        template = self._load_daily_note_template()
        template = self._normalize_line_endings(template)
        template = template.replace("{{date}}", target_date)
        template = template.replace("{{dayHeading}}", day_heading)
        template = template.replace("{{date:YYYY-MM-DD}}", target_date)
        template = template.replace("{{date:dddd, MMMM D, YYYY}}", day_heading)
        return self._replace_or_append_h2_section(
            template,
            section_header="Carried from yesterday",
            new_content=carry_section,
        )

    def _load_daily_note_template(self) -> str:
        candidate_paths = (
            self.playbook_templates_dir / "Daily Note Template.md",
            self.templates_dir / "Daily Note.md",
        )
        for candidate in candidate_paths:
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")
        return (
            '---\ncreated: "{{date}}"\ntype: daily\ndate: "{{date}}"\ntags:\n  - daily\n---\n\n'
            '# {{dayHeading}}\n\n## Focus Today\n- [ ]\n\n## Carried from yesterday\n- (none)\n\n## Tasks\n- [ ]\n\n'
            '## PRs & Code Reviews\n- [ ]\n\n## Notes\n\n\n## Teams Meeting Highlights\n\n## Teams Chat Highlights\n\n'
            '## End of Day\n### What went well?\n-\n\n### What could improve?\n-\n\n### Carry forward to tomorrow\n- [ ]\n'
        )

    def _load_task_template(self) -> str:
        template_path = self.templates_dir / "Task.md"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return (
            '---\ncreated: {{date:YYYY-MM-DD}}\nmodified: {{date:YYYY-MM-DD}}\ntype: task\nstatus: todo\n'
            'priority: P2\ndue: \nscheduled: \nproject: \ntags:\n  - task\n---\n\n'
            '# {{title}}\n\n## Description\n\n\n## Acceptance Criteria\n- [ ] \n\n## Notes\n\n\n## Related\n- \n'
        )

    def _load_named_template(self, template_name: str, fallback: str) -> str:
        template_path = self.templates_dir / f"{template_name}.md"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return fallback

    def _process_template(self, template: str, variables: dict[str, str]) -> str:
        result = template
        if "title" in variables:
            result = result.replace("{{title}}", variables["title"])
        if "person" in variables:
            result = result.replace("{{person}}", variables["person"])

        raw_date = variables.get("date")
        date_obj = datetime.fromisoformat(raw_date).date() if raw_date else self._now_in_user_timezone().date()

        def replace_date(match: re.Match[str]) -> str:
            format_spec = match.group(1)
            modifier = match.group(2)
            target_date = date_obj
            if modifier == "monday":
                target_date = date_obj.fromordinal(date_obj.toordinal() - date_obj.weekday())
            elif modifier == "friday":
                monday = date_obj.fromordinal(date_obj.toordinal() - date_obj.weekday())
                target_date = monday.fromordinal(monday.toordinal() + 4)
            return self._format_template_date(target_date, format_spec)

        return re.sub(r"\{\{date:([^}|]+)(?:\|([^}]+))?\}\}", replace_date, result)

    @staticmethod
    def _format_template_date(target_date, format_spec: str) -> str:
        iso_week = target_date.isocalendar().week
        months = list(calendar.month_name)
        weekdays = list(calendar.day_name)
        result = format_spec
        result = result.replace("YYYY", f"{target_date.year:04d}")
        result = result.replace("[W]ww", f"W{iso_week:02d}")
        result = result.replace("ww", f"{iso_week:02d}")
        result = result.replace("MM", f"{target_date.month:02d}")
        result = result.replace("DD", f"{target_date.day:02d}")
        result = result.replace("MMMM", months[target_date.month])
        result = result.replace("dddd", weekdays[target_date.weekday()])
        result = result.replace("D", str(target_date.day))
        return result

    def _get_current_week_id(self) -> str:
        today = self._now_in_user_timezone().date()
        iso_week = today.isocalendar().week
        return f"{today.year}-W{iso_week:02d}"

    @staticmethod
    def _week_bounds(target_week: str) -> tuple[str, str]:
        year_str, week_str = target_week.split("-W", 1)
        year = int(year_str)
        week_num = int(week_str)
        jan4 = datetime(year, 1, 4).date()
        week1_monday = jan4.fromordinal(jan4.toordinal() - jan4.weekday())
        monday = week1_monday.fromordinal(week1_monday.toordinal() + (week_num - 1) * 7)
        friday = monday.fromordinal(monday.toordinal() + 4)
        return monday.isoformat(), friday.isoformat()

    def _collect_completed_tasks(self, monday_str: str, friday_str: str) -> list[str]:
        completed_tasks: list[str] = []
        if not self.daily_dir.exists():
            return completed_tasks

        for path in sorted(self.daily_dir.glob("*.md")):
            file_date = path.stem
            if file_date < monday_str or file_date > friday_str:
                continue
            content = self._read_text(path)
            section_content = self._get_h2_section_content(content, "Tasks")
            for line in section_content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("- [x]") and stripped != "- [x]":
                    completed_tasks.append(stripped)
            # Also check PRs & Code Reviews for completed reviews
            pr_section = self._get_h2_section_content(content, "PRs & Code Reviews")
            for line in pr_section.split("\n"):
                stripped = line.strip()
                if stripped.startswith("- [x]") and stripped != "- [x]":
                    completed_tasks.append(stripped)
        return completed_tasks

    def _triage_destination(self, content: str) -> tuple[Path, str]:
        type_match = re.search(r"^type:\s*(.+)$", content, flags=re.MULTILINE)
        note_type = type_match.group(1).strip() if type_match else ""
        sample = " ".join(content.split("\n")[:5])

        if note_type == "task" or re.search(r"\b(todo|task|fix|implement|bug)\b", sample, flags=re.IGNORECASE):
            return self.tasks_dir, "task"
        if note_type == "meeting" or re.search(r"\b(meeting|standup|sync|retro)\b", sample, flags=re.IGNORECASE):
            return self.meetings_dir, "meeting"
        if note_type in {"documentation", "reference"}:
            return self.documentation_dir, "documentation"
        return self.topics_dir, "knowledge"

    def _read_sync_state(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        try:
            return json.loads(self._read_text(path))
        except Exception:
            return dict(default)

    def _write_sync_state(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _merge_unique_recent(incoming: list[str], existing: list[str], limit: int) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for item in [*incoming, *existing]:
            if item not in seen:
                unique.append(item)
                seen.add(item)
            if len(unique) >= limit:
                break
        return unique

    def _verify_highlight_dates(self, existing_pending: list[str], processed_dates: list[str], section_header: str) -> list[str]:
        pending = list(existing_pending)
        for target_date in processed_dates:
            daily_path = self._daily_note_path(target_date)
            try:
                note = self._read_text(daily_path)
                section_content = self._get_h2_section_content(note, section_header).strip()
                has_highlights = bool(section_content) and "###" in section_content
                if not has_highlights and target_date not in pending:
                    pending.append(target_date)
                elif has_highlights and target_date in pending:
                    pending.remove(target_date)
            except Exception:
                if target_date not in pending:
                    pending.append(target_date)
        return pending

    def _get_h2_section_content(self, file_content: str, section_header: str) -> str:
        span = self._find_section_span(file_content, section_header, 2)
        if span is None:
            return ""
        body_start, body_end = span
        return file_content[body_start:body_end].strip("\n")

    def _merge_highlight_section(
        self,
        file_content: str,
        section_header: str,
        incoming: str,
        merge_fn=None,
    ) -> str:
        """Append-only merge: never modifies existing content, only appends new entries."""
        span = self._find_section_span(file_content, section_header, 2)
        if span is None:
            return self._replace_or_append_h2_section(file_content, section_header, incoming)

        existing_content = self._get_h2_section_content(file_content, section_header).rstrip()
        if not existing_content.strip():
            # Section exists but is empty — safe to write
            return self._replace_or_append_h2_section(file_content, section_header, incoming)

        # Parse incoming into H3 blocks
        new_blocks = self._parse_h3_blocks(incoming)
        if not new_blocks:
            return file_content

        # Parse existing into H3 blocks to check for duplicates
        existing_blocks = self._parse_h3_blocks(existing_content)
        existing_person_keys = {key for key in existing_blocks}

        # For each new block: if person exists, append new bullets under them;
        # if person is new, append the entire block at the end
        additions_to_existing: dict[str, list[str]] = {}
        new_person_blocks: list[str] = []

        for person_key, block_data in new_blocks.items():
            if person_key in existing_person_keys:
                # Person already exists — find new bullets not already present
                existing_bullets = existing_blocks[person_key]["bullets"]
                existing_bullet_texts = {self._normalize_bullet_text(b) for b in existing_bullets}
                new_bullets = [
                    b for b in block_data["bullets"]
                    if self._normalize_bullet_text(b) not in existing_bullet_texts
                ]
                if new_bullets:
                    additions_to_existing[person_key] = new_bullets
            else:
                # New person — append entire block
                new_person_blocks.append(block_data["raw"])

        if not additions_to_existing and not new_person_blocks:
            return file_content

        # Apply additions to existing person H3 sections (append bullets at end of their section)
        body_start, body_end = span
        section_body = file_content[body_start:body_end]

        for person_key, new_bullets in additions_to_existing.items():
            header_line = existing_blocks[person_key]["header"]
            # Find the end of this person's H3 section within the section body
            h3_pattern = re.escape(header_line)
            h3_match = re.search(h3_pattern, section_body)
            if h3_match:
                # Find end of this H3 block (next H3 or end of section)
                next_h3 = re.search(r"\n### ", section_body[h3_match.end():])
                if next_h3:
                    insert_pos = h3_match.end() + next_h3.start()
                else:
                    insert_pos = len(section_body.rstrip())
                bullet_text = "\n" + "\n".join(new_bullets)
                section_body = section_body[:insert_pos] + bullet_text + section_body[insert_pos:]

        # Append new person blocks at the end
        if new_person_blocks:
            section_body = section_body.rstrip() + "\n\n" + "\n\n".join(new_person_blocks)

        return file_content[:body_start] + section_body + file_content[body_end:]

    @staticmethod
    def _parse_h3_blocks(text: str) -> dict[str, dict[str, Any]]:
        """Parse text into H3-keyed blocks. Returns {normalized_key: {header, bullets, raw}}."""
        blocks: dict[str, dict[str, Any]] = {}
        parts = re.split(r"(?=^### )", text, flags=re.MULTILINE)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            header_match = re.match(r"^(### .+)", part)
            if not header_match:
                continue
            header = header_match.group(1).strip()
            # Normalize key: extract person name from markdown link, wiki link, or plain text
            name = re.sub(r"^###\s*\[([^\]]+)\].*", r"\1", header)  # [Name](url)
            name = re.sub(r"^###\s*\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", name)  # [[Name]] or [[Name|Alias]]
            name = re.sub(r"^###\s*", "", name).strip()
            key = name.lower()
            body = part[header_match.end():].strip()
            bullets = [line for line in body.split("\n") if line.startswith("- ")]
            # Include indented sub-bullets with their parent
            all_lines = body.split("\n")
            bullet_groups: list[str] = []
            current: list[str] = []
            for line in all_lines:
                if re.match(r"^- ", line):
                    if current:
                        bullet_groups.append("\n".join(current))
                    current = [line]
                elif current and (line.startswith("  ") or not line.strip()):
                    current.append(line)
            if current:
                bullet_groups.append("\n".join(current))
            blocks[key] = {"header": header, "bullets": bullet_groups, "raw": part}
        return blocks

    @staticmethod
    def _normalize_bullet_text(bullet: str) -> str:
        """Normalize a bullet for dedup comparison — strip links, whitespace, case."""
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", bullet)  # strip markdown links
        text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", text)  # strip wiki links
        text = re.sub(r"\s+", " ", text).strip().lower()
        return text

    def _update_contact_mentions(
        self,
        *,
        target_date: str,
        context_template: str,
        people: list[str],
        person_notes: list[dict[str, str]],
    ) -> tuple[list[str], list[str]]:
        created_contacts: list[str] = []
        updated_contacts: list[str] = []
        unique_people = list(dict.fromkeys([*people, *(note["name"] for note in person_notes)]))

        for person in unique_people:
            if self._ensure_contact_exists(person, context_template.format(date=target_date)):
                created_contacts.append(person)

        for note_entry in person_notes:
            if self._append_contact_note(note_entry["name"], target_date, note_entry["note"]):
                updated_contacts.append(note_entry["name"])

        return created_contacts, updated_contacts

    def _append_contact_note(self, name: str, target_date: str, note: str) -> bool:
        contact_path = self.contacts_dir / f"{name}.md"
        if not contact_path.exists():
            return False

        contact_content = self._read_text(contact_path)
        note_entry = f"- [{target_date}] {note}"
        if note_entry in contact_content:
            return False

        if re.search(r"^## Notes\s*$", contact_content, flags=re.MULTILINE):
            contact_content = self._append_to_h2_section(
                contact_content,
                section_header="Notes",
                entry=note_entry,
                empty_markers={"-", ""},
                append_if_missing=True,
            )
        else:
            contact_content = contact_content.rstrip() + f"\n\n## Notes\n{note_entry}\n"

        self._write_text(contact_path, contact_content)
        return True

    @staticmethod
    def _build_stats_message(parts: list[str | None]) -> str:
        return "; ".join(part for part in parts if part)

    def _format_date_heading(self, target_date: str) -> str:
        year, month, day = (int(part) for part in target_date.split("-"))
        weekday_name = calendar.day_name[datetime(year, month, day).weekday()]
        month_name = calendar.month_name[month]
        return f"{weekday_name}, {month_name} {day}, {year}"

    @staticmethod
    def _normalize_line_endings(content: str) -> str:
        return content.replace("\r\n", "\n")

    @staticmethod
    def _normalize_title_for_dedup(title: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()

    def _find_existing_task_title(self, title: str) -> tuple[str, str] | None:
        if not self.tasks_dir.exists():
            return None

        normalized_target = self._normalize_title_for_dedup(title)
        for path in sorted(self.tasks_dir.glob("*.md")):
            existing_title = path.stem
            if existing_title.lower() == title.lower():
                return existing_title, "case-insensitive"
            if normalized_target and self._normalize_title_for_dedup(existing_title) == normalized_target:
                return existing_title, "similar"
        return None

    def _find_existing_pr_review_title(self, pr_number: str) -> str | None:
        if not self.pr_reviews_dir.exists():
            return None
        prefix = f"review pr {pr_number}".lower()
        for path in sorted(self.pr_reviews_dir.glob("*.md")):
            if path.stem.lower().startswith(prefix):
                return path.stem
        return None

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Strip path separators and characters illegal in filenames to enforce flat directories."""
        # Replace path separators and illegal filename chars with a dash
        sanitized = re.sub(r'[/\\:*?"<>|]', '-', name)
        # Collapse multiple dashes / trim
        sanitized = re.sub(r'-{2,}', '-', sanitized).strip(' -.')
        return sanitized or 'Untitled'

    @staticmethod
    def _require_non_empty_string(arguments: dict[str, Any], field_name: str) -> str:
        value = arguments.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Field '{field_name}' must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_string(arguments: dict[str, Any], field_name: str) -> str | None:
        value = arguments.get(field_name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"Field '{field_name}' must be a string when provided")
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _optional_string_list(arguments: dict[str, Any], field_name: str) -> list[str] | None:
        value = arguments.get(field_name)
        if value is None:
            return None
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError(f"Field '{field_name}' must be an array of non-empty strings when provided")
        return [item.strip() for item in value]

    @staticmethod
    def _optional_person_notes(arguments: dict[str, Any], field_name: str) -> list[dict[str, str]] | None:
        value = arguments.get(field_name)
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError(f"Field '{field_name}' must be an array when provided")

        parsed: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                raise ValueError(f"Field '{field_name}' entries must be objects")
            name = item.get("name")
            note = item.get("note")
            if not isinstance(name, str) or not name.strip() or not isinstance(note, str) or not note.strip():
                raise ValueError(f"Field '{field_name}' entries must include non-empty 'name' and 'note' strings")
            parsed.append({"name": name.strip(), "note": note.strip()})
        return parsed

    def _ensure_contact_exists(self, person_name: str, context: str) -> bool:
        contact_path = self.contacts_dir / f"{person_name}.md"
        if contact_path.exists():
            return False

        today = self._get_today_date()
        template = (
            f"---\ncreated: {today}\ntype: person\nrole: \nteam: \nemail: \ntags:\n  - person\n---\n\n"
            f"# {person_name}\n\n## Role\n- **Title:** \n- **Team:** \n- **Reports to:** \n\n## Contact\n- **Email:** \n- **Teams:** \n\n"
            "## Working Style\n- \n\n## Topics / Expertise\n- \n\n## 1:1 History\n```dataview\nLIST\nFROM \"02-People/1-on-1s\"\n"
            "WHERE contains(person, this.file.name)\nSORT date DESC\nLIMIT 5\n```\n\n## Meeting History\n```dataview\nLIST\nFROM \"02-People/Meetings\"\n"
            "WHERE contains(attendees, this.file.name)\nSORT date DESC\nLIMIT 5\n```\n\n"
            f"## Notes\n- {context}\n"
        )
        self._write_text(contact_path, template)
        return True

    @staticmethod
    def _pr_action_label(action: str) -> str:
        if action == "reviewed":
            return "Reviewed"
        if action == "commented":
            return "Commented"
        return "Pending Review"

    def _ensure_pr_subsections(self, content: str) -> str:
        """Ensure ### My PRs, ### Requested, and ### Discovered exist under ## PRs & Code Reviews."""
        h2_span = self._find_section_span(content, "PRs & Code Reviews", 2)
        if h2_span is None:
            return content

        subsections = ["My PRs", "Requested", "Discovered"]
        for sub in subsections:
            pattern = rf"^### {re.escape(sub)}\s*$"
            if re.search(pattern, content, re.MULTILINE) is None:
                # Find where to insert: after the last existing subsection, or after H2 header
                insert_pos = None
                for existing_sub in subsections:
                    span = self._find_section_span(content, existing_sub, 3)
                    if span:
                        _, end = span
                        if insert_pos is None or end > insert_pos:
                            insert_pos = end
                if insert_pos is None:
                    # No subsections yet — insert all after ## PRs & Code Reviews header
                    content = re.sub(
                        r"(^## PRs & Code Reviews\s*\n)",
                        r"\g<1>" + "\n".join(f"### {s}\n" for s in subsections) + "\n",
                        content,
                        count=1,
                        flags=re.MULTILINE,
                    )
                    break  # All inserted at once
                else:
                    content = content[:insert_pos] + f"\n### {sub}\n" + content[insert_pos:]
        return content

    def _promote_pr_to_requested(self, content: str, pr_marker: str) -> str:
        """Move a PR entry from ### Discovered to ### Requested if TM claims it.

        If the PR is already in ### Requested, do nothing.
        If the PR is in ### Discovered, remove it from there and add to ### Requested.
        """
        # Find ### Requested section boundaries
        req_span = self._find_section_span(content, "Requested", 3)
        disc_span = self._find_section_span(content, "Discovered", 3)

        if req_span is None or disc_span is None:
            return content  # Subsections don't exist yet

        req_start, req_end = req_span
        req_body = content[req_start:req_end]

        # Already in Requested — no-op
        if pr_marker in req_body.lower():
            return content

        disc_start, disc_end = disc_span
        disc_body = content[disc_start:disc_end]

        # Not in Discovered either — nothing to move
        if pr_marker not in disc_body.lower():
            return content

        # Find the matching line in Discovered and move it
        disc_lines = disc_body.splitlines(keepends=True)
        moved_line = None
        remaining_lines = []
        for line in disc_lines:
            if moved_line is None and pr_marker in line.lower():
                moved_line = line.rstrip("\n")
            else:
                remaining_lines.append(line)

        if moved_line is None:
            return content

        # Rebuild: remove from Discovered, add to Requested
        new_disc_body = "".join(remaining_lines)
        # Append moved line to Requested
        req_body_stripped = req_body.rstrip()
        new_req_body = f"{req_body_stripped}\n{moved_line}\n" if req_body_stripped else f"\n{moved_line}\n"

        # Reconstruct content — Requested comes before Discovered in the file
        # We need to handle both span positions carefully
        if req_start < disc_start:
            # Normal order: Requested then Discovered
            content = (
                content[:req_start]
                + new_req_body
                + content[req_end:disc_start]
                + new_disc_body
                + content[disc_end:]
            )
        else:
            # Reverse order (unusual but handle it)
            content = (
                content[:disc_start]
                + new_disc_body
                + content[disc_end:req_start]
                + new_req_body
                + content[req_end:]
            )

        return content

    @staticmethod
    def _set_frontmatter_field(content: str, field_name: str, value: str) -> str:
        field_regex = re.compile(rf"^({re.escape(field_name)}:[ \t]*).*$", re.MULTILINE)
        if field_regex.search(content):
            return field_regex.sub(lambda match: f"{match.group(1)}{value}", content, count=1)

        if content.startswith("---\n"):
            closing_index = content.find("\n---\n", 4)
            if closing_index != -1:
                insertion_point = closing_index + 1
                return content[:insertion_point] + f"{field_name}: {value}\n" + content[insertion_point:]

        return f"{field_name}: {value}\n{content}"

    @staticmethod
    def _insert_after_heading(content: str, heading: str, text: str) -> str:
        heading_regex = re.compile(rf"^(## {re.escape(heading)}\n)", re.MULTILINE)
        if heading_regex.search(content):
            return heading_regex.sub(lambda match: f"{match.group(1)}{text}\n", content, count=1)
        return content.rstrip() + f"\n\n## {heading}\n{text}\n"

    def _read_text(self, path: Path) -> str:
        return self._normalize_line_endings(path.read_text(encoding="utf-8"))

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _has_h2_section(file_content: str, section_header: str) -> bool:
        return re.search(rf"^## {re.escape(section_header)}\s*$", file_content, flags=re.MULTILINE) is not None

    def _replace_or_append_h2_section(self, file_content: str, section_header: str, new_content: str) -> str:
        return self._replace_or_append_section(file_content, section_header, new_content, level=2, append_mode=False)

    def _replace_or_append_h3_section(
        self,
        file_content: str,
        section_header: str,
        new_content: str,
        append_mode: bool,
        empty_markers: set[str],
        parent_section: str | None = None,
    ) -> str:
        return self._replace_or_append_section(
            file_content,
            section_header,
            new_content,
            level=3,
            append_mode=append_mode,
            empty_markers=empty_markers,
            parent_section=parent_section,
        )

    def _append_to_h2_section(
        self,
        file_content: str,
        section_header: str,
        entry: str,
        empty_markers: set[str],
        append_if_missing: bool,
    ) -> str:
        return self._replace_or_append_section(
            file_content,
            section_header,
            entry,
            level=2,
            append_mode=True,
            empty_markers=empty_markers,
            append_if_missing=append_if_missing,
        )

    def _replace_or_append_section(
        self,
        file_content: str,
        section_header: str,
        new_content: str,
        *,
        level: int,
        append_mode: bool,
        empty_markers: set[str] | None = None,
        append_if_missing: bool = True,
        parent_section: str | None = None,
    ) -> str:
        empty_markers = empty_markers or set()
        span = self._find_section_span(file_content, section_header, level)
        trimmed_new = new_content.strip()
        if span is not None:
            body_start, body_end = span
            existing_body = file_content[body_start:body_end].strip()
            if append_mode:
                merged = trimmed_new if existing_body in empty_markers else f"{existing_body}\n{trimmed_new}"
            else:
                merged = trimmed_new
            return file_content[:body_start] + f"\n{merged}\n" + file_content[body_end:]

        if not append_if_missing:
            return file_content

        section_prefix = "#" * level
        full_section = f"\n\n{section_prefix} {section_header}\n{trimmed_new}\n"
        if parent_section and level == 3:
            parent_span = self._find_section_span(file_content, parent_section, 2)
            if parent_span is not None:
                _, parent_end = parent_span
                return file_content[:parent_end] + full_section + file_content[parent_end:]
        end_of_day_match = re.search(r"\n## End of Day", file_content)
        if end_of_day_match and level == 2:
            insert_at = end_of_day_match.start()
            return file_content[:insert_at] + full_section + file_content[insert_at:]
        return file_content.rstrip() + full_section

    @staticmethod
    def _find_section_span(file_content: str, section_header: str, level: int) -> tuple[int, int] | None:
        header_regex = re.compile(rf"^{'#' * level} {re.escape(section_header)}\s*$", re.MULTILINE)
        header_match = header_regex.search(file_content)
        if header_match is None:
            return None
        body_start = header_match.end()
        remaining = file_content[body_start:]
        next_section = re.search(rf"\n## {'#' * max(level - 2, 0)}|\n## |\n### ", remaining) if level == 3 else re.search(r"\n## ", remaining)
        if level == 3:
            next_section = re.search(r"\n## |\n### ", remaining)
        body_end = body_start + next_section.start() if next_section else len(file_content)
        return body_start, body_end

    @staticmethod
    def _parse_timestamp(raw_timestamp: str) -> datetime:
        normalized = raw_timestamp.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized)

    @staticmethod
    def _text_response(text: str) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": text}]}