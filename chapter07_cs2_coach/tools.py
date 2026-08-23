"""确定性赛事分析工具：只计算事实，不让模型心算。"""

from __future__ import annotations

from collections.abc import Callable

from chapter07_cs2_coach.contact_analysis import compare_contact_outcomes
from chapter07_cs2_coach.models import Evidence, MatchRecord


DUST2_CALLOUTS = {
    "MidDoors": "中门",
    "UnderA": "A小下",
    "Middle": "中路",
    "LongA": "A大",
    "Hole": "B洞",
    "BombsiteB": "B包点",
    "ShortStairs": "A小楼梯",
    "BombsiteA": "A包点",
    "UpperTunnel": "B二层",
    "LowerTunnel": "B一层",
    "ARamp": "A斜坡",
    "CTSpawn": "警家",
    "Catwalk": "A小",
    "LongDoors": "A门",
    "BDoors": "B门",
}


def _location_label(match: MatchRecord, location: str) -> str:
    if match.map_name == "de_dust2" and location in DUST2_CALLOUTS:
        return f"{DUST2_CALLOUTS[location]}（{location}）"
    return location


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
    if total < 3:
        return [
            Evidence(
                finding="本场可识别的首轮交火样本不足，暂时不能判断首杀能力是否稳定。",
                round_numbers=sorted([*won, *lost]),
                metric=f"仅识别到 {total} 次首轮交火：{len(won)} 胜 {len(lost)} 负",
                severity="medium",
                suggestion="继续记录后续比赛，累计至少三次首轮交火后再判断趋势。",
            )
        ]
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


def analyze_engagement_decisions(match: MatchRecord) -> list[Evidence]:
    """基于死亡前局势快照，区分接战条件与最终是否完成补枪。"""

    isolated_advances = [
        item for item in match.engagements if item.classification == "isolated_advance"
    ]
    supported_untraded = [
        item
        for item in match.engagements
        if item.classification == "supported_contact" and not item.was_traded
    ]
    evidence: list[Evidence] = []
    if isolated_advances:
        average_distance = round(
            sum(item.nearest_teammate_distance or 0 for item in isolated_advances)
            / len(isolated_advances)
        )
        average_movement = round(
            sum(item.moved_distance_5s for item in isolated_advances)
            / len(isolated_advances)
        )
        flash_support = sum(
            item.effective_team_flashes_5s for item in isolated_advances
        )
        contexts = "；".join(
            f"R{item.round_number} {_location_label(match, item.location)} "
            f"{item.alive_teammates + 1}v{item.alive_enemies}"
            for item in isolated_advances[:4]
        )
        evidence.append(
            Evidence(
                finding="多次在缺少近距离队友支持时继续向交火区域移动，死亡后难以形成稳定补枪。",
                round_numbers=[item.round_number for item in isolated_advances],
                metric=(
                    f"{len(isolated_advances)} 次孤立推进死亡，最近队友平均约 "
                    f"{average_distance} 单位，五秒平均移动 {average_movement} 单位，"
                    f"团队有效闪白 {flash_support} 人次；{contexts}"
                ),
                severity="high" if len(isolated_advances) >= 2 else "medium",
                suggestion=(
                    "进入下一个交火区域前确认最近队友已缩短距离；若队友仍超过约 1000 单位，"
                    "先停下等同步或用道具迫使敌人转移准星。"
                ),
            )
        )
    if len(supported_untraded) >= 2:
        average_distance = round(
            sum(item.nearest_teammate_distance or 0 for item in supported_untraded)
            / len(supported_untraded)
        )
        contexts = "；".join(
            f"R{item.round_number} {_location_label(match, item.location)} "
            f"距队友 {item.nearest_teammate_distance}"
            for item in supported_untraded[:4]
        )
        evidence.append(
            Evidence(
                finding="部分死亡发生时附近已有队友，但最终没有完成补枪，问题更可能是接触节奏或视线不同步。",
                round_numbers=[item.round_number for item in supported_untraded],
                metric=(
                    f"{len(supported_untraded)} 次近距离支持下仍未补枪，平均距离约 "
                    f"{average_distance} 单位；{contexts}"
                ),
                severity="medium",
                suggestion=(
                    "接触前用一句口令或停顿半秒确认队友准星已经到位；两人尽量从能看到同一目标的"
                    "角度同步拉出，而不是只有空间距离接近。"
                ),
            )
        )
    contacts = compare_contact_outcomes(match.contact_episodes)
    initiated = contacts.first_damage_by_player
    received = contacts.first_damage_by_opponent
    if (
        initiated.resolved >= 3
        and received.resolved >= 3
        and initiated.kill_rate is not None
        and received.kill_rate is not None
        and initiated.kill_rate - received.kill_rate >= 0.15
    ):
        received_death_rounds = sorted(
            {
                item.round_number
                for item in match.contact_episodes
                if not item.first_damage_by_player and item.outcome == "death"
            }
        )
        evidence.append(
            Evidence(
                finding="完整交火样本显示，先取得有效伤害时的转化明显更好，被对手先手时更容易失去交火主动权。",
                round_numbers=received_death_rounds,
                metric=(
                    f"先造成伤害：{initiated.kills} 胜/{initiated.deaths} 负，"
                    f"转化率 {initiated.kill_rate:.1%}；被先造成伤害："
                    f"{received.kills} 胜/{received.deaths} 负，"
                    f"转化率 {received.kill_rate:.1%}；另有 "
                    f"{initiated.disengaged + received.disengaged} 次脱离未计入胜率"
                ),
                severity="medium",
                suggestion=(
                    "优先优化预瞄和信息获取；没有取得先手时先用掩体重置交火，"
                    "不要在血量与准星劣势下机械续枪。"
                ),
            )
        )
    ready = contacts.nearby_support_ready
    unready = contacts.nearby_support_unready
    if (
        ready.resolved >= 3
        and unready.resolved >= 3
        and ready.kill_rate is not None
        and unready.kill_rate is not None
        and ready.kill_rate - unready.kill_rate >= 0.2
    ):
        unready_death_rounds = sorted(
            {
                item.round_number
                for item in match.contact_episodes
                if item.nearest_teammate_distance is not None
                and item.nearest_teammate_distance <= 750
                and item.support_ready_teammates_proxy == 0
                and item.outcome == "death"
            }
        )
        evidence.append(
            Evidence(
                finding="队友空间距离近并不等于已经形成补枪；本场在队友朝向与烟雾代理未就绪时，交火结果明显更差。",
                round_numbers=unready_death_rounds,
                metric=(
                    f"补枪代理就绪：{ready.kills} 胜/{ready.deaths} 负，"
                    f"转化率 {ready.kill_rate:.1%}；未就绪："
                    f"{unready.kills} 胜/{unready.deaths} 负，"
                    f"转化率 {unready.kill_rate:.1%}"
                ),
                severity="medium",
                suggestion=(
                    "接触前除了看小地图距离，还要确认队友准星方向和烟雾线路；"
                    "队友尚未面向同一威胁时，先停顿或报点再同步拉出。"
                ),
            )
        )
    return evidence


ANALYSIS_TOOLS: dict[str, Callable[[MatchRecord], list[Evidence]]] = {
    "opening_duels": analyze_opening_duels,
    "tradeability": analyze_tradeability,
    "utility": analyze_utility,
    "economy": analyze_economy,
    "clutches": analyze_clutches,
    "engagements": analyze_engagement_decisions,
}
