"""Optional MCP transport exposing the same pure payload builders."""

from datetime import date

from mcp.server import MCPServer

from .tool_payloads import build_calendar_payload, build_task_payload

mcp = MCPServer("teamflow-work-tools")


@mcp.tool()
def prepare_task(title: str, owner: str, due_date: str) -> dict[str, object]:
    """Prepare a task payload; persistence remains behind the approval gate."""

    return build_task_payload(title, owner, date.fromisoformat(due_date))


@mcp.tool()
def prepare_calendar_event(title: str, owner: str, due_date: str) -> dict[str, object]:
    """Prepare an all-day reminder payload for an approved action."""

    return build_calendar_payload(title, owner, date.fromisoformat(due_date))


if __name__ == "__main__":
    mcp.run()
