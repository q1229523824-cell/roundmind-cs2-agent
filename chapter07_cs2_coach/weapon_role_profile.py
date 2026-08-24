"""从完整交火样本生成武器、角色与被先手伤害弱点画像。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
import re

from chapter07_cs2_coach.contact_analysis import summarize_contacts
from chapter07_cs2_coach.models import (
    ContactEpisode,
    FirstDamageDisadvantageSegment,
    MatchRecord,
    RoleProfile,
    WeaponCategoryProfile,
)


SNIPERS = {"awp", "ssg08", "scar20", "g3sg1"}
RIFLES = {
    "ak47", "m4a1", "m4a1silencer", "m4a1_silencer", "famas", "galilar",
    "aug", "sg556",
}
SMGS = {"mac10", "mp9", "mp7", "mp5sd", "ump45", "p90", "bizon"}
PISTOLS = {
    "glock", "hkp2000", "usp_silencer", "p250", "fiveseven", "tec9",
    "cz75a", "deagle", "revolver", "elite",
}
SHOTGUNS = {"nova", "xm1014", "mag7", "sawedoff"}
LMGS = {"m249", "negev"}


def normalize_weapon_name(value: str) -> str:
    normalized = value.casefold().strip().replace("weapon_", "")
    return re.sub(r"[^a-z0-9_]", "", normalized)


def weapon_category(value: str) -> str:
    normalized = normalize_weapon_name(value)
    if normalized in SNIPERS:
        return "sniper"
    if normalized in RIFLES:
        return "rifle"
    if normalized in SMGS:
        return "smg"
    if normalized in PISTOLS:
        return "pistol"
    if normalized in SHOTGUNS:
        return "shotgun"
    if normalized in LMGS:
        return "lmg"
    return "other"


def _kill_rate(items: list[ContactEpisode]) -> tuple[int, float | None]:
    stats = summarize_contacts(items)
    return stats.resolved, stats.kill_rate


def build_weapon_profile(
    episodes: Iterable[ContactEpisode],
) -> list[WeaponCategoryProfile]:
    items = list(episodes)
    grouped: dict[str, list[ContactEpisode]] = defaultdict(list)
    for item in items:
        grouped[weapon_category(item.weapon)].append(item)
    profiles = []
    for category, category_items in grouped.items():
        stats = summarize_contacts(category_items)
        t_items = [item for item in category_items if item.side == "T"]
        ct_items = [item for item in category_items if item.side == "CT"]
        t_resolved, t_rate = _kill_rate(t_items)
        ct_resolved, ct_rate = _kill_rate(ct_items)
        profiles.append(
            WeaponCategoryProfile(
                category=category,
                contacts=stats.total,
                resolved=stats.resolved,
                kills=stats.kills,
                deaths=stats.deaths,
                disengaged=stats.disengaged,
                contact_share=round(stats.total / len(items), 4) if items else 0,
                kill_rate=stats.kill_rate,
                first_damage_rate=(
                    round(
                        sum(item.first_damage_by_player for item in category_items)
                        / len(category_items),
                        4,
                    )
                    if category_items
                    else None
                ),
                t_resolved=t_resolved,
                t_kill_rate=t_rate,
                ct_resolved=ct_resolved,
                ct_kill_rate=ct_rate,
            )
        )
    return sorted(profiles, key=lambda item: (-item.contacts, item.category))


def infer_role_profile(
    matches: Iterable[MatchRecord],
    weapon_profiles: list[WeaponCategoryProfile],
) -> RoleProfile:
    match_items = list(matches)
    total_contacts = sum(item.contacts for item in weapon_profiles)
    by_category = {item.category: item for item in weapon_profiles}
    sniper = by_category.get("sniper")
    rifle = by_category.get("rifle")
    sniper_contacts = sniper.contacts if sniper else 0
    sniper_share = sniper.contact_share if sniper else 0
    rifle_share = rifle.contact_share if rifle else 0
    rounds = [round_item for match in match_items for round_item in match.rounds]
    opening_participation = (
        sum(item.opening_duel != "none" for item in rounds) / len(rounds)
        if rounds
        else 0
    )
    common_evidence = [
        f"共 {len(match_items)} 场、{total_contacts} 次交火",
        f"狙击枪交火占比 {sniper_share:.1%}",
        f"步枪交火占比 {rifle_share:.1%}",
        f"首轮交火参与率 {opening_participation:.1%}",
    ]
    if total_contacts < 20:
        return RoleProfile(
            role="insufficient_evidence",
            confidence="low",
            evidence=common_evidence,
            caveats=["交火样本少于 20，暂不进行角色定型。"],
        )
    if sniper_contacts >= 15 and sniper_share >= 0.45:
        confidence = (
            "high" if len(match_items) >= 5 and sniper_contacts >= 40 else "medium"
        )
        return RoleProfile(
            role="primary_awper",
            confidence=confidence,
            evidence=common_evidence,
            caveats=["角色表示当前武器行为倾向，不等同于固定战队位置。"],
        )
    if sniper_contacts >= 8 and sniper_share >= 0.2:
        return RoleProfile(
            role="hybrid_awper",
            confidence="medium" if len(match_items) >= 3 else "low",
            evidence=common_evidence,
            caveats=["同时存在可评估的狙击枪和非狙击枪交火。"],
        )
    if rifle_share >= 0.5 and opening_participation >= 0.25:
        return RoleProfile(
            role="rifle_initiator",
            confidence="medium" if len(match_items) >= 3 else "low",
            evidence=common_evidence,
            caveats=["第一身位只是行为代理，无法从 Demo 单独确认队内战术分工。"],
        )
    if rifle_share >= 0.5:
        return RoleProfile(
            role="rifler",
            confidence="medium" if len(match_items) >= 3 else "low",
            evidence=common_evidence,
            caveats=["现有数据不足以进一步区分突破、补枪和自由人。"],
        )
    return RoleProfile(
        role="mixed",
        confidence="medium" if len(match_items) >= 3 else "low",
        evidence=common_evidence,
        caveats=["武器分布较分散，暂不强行归类为单一角色。"],
    )


def _distance_band(item: ContactEpisode) -> str | None:
    if item.opponent_distance is None:
        return None
    if item.opponent_distance < 500:
        return "close_<500"
    if item.opponent_distance <= 1200:
        return "medium_500_1200"
    return "long_>1200"


def build_first_damage_disadvantage_segments(
    episodes: Iterable[ContactEpisode],
    *,
    limit: int = 6,
) -> list[FirstDamageDisadvantageSegment]:
    items = list(episodes)
    dimensions: list[tuple[str, Callable[[ContactEpisode], str | None]]] = [
        ("weapon", lambda item: weapon_category(item.weapon)),
        ("side", lambda item: item.side),
        (
            "location",
            lambda item: None if item.location == "Unknown" else item.location,
        ),
        ("distance", _distance_band),
    ]
    candidates: list[FirstDamageDisadvantageSegment] = []
    for dimension, value_getter in dimensions:
        grouped: dict[str, list[ContactEpisode]] = defaultdict(list)
        for item in items:
            value = value_getter(item)
            if value:
                grouped[value].append(item)
        for value, group in grouped.items():
            own = [item for item in group if item.first_damage_by_player]
            opponent = [item for item in group if not item.first_damage_by_player]
            own_stats = summarize_contacts(own)
            opponent_stats = summarize_contacts(opponent)
            if own_stats.resolved < 3 or opponent_stats.resolved < 3:
                continue
            assert own_stats.kill_rate is not None
            assert opponent_stats.kill_rate is not None
            gap = own_stats.kill_rate - opponent_stats.kill_rate
            if gap < 0.15:
                continue
            minimum_sample = min(own_stats.resolved, opponent_stats.resolved)
            confidence = (
                "high"
                if minimum_sample >= 15
                else "medium"
                if minimum_sample >= 6
                else "low"
            )
            candidates.append(
                FirstDamageDisadvantageSegment(
                    dimension=dimension,
                    value=value,
                    own_first_resolved=own_stats.resolved,
                    own_first_kill_rate=own_stats.kill_rate,
                    opponent_first_resolved=opponent_stats.resolved,
                    opponent_first_kill_rate=opponent_stats.kill_rate,
                    conversion_gap=round(gap, 4),
                    confidence=confidence,
                )
            )
    return sorted(
        candidates,
        key=lambda item: (
            -item.conversion_gap,
            -(item.own_first_resolved + item.opponent_first_resolved),
            item.dimension,
            item.value,
        ),
    )[:limit]


__all__ = [
    "build_first_damage_disadvantage_segments",
    "build_weapon_profile",
    "infer_role_profile",
    "normalize_weapon_name",
    "weapon_category",
]
