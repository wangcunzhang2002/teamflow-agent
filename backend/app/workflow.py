"""LangGraph workflow that extracts action items without executing tools."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from time import perf_counter
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from .llm import JsonLLM, LLMProviderError
from .models import ActionItem, MeetingResponse, TraceStep

LINE_PATTERN = re.compile(r"^(?:\[\d{1,2}:\d{2}\]\s*)?(?P<speaker>[^：:]+)[：:](?P<text>.+)$")
ACTION_WORDS = ("完成", "负责", "更新", "整理", "跟进", "提交", "准备", "联调", "评审稿")
WEEKDAY_INDEX = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


class TeamFlowState(TypedDict, total=False):
    """State exchanged by transcript processing steps."""

    title: str
    meeting_date: date
    transcript: str
    segments: list[tuple[str, str]]
    action_items: list[ActionItem]
    trace: list[TraceStep]
    extraction_mode: str
    model_call_count: int
    fallback_count: int


def resolve_due_date(text: str, meeting_date: date) -> date | None:
    """Resolve the small, documented date grammar used by the demo extractor."""

    explicit = re.search(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日?前?", text)
    if explicit:
        candidate = date(
            meeting_date.year,
            int(explicit.group("month")),
            int(explicit.group("day")),
        )
        if candidate < meeting_date:
            candidate = candidate.replace(year=meeting_date.year + 1)
        return candidate
    if "后天" in text:
        return meeting_date + timedelta(days=2)
    if "明天" in text:
        return meeting_date + timedelta(days=1)
    if "今天" in text:
        return meeting_date

    next_week = re.search(r"下周(?P<weekday>[一二三四五六日天])", text)
    if next_week:
        monday = meeting_date - timedelta(days=meeting_date.weekday())
        return monday + timedelta(days=7 + WEEKDAY_INDEX[next_week.group("weekday")])
    this_week = re.search(r"周(?P<weekday>[一二三四五六日天])", text)
    if this_week:
        delta = (WEEKDAY_INDEX[this_week.group("weekday")] - meeting_date.weekday()) % 7
        return meeting_date + timedelta(days=delta)
    return None


class TeamFlowAgent:
    """Extract and validate proposed actions; never call external tools itself."""

    def __init__(self, llm: JsonLLM | None = None) -> None:
        self.llm = llm
        graph = StateGraph(TeamFlowState)
        graph.add_node("segment_transcript", self._segment_transcript)
        graph.add_node("extract_actions", self._extract_actions)
        graph.add_node("validate_fields", self._validate_fields)
        graph.add_edge(START, "segment_transcript")
        graph.add_edge("segment_transcript", "extract_actions")
        graph.add_edge("extract_actions", "validate_fields")
        graph.add_edge("validate_fields", END)
        self.graph = graph.compile()

    @staticmethod
    def _trace(
        state: TeamFlowState, name: str, summary: str, started_at: float
    ) -> list[TraceStep]:
        return [
            *state.get("trace", []),
            TraceStep(
                name=name,
                summary=summary,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
            ),
        ]

    def _segment_transcript(self, state: TeamFlowState) -> TeamFlowState:
        started_at = perf_counter()
        segments = []
        for raw_line in state["transcript"].splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = LINE_PATTERN.match(line)
            if match:
                segments.append((match.group("speaker").strip(), match.group("text").strip()))
        return {
            "segments": segments,
            "trace": self._trace(
                state,
                "segment_transcript",
                f"识别 {len(segments)} 个带说话人的文本片段。",
                started_at,
            ),
        }

    @staticmethod
    def _rule_items(state: TeamFlowState) -> list[ActionItem]:
        items = []
        for speaker, text in state["segments"]:
            if not any(word in text for word in ACTION_WORDS):
                continue
            anonymous_owner = any(marker in text for marker in ("有人", "待定", "谁来"))
            owner = None if anonymous_owner else speaker
            due_date = resolve_due_date(text, state["meeting_date"])
            missing = []
            if owner is None:
                missing.append("负责人")
            if due_date is None:
                missing.append("截止日期")
            confidence = 1.0 if not missing else (0.72 if len(missing) == 1 else 0.45)
            items.append(
                ActionItem(
                    action_id=f"ACT-{len(items) + 1:03d}",
                    title=text.rstrip("。"),
                    owner=owner,
                    due_date=due_date,
                    source_quote=f"{speaker}：{text}",
                    confidence=confidence,
                    needs_clarification=missing,
                )
            )
        return items

    def _model_items(self, state: TeamFlowState) -> list[ActionItem]:
        if self.llm is None:
            raise LLMProviderError("No model client is configured.")
        payload = self.llm.complete_json(
            system=(
                "你是会议行动项抽取器。只返回 JSON 对象 {actions: [...] }。每项包含 "
                "title、owner（可为 null）、due_date（YYYY-MM-DD 或 null）、source_quote。"
                "source_quote 必须逐字来自原会议记录，不得创造负责人或日期。"
            ),
            user=json.dumps(
                {
                    "meeting_date": state["meeting_date"].isoformat(),
                    "transcript": state["transcript"],
                },
                ensure_ascii=False,
            ),
        )
        raw_actions = payload.get("actions")
        if not isinstance(raw_actions, list):
            raise LLMProviderError("Model actions must be a list.")
        items = []
        for raw_action in raw_actions:
            if not isinstance(raw_action, dict):
                raise LLMProviderError("Each model action must be an object.")
            title = raw_action.get("title")
            owner = raw_action.get("owner")
            due_value = raw_action.get("due_date")
            source_quote = raw_action.get("source_quote")
            if not isinstance(title, str) or not title.strip():
                raise LLMProviderError("Model action title is invalid.")
            if owner is not None and not isinstance(owner, str):
                raise LLMProviderError("Model action owner is invalid.")
            if not isinstance(source_quote, str) or source_quote not in state["transcript"]:
                raise LLMProviderError("Model source quote is not present in the transcript.")
            if isinstance(owner, str) and owner.strip() and owner.strip() not in source_quote:
                raise LLMProviderError("Model owner is not grounded in the source quote.")
            if due_value is None:
                due_date = None
            elif isinstance(due_value, str):
                try:
                    due_date = date.fromisoformat(due_value)
                except ValueError as exc:
                    raise LLMProviderError("Model due date is not ISO formatted.") from exc
            else:
                raise LLMProviderError("Model due date is invalid.")
            if due_date is not None and due_date < state["meeting_date"]:
                raise LLMProviderError("Model due date is earlier than the meeting date.")
            missing = []
            if not owner:
                missing.append("负责人")
            if due_date is None:
                missing.append("截止日期")
            items.append(
                ActionItem(
                    action_id=f"ACT-{len(items) + 1:03d}",
                    title=title.strip(),
                    owner=owner.strip() if isinstance(owner, str) and owner.strip() else None,
                    due_date=due_date,
                    source_quote=source_quote,
                    confidence=1.0 if not missing else (0.72 if len(missing) == 1 else 0.45),
                    needs_clarification=missing,
                )
            )
        if not items:
            raise LLMProviderError("Model returned no action items.")
        return items

    def _extract_actions(self, state: TeamFlowState) -> TeamFlowState:
        started_at = perf_counter()
        items = self._rule_items(state)
        extraction_mode = "deterministic"
        model_call_count = 0
        fallback_count = 0
        if self.llm is not None:
            model_call_count = 1
            try:
                items = self._model_items(state)
                extraction_mode = "llm"
            except LLMProviderError:
                extraction_mode = "fallback"
                fallback_count = 1
        return {
            "action_items": items,
            "extraction_mode": extraction_mode,
            "model_call_count": model_call_count,
            "fallback_count": fallback_count,
            "trace": self._trace(
                state,
                "extract_actions",
                f"以 {extraction_mode} 模式提取 {len(items)} 个候选行动项，"
                "尚未执行任何工具。",
                started_at,
            ),
        }

    def _validate_fields(self, state: TeamFlowState) -> TeamFlowState:
        started_at = perf_counter()
        incomplete = sum(bool(item.needs_clarification) for item in state["action_items"])
        return {
            "trace": self._trace(
                state,
                "validate_fields",
                f"发现 {incomplete} 个待补充行动项；所有项目保持 proposed 状态等待人工审批。",
                started_at,
            )
        }

    def extract(self, title: str, meeting_date: date, transcript: str) -> MeetingResponse:
        """Return proposed actions with no side effects beyond computation."""

        state = self.graph.invoke(
            {
                "title": title,
                "meeting_date": meeting_date,
                "transcript": transcript,
                "trace": [],
            }
        )
        complete_count = sum(not item.needs_clarification for item in state["action_items"])
        return MeetingResponse(
            meeting_id=str(uuid4()),
            title=title,
            meeting_date=meeting_date,
            transcript=transcript,
            action_items=state["action_items"],
            trace=state["trace"],
            audit_log=[],
            metrics={
                "proposed_action_count": len(state["action_items"]),
                "fully_specified_count": complete_count,
                "approval_bypass_count": 0,
                "tool_call_count": 0,
                "model_call_count": state["model_call_count"],
                "llm_fallback_count": state["fallback_count"],
            },
        )
