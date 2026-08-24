"""把可信比赛事实、画像、个人案例和知识组合成有界的大模型上下文。"""

from __future__ import annotations

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from chapter07_cs2_coach.knowledge_base import retrieve_tactical_knowledge
from chapter07_cs2_coach.models import (
    Evidence,
    FirstDamageDisadvantageSegment,
    KnowledgeReference,
    MatchRecord,
    ProfileFinding,
    RoleProfile,
    WeaponCategoryProfile,
)
from chapter07_cs2_coach.personal_baseline import build_personal_contact_contrasts
from chapter07_cs2_coach.player_profile import build_player_profile
from chapter07_cs2_coach.quality_audit import audit_match
from chapter07_cs2_coach.weapon_role_profile import weapon_category


MAX_CONTEXT_BYTES = 32 * 1024


class ContextSampleSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matches: int = Field(ge=1)
    rounds: int = Field(ge=1)
    contacts: int = Field(ge=0)
    profile_confidence: Literal["high", "medium", "low"]
    quality_gate: Literal["pass", "review"]
    average_quality_score: float = Field(ge=0, le=100)


class ContextEvidenceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_ref: str = Field(pattern=r"^match_\d{2}$")
    round_number: int = Field(ge=1, le=100)
    side: Literal["T", "CT"]
    location: str = Field(min_length=1, max_length=80)
    weapon_category: str = Field(min_length=1, max_length=30)
    opponent_distance: int | None = Field(default=None, ge=0)
    first_damage_by_player: bool
    health_before_contact: int = Field(ge=0, le=100)
    support_ready_teammates_proxy: int | None = Field(default=None, ge=0, le=4)
    player_facing_opponent: bool | None = None
    personal_success_round: int | None = Field(default=None, ge=1, le=100)
    personal_success_similarity: int | None = Field(default=None, ge=0, le=100)
    observed_differences: list[str] = Field(default_factory=list, max_length=8)
    lesson: str = Field(default="", max_length=400)
    confidence: Literal["high", "medium", "low"]


class ContextTrainingPriority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1, le=5)
    focus: str = Field(min_length=1, max_length=240)
    evidence: str = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=500)
    success_metric: str = Field(min_length=1, max_length=300)
    confidence: Literal["high", "medium", "low"]


class LLMCoachContextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.coach-context.v1"] = (
        "roundmind.coach-context.v1"
    )
    player_ref: str = Field(pattern=r"^player_[a-f0-9]{12}$")
    map_name: str = Field(min_length=1, max_length=80)
    sample: ContextSampleSummary
    role_profile: RoleProfile
    weapon_profile: list[WeaponCategoryProfile] = Field(max_length=7)
    repeated_findings: list[ProfileFinding] = Field(max_length=6)
    first_damage_disadvantage_segments: list[FirstDamageDisadvantageSegment] = Field(
        max_length=6
    )
    evidence_cases: list[ContextEvidenceCase] = Field(max_length=4)
    knowledge_references: list[KnowledgeReference] = Field(max_length=3)
    training_priorities: list[ContextTrainingPriority] = Field(max_length=3)
    response_guardrails: list[str] = Field(min_length=1, max_length=8)


def player_reference(steamid: str) -> str:
    """生成可稳定复用的匿名玩家编号，不把 SteamID 写入会话文件。"""
    return f"player_{sha256(steamid.encode('utf-8')).hexdigest()[:12]}"


def _case_score(item) -> tuple[int, int, int]:
    score = 0
    score += 30 if item.side == "T" else 0
    score += 25 if weapon_category(item.weapon) == "rifle" else 0
    score += 15 if item.opponent_distance is not None and 500 <= item.opponent_distance <= 1200 else 0
    score += 10 if item.player_facing_opponent is False else 0
    return score, -item.round_number, -item.start_tick


def _evidence_cases(matches: list[MatchRecord]) -> list[ContextEvidenceCase]:
    candidates = []
    for match_index, match in enumerate(matches, start=1):
        contrasts = {
            (item.death_round, item.death_tick): item
            for item in build_personal_contact_contrasts(match, limit=20)
        }
        for item in match.contact_episodes:
            if item.outcome != "death" or item.first_damage_by_player:
                continue
            contrast = contrasts.get((item.round_number, item.start_tick))
            confidence: Literal["high", "medium", "low"] = (
                contrast.confidence if contrast else "low"
            )
            candidates.append(
                (
                    _case_score(item),
                    ContextEvidenceCase(
                        match_ref=f"match_{match_index:02d}",
                        round_number=item.round_number,
                        side=item.side,
                        location=item.location,
                        weapon_category=weapon_category(item.weapon),
                        opponent_distance=item.opponent_distance,
                        first_damage_by_player=False,
                        health_before_contact=item.health_before_contact,
                        support_ready_teammates_proxy=(
                            item.support_ready_teammates_proxy
                        ),
                        player_facing_opponent=item.player_facing_opponent,
                        personal_success_round=(
                            contrast.success_round if contrast else None
                        ),
                        personal_success_similarity=(
                            contrast.similarity_score if contrast else None
                        ),
                        observed_differences=(
                            contrast.differences if contrast else []
                        ),
                        lesson=contrast.lesson if contrast else (
                            "缺少同阵营同点位的相似成功样本，只能把本回合作为待复核证据。"
                        ),
                        confidence=confidence,
                    ),
                )
            )
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    selected: list[ContextEvidenceCase] = []
    seen: set[tuple[str, str]] = set()
    for _, case in candidates:
        diversity_key = (case.location, case.weapon_category)
        if diversity_key in seen and len(selected) < 2:
            continue
        selected.append(case)
        seen.add(diversity_key)
        if len(selected) >= 4:
            break
    return selected


def _knowledge(
    matches: list[MatchRecord], cases: list[ContextEvidenceCase]
) -> list[KnowledgeReference]:
    by_ref = {f"match_{index:02d}": match for index, match in enumerate(matches, 1)}
    references: dict[str, KnowledgeReference] = {}
    for case in cases:
        match = by_ref[case.match_ref]
        evidence = Evidence(
            finding="T方步枪被先造成伤害后的交火转化下降",
            round_numbers=[case.round_number],
            metric="需要结合点位、距离、预瞄与换位继续复核",
            severity="high",
            suggestion="受伤后优先重置枪线，并对照个人相似成功回合。",
        )
        for reference in retrieve_tactical_knowledge(
            match,
            "分析步枪手在 T 方被先手伤害后的接战、换位、生存和补枪问题",
            [evidence],
            limit=3,
        ):
            previous = references.get(reference.knowledge_id)
            if previous is None or reference.score > previous.score:
                references[reference.knowledge_id] = reference
    return sorted(
        references.values(), key=lambda item: (-item.score, item.knowledge_id)
    )[:3]


def _training_priorities(
    segments: list[FirstDamageDisadvantageSegment],
    cases: list[ContextEvidenceCase],
) -> list[ContextTrainingPriority]:
    priorities: list[ContextTrainingPriority] = []
    preferred = [
        item for item in segments if item.confidence in {"high", "medium"}
    ] or segments
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    preferred = sorted(
        preferred,
        key=lambda item: (confidence_order[item.confidence], -item.conversion_gap),
    )
    for segment in preferred[:2]:
        label = {
            "weapon": "武器",
            "side": "阵营",
            "location": "点位",
            "distance": "距离",
        }[segment.dimension]
        priorities.append(
            ContextTrainingPriority(
                rank=len(priorities) + 1,
                focus=f"降低{label} {segment.value} 被先手伤害后的交火损失",
                evidence=(
                    f"先手 {segment.own_first_resolved} 个已决样本，转化率 "
                    f"{segment.own_first_kill_rate:.1%}；被先手 "
                    f"{segment.opponent_first_resolved} 个，转化率 "
                    f"{segment.opponent_first_kill_rate:.1%}。"
                ),
                action="受伤后先脱离当前枪线或改变高度/横向位置，再决定二次接触；复盘时记录是否原角度继续对枪。",
                success_metric="后续至少 3 场中，该切片被先手后的死亡占比下降，且不以明显降低主动交火数换取。",
                confidence=segment.confidence,
            )
        )
    if cases and len(priorities) < 3:
        with_baseline = sum(case.personal_success_round is not None for case in cases)
        priorities.append(
            ContextTrainingPriority(
                rank=len(priorities) + 1,
                focus="复用个人相似成功回合，而不是只学习通用口号",
                evidence=f"{len(cases)} 个代表失败中，{with_baseline} 个找到同场相似成功基线。",
                action="逐一对照准星落点、第一段伤害、受伤后移动和队友同步，只保留一个最可执行差异。",
                success_metric="每场至少复核 2 个失败/成功对照，并在下一场只跟踪一个行为目标。",
                confidence="medium" if with_baseline >= 2 else "low",
            )
        )
    return priorities[:3]


def build_coach_context(
    matches: list[MatchRecord],
    *,
    player_steamid: str,
    map_name: str | None = None,
) -> LLMCoachContextPackage:
    profile = build_player_profile(
        matches,
        player_steamid=player_steamid,
        map_name=map_name,
    )
    selected = [
        match
        for match in matches
        if match.player_steamid == player_steamid
        and (map_name is None or match.map_name == map_name)
        and audit_match(match).gate in {"pass", "review"}
    ]
    cases = _evidence_cases(selected)
    package = LLMCoachContextPackage(
        player_ref=player_reference(player_steamid),
        map_name=map_name or "all_maps",
        sample=ContextSampleSummary(
            matches=profile.match_count,
            rounds=profile.round_count,
            contacts=profile.contact_count,
            profile_confidence=profile.confidence,
            quality_gate=profile.quality_gate,
            average_quality_score=profile.quality_score_average or 0,
        ),
        role_profile=profile.role_profile,
        weapon_profile=profile.weapon_profile,
        repeated_findings=profile.findings[:6],
        first_damage_disadvantage_segments=(
            profile.first_damage_disadvantage_segments[:6]
        ),
        evidence_cases=cases,
        knowledge_references=_knowledge(selected, cases),
        training_priorities=_training_priorities(
            profile.first_damage_disadvantage_segments, cases
        ),
        response_guardrails=[
            "只引用包内事实，不推测未记录的语音、战术分工或玩家意图。",
            "低置信度切片只能作为待复核信号，不能表述为稳定弱点。",
            "相关性不等于因果；建议必须附带样本量、回合证据或知识 ID。",
            "每次最多给出三个训练重点，并优先复用玩家自己的成功案例。",
        ],
    )
    if len(package.model_dump_json().encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("教练上下文超过 32 KB，需要进一步裁剪。")
    return package


__all__ = [
    "LLMCoachContextPackage",
    "MAX_CONTEXT_BYTES",
    "build_coach_context",
    "player_reference",
]
