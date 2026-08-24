"""对解析后的比赛事实做确定性质量审计，不把解析缺失误当成玩家问题。"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from chapter07_cs2_coach.models import MatchRecord


class QualityCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    status: Literal["pass", "warning", "fail"]
    observed: str
    expected: str
    message: str


class MatchQualityAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str
    map_name: str
    player_steamid: str | None
    quality_score: int = Field(ge=0, le=100)
    gate: Literal["pass", "review", "fail"]
    checks: list[QualityCheck]
    warnings: list[str]


class BatchQualityAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.quality.v1"] = "roundmind.quality.v1"
    match_count: int = Field(ge=0)
    passed: int = Field(ge=0)
    needs_review: int = Field(ge=0)
    failed: int = Field(ge=0)
    average_score: float = Field(ge=0, le=100)
    audits: list[MatchQualityAudit]


def _coverage_check(
    key: str,
    *,
    captured: int,
    expected: int,
    label: str,
) -> QualityCheck:
    if expected == 0:
        return QualityCheck(
            key=key,
            status="pass",
            observed="无目标事件",
            expected="无目标事件时无需抽取",
            message=f"本场没有玩家{label}，该项不参与扣分。",
        )
    ratio = captured / expected
    status: Literal["pass", "warning", "fail"]
    if ratio >= 1:
        status = "pass"
    elif ratio >= 0.9:
        status = "warning"
    else:
        status = "fail"
    return QualityCheck(
        key=key,
        status=status,
        observed=f"{captured}/{expected} ({ratio:.1%})",
        expected="100%",
        message=f"{label}事件应能在结构化接战数据中逐一追溯。",
    )


def _rate_check(
    key: str,
    *,
    count: int,
    total: int,
    warning_above: float,
    fail_above: float,
    label: str,
) -> QualityCheck:
    rate = count / total if total else 0.0
    status: Literal["pass", "warning", "fail"] = "pass"
    if rate > fail_above:
        status = "fail"
    elif rate > warning_above:
        status = "warning"
    return QualityCheck(
        key=key,
        status=status,
        observed=f"{count}/{total} ({rate:.1%})" if total else "0/0 (0.0%)",
        expected=f"不高于 {warning_above:.0%}",
        message=label,
    )


def audit_match(match: MatchRecord) -> MatchQualityAudit:
    """检查覆盖率、重复事件和关键上下文完整性。"""

    expected_kills = sum(item.kills for item in match.rounds)
    expected_deaths = sum(item.died for item in match.rounds)
    captured_kills = sum(item.outcome == "kill" for item in match.contact_episodes)
    captured_deaths = sum(item.outcome == "death" for item in match.contact_episodes)
    episode_keys = [
        (item.round_number, item.start_tick, item.end_tick, item.outcome)
        for item in match.contact_episodes
    ]
    duplicate_count = sum(count - 1 for count in Counter(episode_keys).values())
    unknown_locations = sum(
        item.location.casefold() in {"unknown", "未知", ""}
        for item in match.contact_episodes
    )
    resolved = [
        item for item in match.contact_episodes if item.outcome in {"kill", "death"}
    ]
    missing_distance = sum(item.opponent_distance is None for item in resolved)
    missing_angle = sum(item.player_view_angle_error is None for item in resolved)
    missing_support = sum(
        item.alive_teammates > 0 and item.support_ready_teammates_proxy is None
        for item in resolved
    )
    missing_any_context = sum(
        item.opponent_distance is None
        or item.player_view_angle_error is None
        or (
            item.alive_teammates > 0
            and item.support_ready_teammates_proxy is None
        )
        for item in resolved
    )

    checks = [
        _coverage_check(
            "contact_kill_coverage",
            captured=captured_kills,
            expected=expected_kills,
            label="击杀",
        ),
        _coverage_check(
            "contact_death_coverage",
            captured=captured_deaths,
            expected=expected_deaths,
            label="死亡",
        ),
        _coverage_check(
            "death_snapshot_coverage",
            captured=len(match.engagements),
            expected=expected_deaths,
            label="死亡局势快照",
        ),
        _rate_check(
            "duplicate_contact_rate",
            count=duplicate_count,
            total=len(episode_keys),
            warning_above=0,
            fail_above=0.05,
            label="重复交火会放大某类习惯，必须先去重再生成建议。",
        ),
        _rate_check(
            "unknown_location_rate",
            count=unknown_locations,
            total=len(match.contact_episodes),
            warning_above=0.2,
            fail_above=0.5,
            label="点位缺失会降低地图战术建议的可信度。",
        ),
    ]
    context_rate = missing_any_context / len(resolved) if resolved else 0.0
    context_status: Literal["pass", "warning", "fail"] = "pass"
    if context_rate > 0.5:
        context_status = "fail"
    elif context_rate > 0.2:
        context_status = "warning"
    checks.append(
        QualityCheck(
            key="resolved_context_missing_rate",
            status=context_status,
            observed=(
                f"任一缺失 {missing_any_context}/{len(resolved)} ({context_rate:.1%})；"
                f"距离 {missing_distance}，朝向 {missing_angle}，支援 {missing_support}"
            ),
            expected="任一缺失不高于 20%",
            message="缺少距离、朝向或支援代理时，局势判断只能降低置信度。",
        )
    )
    if not match.player_steamid:
        checks.append(
            QualityCheck(
                key="stable_player_identity",
                status="warning",
                observed="缺少 SteamID",
                expected="存在 SteamID",
                message="无法稳定聚合同名玩家的跨场画像。",
            )
        )
    else:
        checks.append(
            QualityCheck(
                key="stable_player_identity",
                status="pass",
                observed="SteamID 已记录",
                expected="存在 SteamID",
                message="可安全用于跨场去重和玩家画像。",
            )
        )

    score = max(
        0,
        100
        - 20 * sum(item.status == "fail" for item in checks)
        - 7 * sum(item.status == "warning" for item in checks),
    )
    if any(item.status == "fail" for item in checks):
        gate: Literal["pass", "review", "fail"] = "fail"
    elif any(item.status == "warning" for item in checks):
        gate = "review"
    else:
        gate = "pass"
    warnings = [item.message for item in checks if item.status != "pass"]
    return MatchQualityAudit(
        match_id=match.match_id,
        map_name=match.map_name,
        player_steamid=match.player_steamid,
        quality_score=score,
        gate=gate,
        checks=checks,
        warnings=warnings,
    )


def audit_matches(matches: list[MatchRecord]) -> BatchQualityAudit:
    audits = [audit_match(match) for match in matches]
    return BatchQualityAudit(
        match_count=len(audits),
        passed=sum(item.gate == "pass" for item in audits),
        needs_review=sum(item.gate == "review" for item in audits),
        failed=sum(item.gate == "fail" for item in audits),
        average_score=(
            round(sum(item.quality_score for item in audits) / len(audits), 2)
            if audits
            else 0
        ),
        audits=audits,
    )


__all__ = [
    "BatchQualityAudit",
    "MatchQualityAudit",
    "QualityCheck",
    "audit_match",
    "audit_matches",
]
