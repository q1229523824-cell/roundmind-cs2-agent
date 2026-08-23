"""Dust2 决策评分回归评测，可直接作为 CI 测试或本地命令运行。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from chapter07_cs2_coach.decision_scoring import score_engagement
from chapter07_cs2_coach.models import EngagementRecord, MatchRecord


EVALUATION_PATH = (
    Path(__file__).resolve().parent / "evaluation" / "dust2_decisions.json"
)


class DecisionEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    engagement: EngagementRecord
    expected_level: Literal["high", "medium", "low"]
    min_score: int = Field(ge=0, le=100)
    max_score: int = Field(ge=0, le=100)
    expected_confidence: Literal["high", "medium", "low"] | None = None


class DecisionEvaluationResult(BaseModel):
    total: int
    passed: int
    accuracy: float
    failures: list[str]


def load_evaluation_cases() -> list[DecisionEvaluationCase]:
    payload = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    return [DecisionEvaluationCase.model_validate(item) for item in payload]


def _match_for(case: DecisionEvaluationCase) -> MatchRecord:
    return MatchRecord.model_validate(
        {
            "match_id": f"eval-{case.id}",
            "player_name": "EvaluationPlayer",
            "map_name": "de_dust2",
            "team_name": "Team A",
            "opponent_name": "Team B",
            "team_score": 0,
            "opponent_score": 1,
            "rounds": [
                {"number": 1, "side": case.engagement.side, "won": False, "died": True}
            ],
            "engagements": [case.engagement.model_dump()],
        }
    )


def run_decision_evaluation() -> DecisionEvaluationResult:
    cases = load_evaluation_cases()
    failures: list[str] = []
    for case in cases:
        card = score_engagement(_match_for(case), case.engagement)
        valid = (
            card.risk_level == case.expected_level
            and case.min_score <= card.risk_score <= case.max_score
            and (
                case.expected_confidence is None
                or card.confidence == case.expected_confidence
            )
        )
        if not valid:
            failures.append(
                f"{case.id}: 得到 {card.risk_level}/{card.risk_score}/{card.confidence}"
            )
    passed = len(cases) - len(failures)
    return DecisionEvaluationResult(
        total=len(cases),
        passed=passed,
        accuracy=round(passed / len(cases), 4) if cases else 0,
        failures=failures,
    )


if __name__ == "__main__":
    print(run_decision_evaluation().model_dump_json(indent=2))
