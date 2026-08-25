"""批量审计真实 Demo 的局势状态覆盖，暴露解析盲区而不是隐藏缺失值。"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field

from chapter07_cs2_coach.models import MatchRecord
from chapter07_cs2_coach.situation_state import build_situation_state


class SituationCoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_count: int = Field(ge=0)
    engagement_count: int = Field(ge=0)
    average_information_completeness: float = Field(ge=0, le=100)
    low_information_engagements: int = Field(ge=0)
    phase_counts: dict[str, int]
    manpower_counts: dict[str, int]
    support_counts: dict[str, int]
    objective_counts: dict[str, int]
    tempo_counts: dict[str, int]
    warnings: list[str] = Field(default_factory=list, max_length=20)


def audit_situation_coverage(matches: list[MatchRecord]) -> SituationCoverageReport:
    states = [
        build_situation_state(item)
        for match in matches
        for item in match.engagements
    ]
    count = len(states)
    average = (
        round(sum(item.information_completeness for item in states) / count, 2)
        if states
        else 0.0
    )
    low_information = sum(item.information_completeness < 60 for item in states)
    warnings: list[str] = []
    if not states:
        warnings.append("没有接战快照，无法评估局势状态覆盖。")
    if states and low_information / count >= 0.25:
        warnings.append(
            f"{low_information}/{count} 次接战的信息完整度低于 60%，局势建议应降低置信度。"
        )
    settled = sum(item.phase == "settled" for item in states)
    if states and settled / count >= 0.05:
        warnings.append(
            f"{settled}/{count} 次接战落在回合结算阶段，需检查事件时间窗是否越界。"
        )
    unknown_phase = sum(item.phase == "unknown" for item in states)
    if states and unknown_phase / count >= 0.5:
        warnings.append(
            f"{unknown_phase}/{count} 次接战缺少回合时间，无法区分开局、中期和后段。"
        )
    return SituationCoverageReport(
        match_count=len(matches),
        engagement_count=count,
        average_information_completeness=average,
        low_information_engagements=low_information,
        phase_counts=dict(Counter(item.phase for item in states)),
        manpower_counts=dict(Counter(item.manpower for item in states)),
        support_counts=dict(Counter(item.support for item in states)),
        objective_counts=dict(Counter(item.objective for item in states)),
        tempo_counts=dict(Counter(item.tempo for item in states)),
        warnings=warnings,
    )


__all__ = ["SituationCoverageReport", "audit_situation_coverage"]
