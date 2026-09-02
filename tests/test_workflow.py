"""Extraction and date-resolution tests."""

from datetime import date
from pathlib import Path
from typing import Any

from app.workflow import TeamFlowAgent

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StubExtractor:
    """A model stub that exercises transcript-grounded structured extraction."""

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        assert "不得创造负责人或日期" in system
        assert "meeting_date" in user
        return {
            "actions": [
                {
                    "title": "完成登录接口联调",
                    "owner": "李明",
                    "due_date": "2026-08-28",
                    "source_quote": "李明：我会在周五前完成登录接口联调。",
                }
            ]
        }


class UngroundedExtractor:
    """A model stub with a fabricated source quote."""

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        return {
            "actions": [
                {
                    "title": "发布正式版本",
                    "owner": "不存在的人",
                    "due_date": "2026-08-27",
                    "source_quote": "会议中从未出现的原句",
                }
            ]
        }


def test_extracts_actions_and_marks_ambiguity() -> None:
    transcript = (PROJECT_ROOT / "data" / "sprint-planning.txt").read_text(encoding="utf-8")
    result = TeamFlowAgent().extract("迭代规划会", date(2026, 8, 26), transcript)

    assert len(result.action_items) == 4
    assert result.action_items[0].owner == "李明"
    assert result.action_items[0].due_date == date(2026, 8, 28)
    assert result.action_items[1].due_date == date(2026, 8, 30)
    assert result.action_items[2].due_date == date(2026, 8, 31)
    assert result.action_items[3].needs_clarification == ["负责人", "截止日期"]
    assert all(item.status == "proposed" for item in result.action_items)


def test_model_output_must_remain_grounded_in_transcript() -> None:
    transcript = (PROJECT_ROOT / "data" / "sprint-planning.txt").read_text(encoding="utf-8")
    result = TeamFlowAgent(llm=StubExtractor()).extract(
        "迭代规划会", date(2026, 8, 26), transcript
    )

    assert len(result.action_items) == 1
    assert result.action_items[0].owner == "李明"
    assert result.metrics["model_call_count"] == 1
    assert result.metrics["llm_fallback_count"] == 0


def test_fabricated_model_quote_triggers_rule_fallback() -> None:
    transcript = (PROJECT_ROOT / "data" / "sprint-planning.txt").read_text(encoding="utf-8")
    result = TeamFlowAgent(llm=UngroundedExtractor()).extract(
        "迭代规划会", date(2026, 8, 26), transcript
    )

    assert len(result.action_items) == 4
    assert result.metrics["llm_fallback_count"] == 1
