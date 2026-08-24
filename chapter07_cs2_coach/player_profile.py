"""跨比赛聚合玩家交火画像，区分单场信号与重复习惯。"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from chapter07_cs2_coach.contact_analysis import (
    ContactOutcomeStats,
    compare_contact_outcomes,
    find_contact_hotspots,
)
from chapter07_cs2_coach.models import (
    MatchRecord,
    PlayerProfileResponse,
    ProfileFinding,
    ProfileRateSummary,
)
from chapter07_cs2_coach.quality_audit import MatchQualityAudit, audit_match


def _downgrade_confidence(value: str) -> str:
    return {"high": "medium", "medium": "low", "low": "low"}[value]


def _rate_summary(label: str, stats: ContactOutcomeStats) -> ProfileRateSummary:
    interval = stats.kill_rate_interval
    return ProfileRateSummary(
        label=label,
        total=stats.total,
        resolved=stats.resolved,
        kills=stats.kills,
        deaths=stats.deaths,
        disengaged=stats.disengaged,
        kill_rate=stats.kill_rate,
        smoothed_kill_rate=stats.smoothed_kill_rate,
        interval_low=interval[0] if interval else None,
        interval_high=interval[1] if interval else None,
    )


def _finding_confidence(
    *, supporting: int, eligible: int, pooled_resolved: int
) -> tuple[str, str]:
    consistency = supporting / eligible if eligible else 0
    if eligible >= 5 and consistency >= 0.75 and pooled_resolved >= 30:
        return "recurring", "high"
    if eligible >= 3 and consistency >= 2 / 3 and pooled_resolved >= 16:
        return "recurring", "medium"
    if eligible >= 2 and supporting >= 1:
        return "emerging", "low"
    return "single_match_signal", "low"


def _first_damage_finding(matches: list[MatchRecord]) -> ProfileFinding | None:
    eligible = 0
    supporting = 0
    for match in matches:
        comparison = compare_contact_outcomes(match.contact_episodes)
        own = comparison.first_damage_by_player
        opponent = comparison.first_damage_by_opponent
        if (
            own.resolved < 3
            or opponent.resolved < 3
            or own.smoothed_kill_rate is None
            or opponent.smoothed_kill_rate is None
        ):
            continue
        eligible += 1
        if own.smoothed_kill_rate - opponent.smoothed_kill_rate >= 0.12:
            supporting += 1
    if not eligible:
        return None
    contacts = [item for match in matches for item in match.contact_episodes]
    pooled = compare_contact_outcomes(contacts)
    own = pooled.first_damage_by_player
    opponent = pooled.first_damage_by_opponent
    status, confidence = _finding_confidence(
        supporting=supporting,
        eligible=eligible,
        pooled_resolved=own.resolved + opponent.resolved,
    )
    consistency = round(supporting / eligible, 4)
    title = (
        "先手伤害优势在多场比赛中重复出现"
        if status == "recurring"
        else "先手伤害优势正在形成跨场信号"
        if status == "emerging"
        else "本场出现先手伤害转化差异"
    )
    return ProfileFinding(
        key="first-damage-conversion",
        title=title if supporting else "尚未形成稳定先手差异",
        metric=(
            f"{supporting}/{eligible} 场满足差异阈值；聚合转化率："
            f"先造成伤害 {own.kill_rate:.1%}，被先造成伤害 {opponent.kill_rate:.1%}"
        ),
        supporting_matches=supporting,
        eligible_matches=eligible,
        consistency=consistency,
        status=status,
        confidence=confidence,
    )


def _support_finding(matches: list[MatchRecord]) -> ProfileFinding | None:
    eligible = 0
    supporting = 0
    for match in matches:
        comparison = compare_contact_outcomes(match.contact_episodes)
        ready = comparison.nearby_support_ready
        unready = comparison.nearby_support_unready
        if (
            ready.resolved < 3
            or unready.resolved < 3
            or ready.smoothed_kill_rate is None
            or unready.smoothed_kill_rate is None
        ):
            continue
        eligible += 1
        if ready.smoothed_kill_rate - unready.smoothed_kill_rate >= 0.15:
            supporting += 1
    if not eligible:
        return None
    contacts = [item for match in matches for item in match.contact_episodes]
    pooled = compare_contact_outcomes(contacts)
    ready = pooled.nearby_support_ready
    unready = pooled.nearby_support_unready
    status, confidence = _finding_confidence(
        supporting=supporting,
        eligible=eligible,
        pooled_resolved=ready.resolved + unready.resolved,
    )
    title = (
        "补枪准备度差异在多场比赛中重复出现"
        if status == "recurring"
        else "补枪准备度差异正在形成跨场信号"
        if status == "emerging"
        else "本场出现补枪准备度转化差异"
    )
    return ProfileFinding(
        key="support-readiness-conversion",
        title=title if supporting else "补枪准备度差异尚不稳定",
        metric=(
            f"{supporting}/{eligible} 场满足差异阈值；聚合转化率："
            f"就绪 {ready.kill_rate:.1%}，未就绪 {unready.kill_rate:.1%}"
        ),
        supporting_matches=supporting,
        eligible_matches=eligible,
        consistency=round(supporting / eligible, 4),
        status=status,
        confidence=confidence,
    )


def _hotspot_finding(matches: list[MatchRecord]) -> ProfileFinding | None:
    evaluated: dict[tuple[str, str, str], list[ContactOutcomeStats]] = defaultdict(list)
    for match in matches:
        for item in find_contact_hotspots(match.contact_episodes, min_resolved=3):
            evaluated[(match.map_name, item.side, item.location)].append(item.stats)
    candidates: list[tuple[tuple[str, str, str], int, int, int]] = []
    for key, stats in evaluated.items():
        supporting = sum(
            item.kill_rate is not None and item.kill_rate <= 0.45 for item in stats
        )
        if supporting:
            candidates.append(
                (key, supporting, len(stats), sum(item.resolved for item in stats))
            )
    if not candidates:
        return None
    (map_name, side, location), supporting, eligible, pooled_resolved = max(
        candidates,
        key=lambda item: (item[1], item[1] / item[2], item[3]),
    )
    status, confidence = _finding_confidence(
        supporting=supporting,
        eligible=eligible,
        pooled_resolved=pooled_resolved,
    )
    title = (
        f"{side} 方 {location} 是跨场重复出现的低转化交火区域"
        if status == "recurring"
        else f"{side} 方 {location} 正在形成跨场低转化信号"
        if status == "emerging"
        else f"本场 {side} 方 {location} 出现低转化交火信号"
    )
    return ProfileFinding(
        key=f"hotspot-{map_name}-{side}-{location}",
        title=title,
        metric=f"在 {supporting}/{eligible} 场存在可评估弱点位的比赛中出现",
        supporting_matches=supporting,
        eligible_matches=eligible,
        consistency=round(supporting / eligible, 4),
        status=status,
        confidence=confidence,
    )


def build_player_profile(
    matches: Iterable[MatchRecord],
    *,
    player_steamid: str,
    map_name: str | None = None,
    enforce_quality: bool = True,
) -> PlayerProfileResponse:
    selected_by_id = {
        match.match_id: match
        for match in matches
        if match.player_steamid == player_steamid
        and (map_name is None or match.map_name == map_name)
    }
    source_matches = list(selected_by_id.values())
    if not source_matches:
        raise KeyError("没有找到该 SteamID 对应的比赛画像数据。")
    audits: list[MatchQualityAudit] = []
    if enforce_quality:
        audits = [audit_match(match) for match in source_matches]
        accepted_ids = {
            item.match_id for item in audits if item.gate in {"pass", "review"}
        }
        selected = [
            match for match in source_matches if match.match_id in accepted_ids
        ]
        if not selected:
            raise KeyError("找到比赛，但均未通过数据质量门禁，无法生成可靠画像。")
    else:
        selected = source_matches
    contacts = [item for match in selected for item in match.contact_episodes]
    comparison = compare_contact_outcomes(contacts)
    findings = [
        item
        for item in (
            _first_damage_finding(selected),
            _support_finding(selected),
            _hotspot_finding(selected),
        )
        if item is not None
    ]
    match_count = len(selected)
    confidence = (
        "high"
        if match_count >= 5 and len(contacts) >= 150
        else "medium"
        if match_count >= 3 and len(contacts) >= 60
        else "low"
    )
    review_count = sum(item.gate == "review" for item in audits)
    rejected_count = sum(item.gate == "fail" for item in audits)
    if review_count:
        confidence = _downgrade_confidence(confidence)
        findings = [
            item.model_copy(
                update={"confidence": _downgrade_confidence(item.confidence)}
            )
            for item in findings
        ]
    quality_warnings = []
    for audit in audits:
        for warning in audit.warnings:
            message = f"{audit.match_id}: {warning}"
            if message not in quality_warnings:
                quality_warnings.append(message)
    return PlayerProfileResponse(
        player_name=selected[-1].player_name,
        player_steamid=player_steamid,
        map_name=map_name or "all_maps",
        match_count=match_count,
        round_count=sum(len(match.rounds) for match in selected),
        contact_count=len(contacts),
        rate_summaries=[
            _rate_summary("first_damage_by_player", comparison.first_damage_by_player),
            _rate_summary("first_damage_by_opponent", comparison.first_damage_by_opponent),
            _rate_summary("nearby_support_ready", comparison.nearby_support_ready),
            _rate_summary("nearby_support_unready", comparison.nearby_support_unready),
        ],
        findings=findings,
        confidence=confidence,
        source_match_count=len(source_matches),
        rejected_match_count=rejected_count,
        review_match_count=review_count,
        quality_score_average=(
            round(sum(item.quality_score for item in audits) / len(audits), 2)
            if audits
            else None
        ),
        quality_gate=(
            "review"
            if review_count or rejected_count
            else "pass"
            if audits
            else "not_evaluated"
        ),
        quality_warnings=quality_warnings[:20],
    )


__all__ = ["build_player_profile"]
