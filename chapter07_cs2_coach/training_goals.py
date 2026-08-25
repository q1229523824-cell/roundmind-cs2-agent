"""把画像弱点转成可跨比赛追踪的训练目标。"""

from __future__ import annotations

from collections.abc import Callable

from chapter07_cs2_coach.models import ContactEpisode, MatchRecord, TrainingGoal


def _status(
    baseline: float, latest: float | None, target: float, sample_size: int
) -> str:
    if sample_size < 8:
        return "insufficient_data"
    if latest is None:
        return "baseline"
    if latest <= target:
        return "achieved"
    if latest <= baseline - 0.05:
        return "improving"
    if latest >= baseline + 0.05:
        return "regressing"
    return "baseline"


def _death_rate(
    matches: list[MatchRecord], predicate: Callable[[ContactEpisode], bool]
) -> tuple[float | None, int]:
    episodes = [
        item
        for match in matches
        for item in match.contact_episodes
        if predicate(item) and item.outcome in {"kill", "death"}
    ]
    if not episodes:
        return None, 0
    return sum(item.outcome == "death" for item in episodes) / len(episodes), len(episodes)


def _goal(
    matches: list[MatchRecord],
    *,
    key: str,
    focus: str,
    metric: str,
    predicate: Callable[[ContactEpisode], bool],
) -> TrainingGoal | None:
    midpoint = max(1, len(matches) // 2)
    baseline, baseline_count = _death_rate(matches[:midpoint], predicate)
    overall, total_count = _death_rate(matches, predicate)
    latest, _ = _death_rate(matches[midpoint:], predicate) if len(matches) > 1 else (None, 0)
    if baseline is None or overall is None:
        return None
    target = max(0.0, baseline - 0.10)
    confidence = "high" if total_count >= 30 else "medium" if total_count >= 16 else "low"
    return TrainingGoal(
        key=key,
        focus=focus,
        metric=metric,
        baseline_value=round(baseline, 4),
        latest_value=round(latest, 4) if latest is not None else None,
        target_value=round(target, 4),
        direction="lower",
        sample_size=total_count,
        status=_status(baseline, latest, target, total_count),
        confidence=confidence,
    )


def build_training_goals(matches: list[MatchRecord]) -> list[TrainingGoal]:
    """生成最多三个带基线、目标和趋势的训练闭环。"""
    candidates = [
        _goal(
            matches,
            key="opponent-first-damage-survival",
            focus="被先手伤害后先脱离原枪线，再决定是否二次接触",
            metric="对手先造成伤害的已解决交火死亡率",
            predicate=lambda item: not item.first_damage_by_player,
        ),
        _goal(
            matches,
            key="support-unready-survival",
            focus="进入交火前确认队友具备真实补枪条件",
            metric="支援未就绪交火死亡率",
            predicate=lambda item: item.support_ready_teammates_proxy == 0,
        ),
        _goal(
            matches,
            key="rifle-contact-survival",
            focus="提高步枪交火中的生存与击杀转化",
            metric="步枪已解决交火死亡率",
            predicate=lambda item: item.weapon.lower() not in {"awp", "ssg08"},
        ),
    ]
    return [item for item in candidates if item is not None][:3]


__all__ = ["build_training_goals"]
