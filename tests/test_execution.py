"""Approval gate and idempotent tool tests."""

from datetime import date
from pathlib import Path

import pytest
from app.models import ActionEdit
from app.repository import TeamFlowRepository, WorkflowConflict
from app.tools import MockWorkTools
from app.workflow import TeamFlowAgent

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path: Path) -> tuple[TeamFlowRepository, str]:
    repository = TeamFlowRepository(tmp_path / "teamflow.db")
    repository.initialize()
    transcript = (PROJECT_ROOT / "data" / "sprint-planning.txt").read_text(encoding="utf-8")
    meeting = TeamFlowAgent().extract("迭代规划会", date(2026, 8, 26), transcript)
    repository.save_meeting(meeting)
    return repository, meeting.meeting_id


def test_execution_is_blocked_before_approval(
    setup: tuple[TeamFlowRepository, str],
) -> None:
    repository, meeting_id = setup

    with pytest.raises(WorkflowConflict):
        MockWorkTools(repository).execute(meeting_id)


def test_incomplete_action_requires_human_edit(
    setup: tuple[TeamFlowRepository, str],
) -> None:
    repository, meeting_id = setup
    with pytest.raises(WorkflowConflict):
        repository.approve(meeting_id, ["ACT-004"], [])

    approved = repository.approve(
        meeting_id,
        ["ACT-004"],
        [
            ActionEdit(
                action_id="ACT-004",
                owner="陈晨",
                due_date=date(2026, 9, 1),
            )
        ],
    )
    assert approved.action_items[3].status == "approved"
    assert approved.action_items[3].needs_clarification == []


def test_tool_retry_does_not_create_duplicates(
    setup: tuple[TeamFlowRepository, str],
) -> None:
    repository, meeting_id = setup
    repository.approve(meeting_id, ["ACT-001"], [])
    tools = MockWorkTools(repository)

    first = tools.execute(meeting_id)
    second = tools.execute(meeting_id)

    assert first.created_count == 2
    assert first.duplicate_prevented_count == 0
    assert second.created_count == 0
    assert second.duplicate_prevented_count == 2
    assert {artifact.external_id for artifact in first.artifacts} == {
        artifact.external_id for artifact in second.artifacts
    }
