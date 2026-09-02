"""Data contracts for TeamFlow's human-gated execution flow."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    """Meeting content submitted for action extraction."""

    title: str = Field(min_length=2, max_length=200)
    meeting_date: date
    transcript: str = Field(min_length=10, max_length=20_000)


class TraceStep(BaseModel):
    """One deterministic workflow step."""

    name: str
    summary: str
    duration_ms: float = Field(ge=0)


class ActionItem(BaseModel):
    """A proposed or approved unit of work with source lineage."""

    action_id: str
    title: str
    owner: str | None
    due_date: date | None
    source_quote: str
    confidence: float = Field(ge=0, le=1)
    needs_clarification: list[str]
    status: Literal["proposed", "approved", "executed"] = "proposed"


class ActionEdit(BaseModel):
    """A human correction applied before approval."""

    action_id: str
    title: str | None = Field(default=None, min_length=2, max_length=500)
    owner: str | None = Field(default=None, min_length=1, max_length=100)
    due_date: date | None = None


class ApprovalRequest(BaseModel):
    """Selection and optional edits supplied by a human reviewer."""

    action_ids: list[str] = Field(min_length=1)
    edits: list[ActionEdit] = Field(default_factory=list)


class AuditEvent(BaseModel):
    """An immutable event in the meeting execution history."""

    event_id: str
    event_type: Literal["extracted", "approved", "executed"]
    actor: Literal["agent", "human", "tool"]
    detail: str
    occurred_at: str


class MeetingResponse(BaseModel):
    """Current persisted meeting state."""

    meeting_id: str
    title: str
    meeting_date: date
    transcript: str
    action_items: list[ActionItem]
    trace: list[TraceStep]
    audit_log: list[AuditEvent]
    metrics: dict[str, float | int]


class ToolArtifact(BaseModel):
    """A mock external object produced through an idempotent tool call."""

    artifact_id: str
    action_id: str
    tool: Literal["task", "calendar"]
    external_id: str
    payload: dict[str, Any]
    created: bool


class ExecutionResponse(BaseModel):
    """Tool execution result including duplicate prevention evidence."""

    meeting_id: str
    artifacts: list[ToolArtifact]
    created_count: int
    duplicate_prevented_count: int
