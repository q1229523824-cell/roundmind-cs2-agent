"""逐回合接战风险评分。

分数只表达当前可观测条件下的风险，不把“死亡”直接等同于“错误决策”。
"""

from __future__ import annotations

from chapter07_cs2_coach.knowledge_base import retrieve_for_engagement
from chapter07_cs2_coach.models import DecisionCard, EngagementRecord, MatchRecord
from chapter07_cs2_coach.tools import DUST2_CALLOUTS


BASE_RISK = {
    "isolated_advance": 52,
    "isolated_contact": 36,
    "supported_contact": 28,
    "uncertain_support": 34,
    "last_alive": 18,
}


def _location_label(match: MatchRecord, location: str) -> str:
    if match.map_name == "de_dust2" and location in DUST2_CALLOUTS:
        return f"{DUST2_CALLOUTS[location]}（{location}）"
    return location


def score_engagement(match: MatchRecord, item: EngagementRecord) -> DecisionCard:
    score = BASE_RISK[item.classification]
    factors: list[str] = []
    confidence = "high"

    distance = item.nearest_teammate_distance
    if item.alive_teammates == 0:
        factors.append("当时已无存活队友，不能用补枪条件评价")
    elif distance is None:
        score += 8
        confidence = "low"
        factors.append("缺少最近队友距离，支援条件不完整")
    elif distance > 1500:
        score += 20
        factors.append(f"最近队友约 {distance} 单位，明显超出稳定补枪距离")
    elif distance > 1000:
        score += 14
        factors.append(f"最近队友约 {distance} 单位，补枪风险较高")
    elif distance > 750:
        score += 7
        factors.append(f"最近队友约 {distance} 单位，支援存在延迟")
    else:
        score -= 8
        factors.append(f"最近队友约 {distance} 单位，空间距离具备支援可能")

    smoke_between = item.smoke_between_player_and_nearest_teammate
    if smoke_between is True:
        score += 12
        confidence = "medium"
        factors.append("活跃烟雾可能切断玩家与最近队友的补枪线路")
    elif smoke_between is None and item.nearby_support:
        confidence = "medium"
        factors.append("队友虽近，但缺少烟雾遮挡数据，无法确认真实补枪视线")
    elif item.active_smokes_nearby:
        factors.append(
            f"附近识别到 {item.active_smokes_nearby} 颗活跃烟雾，"
            "未落在最近队友连线代理上"
        )

    if item.moved_distance_5s >= 600:
        score += 10
        factors.append(f"死亡前五秒移动 {item.moved_distance_5s} 单位，持续进入新空间")
    elif item.moved_distance_5s >= 300:
        score += 5
        factors.append(f"死亡前五秒移动 {item.moved_distance_5s} 单位，接触前仍在推进")
    else:
        factors.append(f"死亡前五秒移动 {item.moved_distance_5s} 单位，未见明显强行推进")

    if item.effective_team_flashes_5s == 0 and item.classification != "last_alive":
        score += 7
        factors.append("接战前五秒没有识别到团队有效闪光")
    elif item.effective_team_flashes_5s:
        score -= min(item.effective_team_flashes_5s * 3, 9)
        factors.append(f"接战前五秒有 {item.effective_team_flashes_5s} 次团队有效闪光")

    player_side_alive = item.alive_teammates + 1
    if player_side_alive > item.alive_enemies and not item.was_traded:
        score += 8
        factors.append(f"当时 {player_side_alive}v{item.alive_enemies} 人数占优但死亡未被补枪")
    elif item.was_traded:
        score -= 12
        factors.append("死亡后完成补枪，接战具备一定交换价值")

    if item.bomb_state == "planted":
        timing = (
            f"，已下包约 {item.seconds_since_bomb_plant:g} 秒"
            if item.seconds_since_bomb_plant is not None
            else ""
        )
        factors.append(
            f"炸弹已在 {item.bombsite or '未知'} 点安放{timing}，"
            "需要按回防/守包语境复核"
        )
    elif item.bomb_state in {"defused", "exploded"}:
        factors.append("该快照位于炸弹结算阶段附近，常规接战评分仅供复核")

    if item.round_elapsed_seconds is not None:
        factors.append(f"快照距冻结时间结束约 {item.round_elapsed_seconds:g} 秒")

    score = max(0, min(round(score), 100))
    risk_level = "high" if score >= 70 else "medium" if score >= 40 else "low"
    verdict = "high_risk" if risk_level == "high" else "review" if risk_level == "medium" else "reasonable"
    if confidence == "high" and item.classification == "uncertain_support":
        confidence = "medium"

    actions = {
        "isolated_advance": "进入下一交火区前先等队友缩短距离，或用闪光、烟雾隔离枪线后再同步接触。",
        "isolated_contact": "先确认队友能看到同一目标；无法形成补枪时应控住现有空间而非继续扩大接触。",
        "supported_contact": "距离已经接近，重点复盘双方准星、视线与拉出时机是否真正同步。",
        "uncertain_support": "当前数据不足以下定论，优先回看该回合录像并确认烟雾遮挡与队友视线。",
        "last_alive": "这是无队友支援的残局场景，应结合时间、炸弹与已知敌人位置单独评价。",
    }
    references = retrieve_for_engagement(match, item)
    situation = (
        f"{item.side} 方 · {_location_label(match, item.location)} · "
        f"{player_side_alive}v{item.alive_enemies} · {item.weapon}"
    )
    return DecisionCard(
        round_number=item.round_number,
        tick=item.tick,
        location=_location_label(match, item.location),
        side=item.side,
        classification=item.classification,
        risk_score=score,
        risk_level=risk_level,
        verdict=verdict,
        situation=situation,
        factors=factors,
        better_action=actions[item.classification],
        knowledge_ids=[ref.knowledge_id for ref in references],
        confidence=confidence,
    )


def build_decision_cards(match: MatchRecord) -> list[DecisionCard]:
    cards = [score_engagement(match, item) for item in match.engagements]
    return sorted(cards, key=lambda card: (-card.risk_score, card.round_number))


__all__ = ["build_decision_cards", "score_engagement"]
