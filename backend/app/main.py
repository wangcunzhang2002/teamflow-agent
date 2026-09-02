"""FastAPI entry point for TeamFlow."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .llm import OpenAICompatibleJsonClient
from .models import ApprovalRequest, ExecutionResponse, ExtractRequest, MeetingResponse
from .repository import MeetingNotFound, TeamFlowRepository, WorkflowConflict
from .tools import MockWorkTools
from .workflow import TeamFlowAgent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
repository = TeamFlowRepository(PROJECT_ROOT / "runtime" / "teamflow.db")
repository.initialize()
agent = TeamFlowAgent(llm=OpenAICompatibleJsonClient.from_env())
tools = MockWorkTools(repository)

app = FastAPI(
    title="TeamFlow API",
    version="0.1.0",
    description="Human-gated meeting action extraction and idempotent mock execution.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5175", "http://127.0.0.1:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Expose readiness and the explicit mock-tools mode."""

    mode = "llm-assisted" if agent.llm is not None else "deterministic-demo"
    return {"status": "ok", "mode": mode, "tools": "mock"}


@app.post("/api/meetings/extract", response_model=MeetingResponse)
def extract(request: ExtractRequest) -> MeetingResponse:
    """Extract proposed actions without executing side effects."""

    meeting = agent.extract(request.title, request.meeting_date, request.transcript)
    return repository.save_meeting(meeting)


@app.get("/api/meetings/{meeting_id}", response_model=MeetingResponse)
def get_meeting(meeting_id: str) -> MeetingResponse:
    """Return the latest persisted state."""

    try:
        return repository.snapshot(meeting_id)
    except MeetingNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/meetings/{meeting_id}/approve", response_model=MeetingResponse)
def approve(meeting_id: str, request: ApprovalRequest) -> MeetingResponse:
    """Apply corrections and advance selected actions through the human gate."""

    try:
        return repository.approve(meeting_id, request.action_ids, request.edits)
    except MeetingNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/meetings/{meeting_id}/execute", response_model=ExecutionResponse)
def execute(meeting_id: str) -> ExecutionResponse:
    """Create mock external objects for approved actions only."""

    try:
        return tools.execute(meeting_id)
    except MeetingNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
