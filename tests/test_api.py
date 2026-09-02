"""HTTP workflow contract tests."""

from pathlib import Path

from app.main import app
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_http_flow_enforces_approval_gate() -> None:
    transcript = (PROJECT_ROOT / "data" / "sprint-planning.txt").read_text(encoding="utf-8")
    extracted = client.post(
        "/api/meetings/extract",
        json={
            "title": "迭代规划会",
            "meeting_date": "2026-08-26",
            "transcript": transcript,
        },
    )
    assert extracted.status_code == 200
    meeting_id = extracted.json()["meeting_id"]

    blocked = client.post(f"/api/meetings/{meeting_id}/execute")
    assert blocked.status_code == 409

    approved = client.post(
        f"/api/meetings/{meeting_id}/approve",
        json={"action_ids": ["ACT-001"], "edits": []},
    )
    assert approved.status_code == 200
    executed = client.post(f"/api/meetings/{meeting_id}/execute")
    assert executed.status_code == 200
    assert executed.json()["created_count"] == 2
