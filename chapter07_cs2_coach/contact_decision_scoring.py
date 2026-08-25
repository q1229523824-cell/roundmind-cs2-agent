"""对全部交火做不泄漏结果的事前风险评分与候选动作比较。"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from chapter07_cs2_coach.models import (
    ContactCandidateAction,
    ContactDecisionCard,
    ContactEpisode,
    MatchRecord,
)

ActionName = Literal[
    "continue_contact",
    "disengage_reset",
    "wait_for_support",
    "create_utility_condition",
]


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _condition_score(episode: ContactEpisode) -> tuple[int, list[str], str]:
    """只读取接触开始前或第一段伤害瞬间已知的字段。"""
    score = 38
    factors: list[str] = []
    known = 0
    total = 4

    if episode.first_damage_by_player:
        score -= 12
        factors.append("玩家先造成第一段伤害，拥有短暂主动权")
    else:
        score += 18
        factors.append("对手先造成第一段伤害，继续原枪线风险上升")
    known += 1

    if episode.health_before_contact <= 35:
        score += 18
        factors.append(f"接触前仅 {episode.health_before_contact} HP，容错很低")
    elif episode.health_before_contact <= 60:
        score += 9
        factors.append(f"接触前 {episode.health_before_contact} HP，容错受限")
    else:
        score -= 3
        factors.append(f"接触前 {episode.health_before_contact} HP，仍有基础容错")
    known += 1

    if episode.support_ready_teammates_proxy is not None:
        known += 1
        if episode.support_ready_teammates_proxy >= 1:
            score -= 13
            factors.append("至少一名队友具备快速补枪代理条件")
        else:
            score += 12
            factors.append("没有队友具备快速补枪代理条件")
    elif episode.nearest_teammate_distance is not None:
        known += 1
        if episode.nearest_teammate_distance > 1500:
            score += 15
            factors.append("最近队友距离超过 1500 单位，支援明显偏远")
        elif episode.nearest_teammate_distance > 900:
            score += 8
            factors.append("最近队友距离超过 900 单位，补枪存在延迟")
        else:
            score -= 4
            factors.append("最近队友距离较近，但尚未验证其准星是否到位")
    else:
        factors.append("缺少队友距离与补枪准备信息")

    if episode.player_view_angle_error is not None:
        known += 1
        if episode.player_view_angle_error > 90:
            score += 14
            factors.append("接触时准星方向偏差超过 90°")
        elif episode.player_view_angle_error > 45:
            score += 7
            factors.append("接触时准星方向偏差超过 45°")
        else:
            score -= 5
            factors.append("接触时准星方向基本覆盖对手")
    elif episode.player_facing_opponent is not None:
        known += 1
        if episode.player_facing_opponent:
            score -= 5
            factors.append("接触时玩家面向对手")
        else:
            score += 12
            factors.append("接触时玩家未面向对手")
    else:
        factors.append("缺少接触瞬间准星方向信息")

    completeness = known / total
    confidence = "high" if completeness == 1 else "medium" if completeness >= 0.75 else "low"
    return _clamp(score), factors, confidence


def _preferred_action(episode: ContactEpisode) -> ActionName:
    support_ready = (episode.support_ready_teammates_proxy or 0) >= 1
    facing = episode.player_facing_opponent is not False
    if (
        episode.first_damage_by_player
        and episode.health_before_contact > 60
        and support_ready
        and facing
    ):
        return "continue_contact"
    if not episode.first_damage_by_player or episode.health_before_contact <= 60:
        return "disengage_reset"
    if episode.alive_teammates > 0 and not support_ready:
        return "wait_for_support"
    return "create_utility_condition"


def _candidate_actions(
    episode: ContactEpisode, base_risk: int, preferred: ActionName
) -> list[ContactCandidateAction]:
    opponent_first = not episode.first_damage_by_player
    low_health = episode.health_before_contact <= 60
    support_ready = (episode.support_ready_teammates_proxy or 0) >= 1

    risks: dict[ActionName, int] = {
        "continue_contact": _clamp(base_risk + (10 if opponent_first or low_health else 0)),
        "disengage_reset": _clamp(base_risk - (24 if opponent_first or low_health else 8)),
        "wait_for_support": _clamp(base_risk - (20 if not support_ready else 5)),
        "create_utility_condition": _clamp(base_risk - 17),
    }
    # 推荐动作表达当前最可执行选择，并保证它在本卡候选中拥有最低预测风险。
    risks[preferred] = min(risks.values())
    rows = [
        ContactCandidateAction(
            action="continue_contact",
            label="继续当前接触",
            risk_score=risks["continue_contact"],
            rationale="保持当前枪线继续完成交火；只有在先手、血量和支援条件同时较好时才优先。",
            recommended=preferred == "continue_contact",
        ),
        ContactCandidateAction(
            action="disengage_reset",
            label="脱离并重置枪线",
            risk_score=risks["disengage_reset"],
            rationale="先用掩体、横移或高度变化中断对手预瞄，再决定是否二次接触。",
            recommended=preferred == "disengage_reset",
        ),
    ]
    if episode.alive_teammates > 0:
        rows.append(
            ContactCandidateAction(
                action="wait_for_support",
                label="等待支援条件",
                risk_score=risks["wait_for_support"],
                rationale="延迟接触，等队友距离和准星满足快速补枪条件后再同步。",
                assumptions=["队友仍存活且能够形成同一交火窗口"],
                recommended=preferred == "wait_for_support",
            )
        )
    rows.append(
        ContactCandidateAction(
            action="create_utility_condition",
            label="先创造道具条件",
            risk_score=risks["create_utility_condition"],
            rationale="用烟、闪或燃烧弹切断一条枪线，再进入更可控的二次接触。",
            assumptions=["玩家或队友仍有合适道具，且有施放时间"],
            recommended=preferred == "create_utility_condition",
        )
    )
    return rows


def score_contact_decision(episode: ContactEpisode) -> ContactDecisionCard:
    """评分中不使用 outcome、伤害结果、持续时间或结束 Tick。"""
    risk, factors, confidence = _condition_score(episode)
    preferred = _preferred_action(episode)
    return ContactDecisionCard(
        round_number=episode.round_number,
        tick=episode.start_tick,
        location=episode.location,
        side=episode.side,
        observed_outcome=episode.outcome,
        weapon=episode.weapon,
        first_damage_by_player=episode.first_damage_by_player,
        condition_risk_score=risk,
        risk_level="high" if risk >= 65 else "medium" if risk >= 40 else "low",
        factors=factors,
        candidate_actions=_candidate_actions(episode, risk, preferred),
        preferred_action=preferred,
        confidence=confidence,
    )


def score_all_contacts(match: MatchRecord) -> list[ContactDecisionCard]:
    return [score_contact_decision(item) for item in match.contact_episodes]


def build_contact_decision_cards(
    match: MatchRecord, *, limit: int = 12
) -> list[ContactDecisionCard]:
    """输出有界且结果多样的代表卡；底层仍对所有交火完成评分。"""
    if limit <= 0:
        return []
    cards = score_all_contacts(match)
    groups: dict[str, list[ContactDecisionCard]] = defaultdict(list)
    for card in cards:
        groups[card.observed_outcome].append(card)
    for group in groups.values():
        group.sort(key=lambda item: (-item.condition_risk_score, item.round_number, item.tick))

    selected: list[ContactDecisionCard] = []
    seen: set[tuple[int, int]] = set()
    for outcome in ("kill", "death", "disengaged"):
        for card in groups[outcome][:2]:
            if len(selected) >= limit:
                break
            selected.append(card)
            seen.add((card.round_number, card.tick))
    remaining = sorted(
        cards,
        key=lambda item: (-item.condition_risk_score, item.round_number, item.tick),
    )
    for card in remaining:
        key = (card.round_number, card.tick)
        if key in seen:
            continue
        selected.append(card)
        seen.add(key)
        if len(selected) >= limit:
            break
    return selected


__all__ = [
    "build_contact_decision_cards",
    "score_all_contacts",
    "score_contact_decision",
]
