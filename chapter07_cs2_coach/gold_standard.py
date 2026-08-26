"""Demo 金标准、字段级差异和解析准确率报告。"""

from __future__ import annotations

import platform
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from chapter07_cs2_coach import demo_parser
from chapter07_cs2_coach.models import MatchRecord


PARSER_CONTRACT_VERSION = "roundmind.demo-parser.v1"


class ParserProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parser_contract: Literal["roundmind.demo-parser.v1"] = PARSER_CONTRACT_VERSION
    parser_source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    demoparser2_version: str
    python_version: str


class RoundKeyFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1, le=100)
    side: Literal["T", "CT"]
    won: bool
    kills: int = Field(ge=0, le=5)
    assists: int = Field(ge=0, le=5)
    died: bool
    opening_duel: Literal["won", "lost", "none"]


class MatchKeyFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    map_name: str
    team_score: int = Field(ge=0, le=100)
    opponent_score: int = Field(ge=0, le=100)
    round_count: int = Field(ge=1, le=100)
    kills: int = Field(ge=0)
    deaths: int = Field(ge=0)
    assists: int = Field(ge=0)
    opening_wins: int = Field(ge=0)
    opening_losses: int = Field(ge=0)
    rounds: list[RoundKeyFacts] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_totals(self) -> "MatchKeyFacts":
        if self.round_count != len(self.rounds):
            raise ValueError("round_count 必须等于 rounds 数量。")
        if self.team_score + self.opponent_score != self.round_count:
            raise ValueError("双方比分之和必须等于回合数。")
        return self


class DemoGoldStandard(BaseModel):
    """人工核对文件；draft 不能默认参与发布门禁。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.demo-gold.v1"] = "roundmind.demo-gold.v1"
    status: Literal["draft", "verified"] = "draft"
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{16}$")
    player_ref: str = Field(pattern=r"^player_[a-f0-9]{12}$")
    baseline_parser: ParserProvenance
    expected: MatchKeyFacts
    verification_notes: list[str] = Field(default_factory=list, max_length=20)


class FieldComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    expected: str | int | bool
    actual: str | int | bool | None
    matched: bool
    critical: bool = False


class AccuracyMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matched: int = Field(ge=0)
    total: int = Field(ge=0)
    accuracy: float = Field(ge=0, le=1)


class DemoRegressionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.demo-regression.v1"] = (
        "roundmind.demo-regression.v1"
    )
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{16}$")
    gold_status: Literal["draft", "verified"]
    passed: bool
    parser_version_changed: bool
    baseline_parser: ParserProvenance
    current_parser: ParserProvenance
    overall: AccuracyMetric
    critical: AccuracyMetric
    round_level: AccuracyMetric
    comparisons: list[FieldComparison]


def current_parser_provenance() -> ParserProvenance:
    source = Path(demo_parser.__file__).read_bytes()
    try:
        parser_package_version = version("demoparser2")
    except PackageNotFoundError:
        parser_package_version = "not-installed"
    return ParserProvenance(
        parser_source_sha256=sha256(source).hexdigest(),
        demoparser2_version=parser_package_version,
        python_version=platform.python_version(),
    )


def _player_ref(match: MatchRecord) -> str:
    identity = match.player_steamid or match.player_name
    digest = sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"player_{digest}"


def _source_fingerprint(match: MatchRecord) -> str:
    identity = f"{match.match_id}|{match.player_steamid or match.player_name}"
    return sha256(identity.encode("utf-8")).hexdigest()[:16]


def extract_key_facts(match: MatchRecord) -> MatchKeyFacts:
    rounds = [
        RoundKeyFacts(
            number=item.number,
            side=item.side,
            won=item.won,
            kills=item.kills,
            assists=item.assists,
            died=item.died,
            opening_duel=item.opening_duel,
        )
        for item in sorted(match.rounds, key=lambda row: row.number)
    ]
    return MatchKeyFacts(
        map_name=match.map_name,
        team_score=match.team_score,
        opponent_score=match.opponent_score,
        round_count=len(rounds),
        kills=sum(item.kills for item in rounds),
        deaths=sum(item.died for item in rounds),
        assists=sum(item.assists for item in rounds),
        opening_wins=sum(item.opening_duel == "won" for item in rounds),
        opening_losses=sum(item.opening_duel == "lost" for item in rounds),
        rounds=rounds,
    )


def create_gold_draft(match: MatchRecord) -> DemoGoldStandard:
    return DemoGoldStandard(
        source_fingerprint=_source_fingerprint(match),
        player_ref=_player_ref(match),
        baseline_parser=current_parser_provenance(),
        expected=extract_key_facts(match),
        verification_notes=[
            "这是自动生成的草稿；请对照游戏结算页或可信 Demo 工具核对后将 status 改为 verified。"
        ],
    )


def _metric(rows: list[FieldComparison]) -> AccuracyMetric:
    matched = sum(item.matched for item in rows)
    total = len(rows)
    return AccuracyMetric(
        matched=matched,
        total=total,
        accuracy=round(matched / total, 4) if total else 0,
    )


def compare_with_gold(
    gold: DemoGoldStandard,
    actual_match: MatchRecord,
    *,
    allow_draft: bool = False,
) -> DemoRegressionReport:
    if gold.status != "verified" and not allow_draft:
        raise ValueError("金标准仍是 draft，人工核对后才能用于正式准确率门禁。")
    if gold.source_fingerprint != _source_fingerprint(actual_match):
        raise ValueError("当前 Demo 或玩家与这份金标准不匹配。")

    actual = extract_key_facts(actual_match)
    comparisons: list[FieldComparison] = []
    critical_fields = [
        "map_name",
        "team_score",
        "opponent_score",
        "round_count",
        "kills",
        "deaths",
        "assists",
        "opening_wins",
        "opening_losses",
    ]
    for name in critical_fields:
        expected_value = getattr(gold.expected, name)
        actual_value = getattr(actual, name)
        comparisons.append(
            FieldComparison(
                path=name,
                expected=expected_value,
                actual=actual_value,
                matched=expected_value == actual_value,
                critical=True,
            )
        )

    actual_rounds = {item.number: item for item in actual.rounds}
    for expected_round in gold.expected.rounds:
        actual_round = actual_rounds.get(expected_round.number)
        for name in ("side", "won", "kills", "assists", "died", "opening_duel"):
            expected_value = getattr(expected_round, name)
            actual_value = getattr(actual_round, name) if actual_round else None
            comparisons.append(
                FieldComparison(
                    path=f"rounds.{expected_round.number}.{name}",
                    expected=expected_value,
                    actual=actual_value,
                    matched=expected_value == actual_value,
                )
            )

    overall = _metric(comparisons)
    critical_rows = [item for item in comparisons if item.critical]
    round_rows = [item for item in comparisons if item.path.startswith("rounds.")]
    critical = _metric(critical_rows)
    current = current_parser_provenance()
    return DemoRegressionReport(
        source_fingerprint=gold.source_fingerprint,
        gold_status=gold.status,
        passed=critical.accuracy == 1 and overall.accuracy >= 0.98,
        parser_version_changed=(
            gold.baseline_parser.parser_source_sha256
            != current.parser_source_sha256
            or gold.baseline_parser.demoparser2_version
            != current.demoparser2_version
        ),
        baseline_parser=gold.baseline_parser,
        current_parser=current,
        overall=overall,
        critical=critical,
        round_level=_metric(round_rows),
        comparisons=comparisons,
    )


__all__ = [
    "DemoGoldStandard",
    "DemoRegressionReport",
    "MatchKeyFacts",
    "ParserProvenance",
    "compare_with_gold",
    "create_gold_draft",
    "current_parser_provenance",
    "extract_key_facts",
]
