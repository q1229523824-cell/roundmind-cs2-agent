"""从玩家自己的成功交火中检索失败样本的个性化基线。"""

from __future__ import annotations

from chapter07_cs2_coach.models import (
    ContactEpisode,
    MatchRecord,
    PersonalContactContrast,
)


def _ready(value: int | None) -> bool | None:
    if value is None:
        return None
    return value >= 1


def _similarity(death: ContactEpisode, success: ContactEpisode) -> int:
    if death.side != success.side or death.location != success.location:
        return -1
    score = 40
    if death.opponent_distance is not None and success.opponent_distance is not None:
        score += round(
            25
            * (
                1
                - min(
                    abs(death.opponent_distance - success.opponent_distance) / 1500,
                    1,
                )
            )
        )
    if death.first_damage_by_player == success.first_damage_by_player:
        score += 15
    death_ready = _ready(death.support_ready_teammates_proxy)
    success_ready = _ready(success.support_ready_teammates_proxy)
    if (
        death_ready is not None
        and success_ready is not None
        and death_ready == success_ready
    ):
        score += 10
    score += round(
        10
        * (
            1
            - min(
                abs(death.health_before_contact - success.health_before_contact) / 100,
                1,
            )
        )
    )
    return min(score, 100)


def _differences(death: ContactEpisode, success: ContactEpisode) -> list[str]:
    result: list[str] = []
    if death.first_damage_by_player != success.first_damage_by_player:
        result.append(
            "失败样本由对手先造成伤害，成功样本由玩家先造成伤害"
            if success.first_damage_by_player
            else "失败样本由玩家先造成伤害，成功样本反而由对手先造成伤害"
        )
    death_ready = _ready(death.support_ready_teammates_proxy)
    success_ready = _ready(success.support_ready_teammates_proxy)
    if death_ready != success_ready and None not in {death_ready, success_ready}:
        result.append(
            "失败样本没有补枪准备队友，成功样本至少有一名"
            if success_ready
            else "成功样本也没有补枪准备队友，不能把结果差异只归因于支援"
        )
    if death.player_facing_opponent != success.player_facing_opponent and None not in {
        death.player_facing_opponent,
        success.player_facing_opponent,
    }:
        result.append(
            "失败接触时未面向对手，成功接触时已完成预瞄"
            if success.player_facing_opponent
            else "成功样本也未提前面向对手，朝向不是唯一解释"
        )
    if (
        death.opponent_distance is not None
        and success.opponent_distance is not None
        and abs(death.opponent_distance - success.opponent_distance) >= 300
    ):
        result.append(
            f"交火距离由失败样本约 {death.opponent_distance} 单位变为"
            f"成功样本约 {success.opponent_distance} 单位"
        )
    health_difference = success.health_before_contact - death.health_before_contact
    if abs(health_difference) >= 20:
        result.append(
            f"成功样本接触前生命值高 {health_difference}"
            if health_difference > 0
            else f"成功样本接触前生命值反而低 {-health_difference}"
        )
    if not result:
        result.append("两次可观测条件非常接近，结果差异更可能来自首发命中、准星落点或短时机波动")
    return result


def _lesson(differences: list[str]) -> str:
    text = "；".join(differences)
    if "成功样本由玩家先造成伤害" in text:
        return "复用成功样本的预瞄和接触方式，先用信息或道具争取第一段有效伤害。"
    if "成功样本至少有一名" in text:
        return "复用成功样本的同步节奏，等至少一名队友朝向同一威胁且烟雾线路可用后再接触。"
    if "成功接触时已完成预瞄" in text:
        return "进入该点位前先把准星落到成功样本的威胁方向，再减少大角度临时修枪。"
    return "两次局势条件相近，优先对照录像中的准星落点、首发命中和拉出时机，而不是继续改动站位规则。"


def build_personal_contact_contrasts(
    match: MatchRecord,
    *,
    minimum_similarity: int = 65,
    limit: int = 6,
) -> list[PersonalContactContrast]:
    deaths = [item for item in match.contact_episodes if item.outcome == "death"]
    successes = [item for item in match.contact_episodes if item.outcome == "kill"]
    contrasts: list[PersonalContactContrast] = []
    for death in deaths:
        candidates = [
            (_similarity(death, success), success)
            for success in successes
            if success.side == death.side and success.location == death.location
        ]
        if not candidates:
            continue
        similarity, success = max(
            candidates,
            key=lambda item: (item[0], -abs(item[1].start_tick - death.start_tick)),
        )
        if similarity < minimum_similarity:
            continue
        differences = _differences(death, success)
        contrasts.append(
            PersonalContactContrast(
                death_round=death.round_number,
                death_tick=death.start_tick,
                success_round=success.round_number,
                success_tick=success.start_tick,
                side=death.side,
                location=death.location,
                similarity_score=similarity,
                differences=differences,
                lesson=_lesson(differences),
                confidence=(
                    "high" if similarity >= 85 else "medium" if similarity >= 75 else "low"
                ),
            )
        )
    return sorted(
        contrasts,
        key=lambda item: (-item.similarity_score, item.death_round, item.death_tick),
    )[:limit]


__all__ = ["build_personal_contact_contrasts"]
