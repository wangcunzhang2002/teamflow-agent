"""Evaluate action, owner, and deadline extraction on a tracked meeting."""

import json
from datetime import date
from pathlib import Path

from app.workflow import TeamFlowAgent

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Write exact-field scores and preserve per-case errors."""

    expected = json.loads(
        (PROJECT_ROOT / "evals" / "expected.json").read_text(encoding="utf-8")
    )
    transcript = (PROJECT_ROOT / "data" / "sprint-planning.txt").read_text(encoding="utf-8")
    result = TeamFlowAgent().extract(
        "迭代规划会",
        date.fromisoformat(expected["meeting_date"]),
        transcript,
    )
    matched = []
    for gold in expected["actions"]:
        prediction = next(
            (item for item in result.action_items if gold["title_contains"] in item.title),
            None,
        )
        matched.append(
            {
                "title_contains": gold["title_contains"],
                "found": prediction is not None,
                "owner_correct": prediction is not None and prediction.owner == gold["owner"],
                "deadline_correct": prediction is not None
                and (prediction.due_date.isoformat() if prediction.due_date else None)
                == gold["due_date"],
            }
        )
    count = len(matched)
    report = {
        "expected_action_count": count,
        "predicted_action_count": len(result.action_items),
        "action_recall": sum(item["found"] for item in matched) / count,
        "owner_accuracy": sum(item["owner_correct"] for item in matched) / count,
        "deadline_accuracy": sum(item["deadline_correct"] for item in matched) / count,
        "approval_bypass_count": result.metrics["approval_bypass_count"],
        "records": matched,
    }
    (PROJECT_ROOT / "evals" / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
