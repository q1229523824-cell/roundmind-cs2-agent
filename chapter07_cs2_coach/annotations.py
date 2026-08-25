"""真实 Demo 决策标注包：匿名导出、分层抽样与质量指标。"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from chapter07_cs2_coach.decision_scoring import build_decision_cards
from chapter07_cs2_coach.models import DecisionCard, EngagementRecord, MatchRecord


HumanVerdict = Literal["high_risk", "review", "reasonable", "uncertain"]
ScoredVerdict = Literal["high_risk", "review", "reasonable"]
VERDICT_ORDER: dict[ScoredVerdict, int] = {
    "reasonable": 0,
    "review": 1,
    "high_risk": 2,
}


class HumanAnnotation(BaseModel):
    """未来由玩家或教练填写；空 verdict 表示仍待标注。"""

    model_config = ConfigDict(extra="forbid")

    verdict: HumanVerdict | None = None
    reason_tags: list[str] = Field(default_factory=list, max_length=10)
    better_action: str = Field(default="", max_length=400)
    note: str = Field(default="", max_length=600)
    annotator_alias: str = Field(default="", max_length=80)


class AnnotationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^case_[a-f0-9]{16}$")
    round_number: int = Field(ge=1, le=100)
    tick: int = Field(ge=0)
    map_name: str
    engagement: EngagementRecord
    prediction: DecisionCard
    human_annotation: HumanAnnotation = Field(default_factory=HumanAnnotation)


class AnnotationPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.annotation.v1"] = "roundmind.annotation.v1"
    created_at: datetime
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{16}$")
    map_name: str
    selection_strategy: str
    cases: list[AnnotationCase] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> "AnnotationPackage":
        ids = [item.case_id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("标注包 case_id 不能重复。")
        return self


class AnnotationMetrics(BaseModel):
    total_cases: int
    labeled_cases: int
    scorable_cases: int
    coverage: float
    exact_agreement: float | None
    mean_ordinal_error: float | None
    high_risk_precision: float | None
    high_risk_recall: float | None
    top3_high_risk_precision: float | None
    uncertain_cases: int
    confusion: dict[str, int]


def _case_id(match: MatchRecord, engagement: EngagementRecord) -> str:
    identity = (
        f"{match.match_id}|{match.player_steamid or match.player_name}|"
        f"{engagement.round_number}|{engagement.tick}"
    )
    return f"case_{sha256(identity.encode('utf-8')).hexdigest()[:16]}"


def _source_fingerprint(match: MatchRecord) -> str:
    identity = f"{match.match_id}|{match.player_steamid or match.player_name}"
    return sha256(identity.encode("utf-8")).hexdigest()[:16]


def select_annotation_cards(
    cards: list[DecisionCard],
    *,
    limit: int = 8,
) -> list[DecisionCard]:
    """兼顾高风险、阈值边界、低风险对照和类型多样性。"""

    if limit <= 0:
        return []
    selected: list[DecisionCard] = []
    selected_keys: set[tuple[int, int]] = set()

    def add(card: DecisionCard) -> None:
        key = (card.round_number, card.tick)
        if key not in selected_keys and len(selected) < limit:
            selected.append(card)
            selected_keys.add(key)

    high = sorted(
        (card for card in cards if card.risk_level == "high"),
        key=lambda card: (-card.risk_score, card.round_number),
    )
    for card in high[:2]:
        add(card)

    low = sorted(
        (card for card in cards if card.risk_level == "low"),
        key=lambda card: (card.risk_score, card.round_number),
    )
    if low:
        add(low[0])

    for threshold in (70, 40):
        boundary = sorted(
            cards,
            key=lambda card: (abs(card.risk_score - threshold), card.round_number),
        )
        for card in boundary[:2]:
            add(card)

    uncertain = sorted(
        (card for card in cards if card.confidence != "high"),
        key=lambda card: (card.confidence != "low", -card.risk_score),
    )
    if uncertain:
        add(uncertain[0])

    seen_classes = {card.classification for card in selected}
    diverse = sorted(
        cards,
        key=lambda card: (
            card.classification in seen_classes,
            -card.risk_score,
            card.round_number,
        ),
    )
    for card in diverse:
        add(card)
        seen_classes.add(card.classification)
    return selected


def create_annotation_package(
    match: MatchRecord,
    *,
    limit: int = 8,
) -> AnnotationPackage:
    engagement_by_key = {
        (item.round_number, item.tick): item for item in match.engagements
    }
    selected = select_annotation_cards(build_decision_cards(match), limit=limit)
    cases = []
    for card in selected:
        engagement = engagement_by_key[(card.round_number, card.tick)]
        cases.append(
            AnnotationCase(
                case_id=_case_id(match, engagement),
                round_number=engagement.round_number,
                tick=engagement.tick,
                map_name=match.map_name,
                engagement=engagement,
                prediction=card,
            )
        )
    if not cases:
        raise ValueError("比赛没有可用于标注的接战快照。")
    return AnnotationPackage(
        created_at=datetime.now(UTC),
        source_fingerprint=_source_fingerprint(match),
        map_name=match.map_name,
        selection_strategy="stratified_risk_boundary_diversity_v1",
        cases=cases,
    )


def evaluate_annotations(package: AnnotationPackage) -> AnnotationMetrics:
    labeled = [
        item for item in package.cases if item.human_annotation.verdict is not None
    ]
    scorable = [
        item
        for item in labeled
        if item.human_annotation.verdict != "uncertain"
    ]
    confusion: dict[str, int] = {}
    exact = 0
    ordinal_error = 0
    predicted_high = 0
    true_high = 0
    true_positive_high = 0
    for item in scorable:
        predicted = item.prediction.verdict
        actual = item.human_annotation.verdict
        assert actual in VERDICT_ORDER
        confusion[f"actual={actual}|predicted={predicted}"] = (
            confusion.get(f"actual={actual}|predicted={predicted}", 0) + 1
        )
        exact += predicted == actual
        ordinal_error += abs(VERDICT_ORDER[predicted] - VERDICT_ORDER[actual])
        predicted_high += predicted == "high_risk"
        true_high += actual == "high_risk"
        true_positive_high += predicted == actual == "high_risk"

    top3 = sorted(
        scorable,
        key=lambda item: (-item.prediction.risk_score, item.round_number),
    )[:3]
    top3_precision = (
        sum(item.human_annotation.verdict == "high_risk" for item in top3) / len(top3)
        if top3
        else None
    )
    count = len(scorable)
    return AnnotationMetrics(
        total_cases=len(package.cases),
        labeled_cases=len(labeled),
        scorable_cases=count,
        coverage=round(len(labeled) / len(package.cases), 4),
        exact_agreement=round(exact / count, 4) if count else None,
        mean_ordinal_error=round(ordinal_error / count, 4) if count else None,
        high_risk_precision=(
            round(true_positive_high / predicted_high, 4) if predicted_high else None
        ),
        high_risk_recall=(
            round(true_positive_high / true_high, 4) if true_high else None
        ),
        top3_high_risk_precision=(
            round(top3_precision, 4) if top3_precision is not None else None
        ),
        uncertain_cases=sum(
            item.human_annotation.verdict == "uncertain" for item in labeled
        ),
        confusion=confusion,
    )


__all__ = [
    "AnnotationMetrics",
    "AnnotationPackage",
    "HumanAnnotation",
    "create_annotation_package",
    "evaluate_annotations",
    "select_annotation_cards",
]
