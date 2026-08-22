"""确定性赛事分析工具：只计算事实，不让模型心算。"""

from __future__ import annotations

from collections.abc import Callable

from chapter07_cs2_coach.models import Evidence, MatchRecord


def get_match_summary(match: MatchRecord) -> dict[str, int | float | str]:
    rounds = match.rounds
    deaths = sum(item.died for item in rounds)
    kills = sum(item.kills for item in rounds)
    assists = sum(item.assists for item in rounds)
    kast_rounds = sum(
        item.kills > 0 or item.assists > 0 or not item.died or item.was_traded
        for item in rounds
    )
    return {
        "player": match.player_name,
        "map": match.map_name,
        "score": f"{match.team_score}:{match.opponent_score}",
        "rounds": len(rounds),
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "adr": round(sum(item.damage for item in rounds) / len(rounds), 1),
        "kast_percent": round(kast_rounds / len(rounds) * 100, 1),
    }


def analyze_opening_duels(match: MatchRecord) -> list[Evidence]:
    won = [item.number for item in match.rounds if item.opening_duel == "won"]
    lost = [item.number for item in match.rounds if item.opening_duel == "lost"]
    total = len(won) + len(lost)
    if not total:
        return []
    rate = len(won) / total * 100
    if len(lost) >= 4 and rate < 45:
        return [
            Evidence(
                finding="首轮交火承担较多，但成功率偏低，容易让队伍过早进入人数劣势。",
                round_numbers=lost,
                metric=f"首杀对枪 {len(won)} 胜 {len(lost)} 负，成功率 {rate:.1f}%",
                severity="high",
                suggestion="进攻方优先要求队友给闪或保持可补枪距离；防守方首轮接触后减少重复 peek。",
            )
        ]
    return [
        Evidence(
            finding="首轮交火为队伍创造了稳定的人数优势。",
            round_numbers=won,
            metric=f"首杀对枪成功率 {rate:.1f}%",
            severity="positive",
            suggestion="保留当前首轮交火选择，同时复盘成功回合中的道具和队友距离。",
        )
    ]


def analyze_tradeability(match: MatchRecord) -> list[Evidence]:
    untraded = [
        item.number
        for item in match.rounds
        if item.died and not item.was_traded and not item.clutch_attempted
    ]
    deaths = sum(item.died for item in match.rounds)
    if not deaths:
        return []
    rate = len(untraded) / deaths * 100
    if len(untraded) >= 5:
        return [
            Evidence(
                finding="多数死亡没有形成及时补枪，站位距离或接触时机是本场最高优先级问题。",
                round_numbers=untraded,
                metric=f"{deaths} 次死亡中 {len(untraded)} 次未被补枪（{rate:.1f}%）",
                severity="high",
                suggestion="每次准备接触前先确认最近队友位置；把‘能否在两秒内被补枪’作为出手条件。",
            )
        ]
    return []


def analyze_utility(match: MatchRecord) -> list[Evidence]:
    rounds = len(match.rounds)
    useful = [
        item.number
        for item in match.rounds
        if item.utility_damage >= 20 or item.enemies_flashed >= 2
    ]
    avg_damage = sum(item.utility_damage for item in match.rounds) / rounds
    flashes = sum(item.enemies_flashed for item in match.rounds)
    severity = "medium" if avg_damage < 12 and flashes < rounds * 0.5 else "positive"
    finding = (
        "道具对交火的直接支持偏少，多次首轮接触缺少闪光或伤害铺垫。"
        if severity == "medium"
        else "道具能在部分关键回合为队伍创造有效交火条件。"
    )
    return [
        Evidence(
            finding=finding,
            round_numbers=useful,
            metric=f"场均道具伤害 {avg_damage:.1f}，共闪白敌人 {flashes} 次",
            severity=severity,
            suggestion="固定掌握每张常用地图的两颗进攻闪与两颗拖延道具，并记录是否真正帮助队友接敌。",
        )
    ]


def analyze_economy(match: MatchRecord) -> list[Evidence]:
    light_buy_deaths = [
        item.number
        for item in match.rounds
        if 1800 <= item.equipment_value < 4000 and item.died and not item.won
    ]
    if len(light_buy_deaths) < 2:
        return []
    return [
        Evidence(
            finding="多个非长枪局投入装备后仍快速阵亡，经济局打法与购买目标需要更统一。",
            round_numbers=light_buy_deaths,
            metric=f"{len(light_buy_deaths)} 个中等投入回合失利且阵亡",
            severity="medium",
            suggestion="购买前明确本回合是保下局经济、集中强起还是为队友起枪，避免个人半起后单独接触。",
        )
    ]


def analyze_clutches(match: MatchRecord) -> list[Evidence]:
    attempts = [item.number for item in match.rounds if item.clutch_attempted]
    wins = [item.number for item in match.rounds if item.clutch_won]
    if not attempts:
        return []
    return [
        Evidence(
            finding="部分击杀发生在低胜率残局，击杀数没有完全转化为回合胜利。",
            round_numbers=attempts,
            metric=f"残局 {len(attempts)} 次，获胜 {len(wins)} 次",
            severity="medium" if not wins else "positive",
            suggestion="残局先评估时间、拆包条件和逐个击破路线；时间不足时把保枪纳入决策。",
        )
    ]


ANALYSIS_TOOLS: dict[str, Callable[[MatchRecord], list[Evidence]]] = {
    "opening_duels": analyze_opening_duels,
    "tradeability": analyze_tradeability,
    "utility": analyze_utility,
    "economy": analyze_economy,
    "clutches": analyze_clutches,
}
