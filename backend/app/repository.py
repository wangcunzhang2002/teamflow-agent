"""SQLite persistence and idempotency boundary for TeamFlow."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import (
    ActionEdit,
    ActionItem,
    AuditEvent,
    MeetingResponse,
    ToolArtifact,
    TraceStep,
)


class MeetingNotFound(LookupError):
    """Raised when a requested meeting is absent."""


class WorkflowConflict(ValueError):
    """Raised when approval or execution violates the workflow state."""


class TeamFlowRepository:
    """Store meeting state, approvals, audit events, and tool artifacts."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        """Create all local persistence tables."""

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS meetings (
                    meeting_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    meeting_date TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    trace_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS actions (
                    action_id TEXT NOT NULL,
                    meeting_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    owner TEXT,
                    due_date TEXT,
                    source_quote TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    clarification_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    PRIMARY KEY (meeting_id, action_id),
                    FOREIGN KEY (meeting_id) REFERENCES meetings(meeting_id)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    meeting_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    idempotency_key TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    meeting_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _add_audit(
        connection: sqlite3.Connection,
        meeting_id: str,
        event_type: str,
        actor: str,
        detail: str,
    ) -> None:
        connection.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                meeting_id,
                event_type,
                actor,
                detail,
                datetime.now(UTC).isoformat(),
            ),
        )

    def save_meeting(self, meeting: MeetingResponse) -> MeetingResponse:
        """Persist an extracted meeting and its proposed actions atomically."""

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "INSERT INTO meetings VALUES (?, ?, ?, ?, ?, ?)",
                (
                    meeting.meeting_id,
                    meeting.title,
                    meeting.meeting_date.isoformat(),
                    meeting.transcript,
                    json.dumps([step.model_dump() for step in meeting.trace], ensure_ascii=False),
                    json.dumps(meeting.metrics, ensure_ascii=False),
                ),
            )
            connection.executemany(
                "INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        item.action_id,
                        meeting.meeting_id,
                        item.title,
                        item.owner,
                        item.due_date.isoformat() if item.due_date else None,
                        item.source_quote,
                        item.confidence,
                        json.dumps(item.needs_clarification, ensure_ascii=False),
                        item.status,
                    )
                    for item in meeting.action_items
                ],
            )
            self._add_audit(
                connection,
                meeting.meeting_id,
                "extracted",
                "agent",
                f"提出 {len(meeting.action_items)} 个行动项；未调用外部工具。",
            )
        return self.snapshot(meeting.meeting_id)

    def _meeting_row(self, connection: sqlite3.Connection, meeting_id: str) -> sqlite3.Row:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ).fetchone()
        if row is None:
            raise MeetingNotFound(f"Meeting {meeting_id} was not found.")
        return row

    def snapshot(self, meeting_id: str) -> MeetingResponse:
        """Reconstruct the current public meeting state."""

        with sqlite3.connect(self.db_path) as connection:
            meeting = self._meeting_row(connection, meeting_id)
            action_rows = connection.execute(
                "SELECT * FROM actions WHERE meeting_id = ? ORDER BY action_id", (meeting_id,)
            ).fetchall()
            audit_rows = connection.execute(
                """
                SELECT event_id, event_type, actor, detail, occurred_at
                FROM audit_events WHERE meeting_id = ? ORDER BY occurred_at, event_id
                """,
                (meeting_id,),
            ).fetchall()
            artifact_count = connection.execute(
                "SELECT COUNT(*) FROM artifacts WHERE meeting_id = ?", (meeting_id,)
            ).fetchone()[0]

        actions = [
            ActionItem(
                action_id=row["action_id"],
                title=row["title"],
                owner=row["owner"],
                due_date=row["due_date"],
                source_quote=row["source_quote"],
                confidence=row["confidence"],
                needs_clarification=json.loads(row["clarification_json"]),
                status=row["status"],
            )
            for row in action_rows
        ]
        metrics = json.loads(meeting["metrics_json"])
        metrics.update(
            {
                "approved_action_count": sum(item.status == "approved" for item in actions),
                "executed_action_count": sum(item.status == "executed" for item in actions),
                "tool_call_count": artifact_count,
            }
        )
        return MeetingResponse(
            meeting_id=meeting["meeting_id"],
            title=meeting["title"],
            meeting_date=meeting["meeting_date"],
            transcript=meeting["transcript"],
            action_items=actions,
            trace=[TraceStep.model_validate(item) for item in json.loads(meeting["trace_json"])],
            audit_log=[AuditEvent.model_validate(dict(row)) for row in audit_rows],
            metrics=metrics,
        )

    def approve(
        self,
        meeting_id: str,
        action_ids: list[str],
        edits: list[ActionEdit],
    ) -> MeetingResponse:
        """Apply human edits and approve only fully specified selected actions."""

        selected = set(action_ids)
        edit_map = {edit.action_id: edit for edit in edits}
        if len(selected) != len(action_ids):
            raise WorkflowConflict("Duplicate action IDs are not allowed in one approval.")
        with sqlite3.connect(self.db_path) as connection:
            self._meeting_row(connection, meeting_id)
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM actions WHERE meeting_id = ?", (meeting_id,)
            ).fetchall()
            by_id = {row["action_id"]: row for row in rows}
            unknown = selected - set(by_id)
            if unknown:
                raise WorkflowConflict(f"Unknown action IDs: {sorted(unknown)}")

            for action_id in action_ids:
                row = by_id[action_id]
                edit = edit_map.get(action_id)
                title = edit.title if edit and edit.title is not None else row["title"]
                owner = edit.owner if edit and edit.owner is not None else row["owner"]
                due_date = (
                    edit.due_date.isoformat()
                    if edit and edit.due_date is not None
                    else row["due_date"]
                )
                missing = [
                    label
                    for label, value in (("负责人", owner), ("截止日期", due_date))
                    if not value
                ]
                if missing:
                    raise WorkflowConflict(
                        f"{action_id} 仍缺少{'、'.join(missing)}，不能批准执行。"
                    )
                connection.execute(
                    """
                    UPDATE actions SET title = ?, owner = ?, due_date = ?,
                        clarification_json = '[]', status = 'approved'
                    WHERE meeting_id = ? AND action_id = ?
                    """,
                    (title, owner, due_date, meeting_id, action_id),
                )
            self._add_audit(
                connection,
                meeting_id,
                "approved",
                "human",
                f"人工批准 {len(action_ids)} 个行动项：{', '.join(action_ids)}。",
            )
        return self.snapshot(meeting_id)

    def executable_actions(self, meeting_id: str) -> list[ActionItem]:
        """Return approved or previously executed actions for idempotent retries."""

        meeting = self.snapshot(meeting_id)
        items = [item for item in meeting.action_items if item.status in {"approved", "executed"}]
        if not items:
            raise WorkflowConflict("No approved actions are available for execution.")
        return items

    def create_artifact(
        self,
        *,
        meeting_id: str,
        action_id: str,
        tool: str,
        external_id: str,
        payload: dict[str, object],
    ) -> ToolArtifact:
        """Create one mock external object exactly once per meeting/action/tool."""

        idempotency_key = f"{meeting_id}:{action_id}:{tool}"
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            existing = connection.execute(
                "SELECT * FROM artifacts WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                return ToolArtifact(
                    artifact_id=existing["artifact_id"],
                    action_id=existing["action_id"],
                    tool=existing["tool"],
                    external_id=existing["external_id"],
                    payload=json.loads(existing["payload_json"]),
                    created=False,
                )
            artifact_id = str(uuid4())
            connection.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    idempotency_key,
                    artifact_id,
                    meeting_id,
                    action_id,
                    tool,
                    external_id,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        return ToolArtifact(
            artifact_id=artifact_id,
            action_id=action_id,
            tool=tool,
            external_id=external_id,
            payload=payload,
            created=True,
        )

    def mark_executed(
        self, meeting_id: str, action_ids: list[str], created: int, duplicates: int
    ) -> None:
        """Advance action state and record the result of a tool execution attempt."""

        with sqlite3.connect(self.db_path) as connection:
            connection.executemany(
                "UPDATE actions SET status = 'executed' WHERE meeting_id = ? AND action_id = ?",
                [(meeting_id, action_id) for action_id in action_ids],
            )
            self._add_audit(
                connection,
                meeting_id,
                "executed",
                "tool",
                f"创建 {created} 个模拟对象，幂等拦截 {duplicates} 个重复对象。",
            )
