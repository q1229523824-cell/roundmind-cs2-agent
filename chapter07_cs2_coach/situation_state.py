"""把 Demo 接战快照重建为稳定、可测试的局势状态。"""

from __future__ import annotations

from chapter07_cs2_coach.models import EngagementRecord, RoundSituationState


def build_situation_state(item: EngagementRecord) -> RoundSituationState:
    player_alive = item.alive_teammates + 1
    if item.alive_teammates == 0:
        manpower = "last_alive"
    elif player_alive > item.alive_enemies:
        manpower = "advantage"
    elif player_alive < item.alive_enemies:
        manpower = "disadvantage"
    else:
        manpower = "even"

    if item.alive_teammates == 0:
        support = "none"
    elif item.nearest_teammate_distance is None:
        support = "unknown"
    elif item.support_ready_teammates_proxy:
        support = "ready"
    elif item.nearest_teammate_distance <= 750:
        support = "near_unready"
    else:
        support = "distant"

    if item.bomb_state == "planted":
        objective = "bomb_planted"
        phase = "post_plant"
    elif item.bomb_state in {"defused", "exploded"}:
        objective = "round_settled"
        phase = "settled"
    else:
        objective = "default" if item.bomb_state == "not_planted" else "unknown"
        elapsed = item.round_elapsed_seconds
        phase = (
            "unknown"
            if elapsed is None
            else "opening"
            if elapsed < 25
            else "mid_round"
            if elapsed < 80
            else "late_round"
        )

    known = [
        item.round_elapsed_seconds is not None,
        item.bomb_state != "unknown",
        item.nearest_teammate_distance is not None or item.alive_teammates == 0,
        item.support_ready_teammates_proxy is not None or item.alive_teammates == 0,
        item.smoke_between_player_and_nearest_teammate is not None
        or item.alive_teammates == 0,
    ]
    completeness = round(sum(known) / len(known) * 100)
    tempo = "expanding" if item.moved_distance_5s >= 600 else "controlled"
    labels = [
        f"阶段:{phase}",
        f"人数:{manpower}",
        f"支援:{support}",
        f"目标:{objective}",
        f"节奏:{tempo}",
    ]
    return RoundSituationState(
        phase=phase,
        manpower=manpower,
        support=support,
        objective=objective,
        tempo=tempo,
        information_completeness=completeness,
        labels=labels,
    )


__all__ = ["build_situation_state"]
