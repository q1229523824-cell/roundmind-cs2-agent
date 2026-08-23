"""比较完整交火样本，减少只观察死亡回合造成的结果偏差。"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from chapter07_cs2_coach.models import ContactEpisode


@dataclass(frozen=True)
class ContactOutcomeStats:
    total: int
    kills: int
    deaths: int
    disengaged: int

    @property
    def resolved(self) -> int:
        return self.kills + self.deaths

    @property
    def kill_rate(self) -> float | None:
        if not self.resolved:
            return None
        return round(self.kills / self.resolved, 4)

    @property
    def smoothed_kill_rate(self) -> float | None:
        if not self.resolved:
            return None
        return round((self.kills + 1) / (self.resolved + 2), 4)

    @property
    def kill_rate_interval(self) -> tuple[float, float] | None:
        """二项比例的 95% Wilson 区间，小样本时不会给出虚假精度。"""

        if not self.resolved:
            return None
        z = 1.96
        n = self.resolved
        proportion = self.kills / n
        denominator = 1 + z * z / n
        center = (proportion + z * z / (2 * n)) / denominator
        margin = (
            z
            * math.sqrt(
                proportion * (1 - proportion) / n + z * z / (4 * n * n)
            )
            / denominator
        )
        return round(max(0.0, center - margin), 4), round(
            min(1.0, center + margin), 4
        )

    @property
    def evidence_strength(self) -> str:
        if self.resolved < 8:
            return "low"
        if self.resolved < 20:
            return "medium"
        return "high"


@dataclass(frozen=True)
class ContactComparison:
    all_contacts: ContactOutcomeStats
    first_damage_by_player: ContactOutcomeStats
    first_damage_by_opponent: ContactOutcomeStats
    nearby_support_ready: ContactOutcomeStats
    nearby_support_unready: ContactOutcomeStats


@dataclass(frozen=True)
class ContactCoverage:
    expected_kills: int
    captured_kills: int
    expected_deaths: int
    captured_deaths: int

    @property
    def kill_coverage(self) -> float | None:
        if not self.expected_kills:
            return None
        return round(self.captured_kills / self.expected_kills, 4)

    @property
    def death_coverage(self) -> float | None:
        if not self.expected_deaths:
            return None
        return round(self.captured_deaths / self.expected_deaths, 4)


@dataclass(frozen=True)
class ContactHotspot:
    side: str
    location: str
    stats: ContactOutcomeStats


def summarize_contacts(episodes: Iterable[ContactEpisode]) -> ContactOutcomeStats:
    items = list(episodes)
    return ContactOutcomeStats(
        total=len(items),
        kills=sum(item.outcome == "kill" for item in items),
        deaths=sum(item.outcome == "death" for item in items),
        disengaged=sum(item.outcome == "disengaged" for item in items),
    )


def compare_contact_outcomes(
    episodes: Iterable[ContactEpisode],
) -> ContactComparison:
    items = list(episodes)
    nearby = [
        item
        for item in items
        if item.nearest_teammate_distance is not None
        and item.nearest_teammate_distance <= 750
        and item.support_ready_teammates_proxy is not None
    ]
    return ContactComparison(
        all_contacts=summarize_contacts(items),
        first_damage_by_player=summarize_contacts(
            item for item in items if item.first_damage_by_player
        ),
        first_damage_by_opponent=summarize_contacts(
            item for item in items if not item.first_damage_by_player
        ),
        nearby_support_ready=summarize_contacts(
            item for item in nearby if (item.support_ready_teammates_proxy or 0) >= 1
        ),
        nearby_support_unready=summarize_contacts(
            item for item in nearby if item.support_ready_teammates_proxy == 0
        ),
    )


def evaluate_contact_coverage(
    expected_kills: int,
    expected_deaths: int,
    episodes: Iterable[ContactEpisode],
) -> ContactCoverage:
    """用回合总数检查交火抽取覆盖率，不把覆盖率冒充策略准确率。"""

    items = list(episodes)
    return ContactCoverage(
        expected_kills=expected_kills,
        captured_kills=sum(item.outcome == "kill" for item in items),
        expected_deaths=expected_deaths,
        captured_deaths=sum(item.outcome == "death" for item in items),
    )


def find_contact_hotspots(
    episodes: Iterable[ContactEpisode],
    *,
    min_resolved: int = 3,
) -> list[ContactHotspot]:
    grouped: dict[tuple[str, str], list[ContactEpisode]] = {}
    for item in episodes:
        if item.location == "Unknown":
            continue
        grouped.setdefault((item.side, item.location), []).append(item)
    hotspots = [
        ContactHotspot(side=side, location=location, stats=summarize_contacts(items))
        for (side, location), items in grouped.items()
        if summarize_contacts(items).resolved >= min_resolved
    ]
    return sorted(
        hotspots,
        key=lambda item: (
            item.stats.smoothed_kill_rate
            if item.stats.smoothed_kill_rate is not None
            else 1.0,
            -item.stats.resolved,
            item.side,
            item.location,
        ),
    )


__all__ = [
    "ContactComparison",
    "ContactCoverage",
    "ContactHotspot",
    "ContactOutcomeStats",
    "compare_contact_outcomes",
    "evaluate_contact_coverage",
    "find_contact_hotspots",
    "summarize_contacts",
]
