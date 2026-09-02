"""MCP v2 transport registration smoke tests."""

import asyncio

from app.mcp_server import mcp


def test_mcp_registers_both_work_tools() -> None:
    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} == {"prepare_task", "prepare_calendar_event"}
