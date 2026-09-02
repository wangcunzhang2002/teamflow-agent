"""Pure payload builders shared by HTTP execution and the MCP transport."""

from datetime import date
from typing import Any


def build_task_payload(title: str, owner: str, due_date: date) -> dict[str, Any]:
    """Build a deterministic mock task payload."""

    return {
        "title": title,
        "assignee": owner,
        "due_date": due_date.isoformat(),
        "labels": ["teamflow", "meeting-action"],
    }


def build_calendar_payload(title: str, owner: str, due_date: date) -> dict[str, Any]:
    """Build a deterministic all-day calendar reminder payload."""

    return {
        "summary": f"截止：{title}",
        "attendee": owner,
        "date": due_date.isoformat(),
        "all_day": True,
    }
