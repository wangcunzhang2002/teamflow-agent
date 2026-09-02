"""Mock external tools with deterministic payloads and idempotent persistence."""

from hashlib import sha256

from .models import ActionItem, ExecutionResponse
from .repository import TeamFlowRepository
from .tool_payloads import build_calendar_payload, build_task_payload


class MockWorkTools:
    """Create task and calendar artifacts without contacting third-party services."""

    def __init__(self, repository: TeamFlowRepository) -> None:
        self.repository = repository

    @staticmethod
    def _external_id(meeting_id: str, action_id: str, tool: str) -> str:
        digest = sha256(f"{meeting_id}:{action_id}:{tool}".encode()).hexdigest()[:10]
        return f"MOCK-{tool.upper()}-{digest}"

    def execute(self, meeting_id: str) -> ExecutionResponse:
        """Execute approved actions; safe retries return existing artifacts."""

        actions = self.repository.executable_actions(meeting_id)
        artifacts = []
        for action in actions:
            if action.owner is None or action.due_date is None:
                raise ValueError("Repository returned an incomplete approved action.")
            artifacts.append(self._create_task(meeting_id, action))
            artifacts.append(self._create_calendar_event(meeting_id, action))
        created_count = sum(artifact.created for artifact in artifacts)
        duplicate_count = len(artifacts) - created_count
        self.repository.mark_executed(
            meeting_id,
            [action.action_id for action in actions],
            created_count,
            duplicate_count,
        )
        return ExecutionResponse(
            meeting_id=meeting_id,
            artifacts=artifacts,
            created_count=created_count,
            duplicate_prevented_count=duplicate_count,
        )

    def _create_task(self, meeting_id: str, action: ActionItem):
        assert action.owner is not None and action.due_date is not None
        return self.repository.create_artifact(
            meeting_id=meeting_id,
            action_id=action.action_id,
            tool="task",
            external_id=self._external_id(meeting_id, action.action_id, "task"),
            payload=build_task_payload(action.title, action.owner, action.due_date),
        )

    def _create_calendar_event(self, meeting_id: str, action: ActionItem):
        assert action.owner is not None and action.due_date is not None
        return self.repository.create_artifact(
            meeting_id=meeting_id,
            action_id=action.action_id,
            tool="calendar",
            external_id=self._external_id(meeting_id, action.action_id, "calendar"),
            payload=build_calendar_payload(action.title, action.owner, action.due_date),
        )
