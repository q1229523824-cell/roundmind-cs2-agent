"""本地 Dust2 战术知识库与可解释的混合检索。

第一版不依赖外部 Embedding 服务：先用地图/阵营/点位元数据过滤，再按问题、
事实证据和标签做关键词计分。接口与向量检索解耦，后续可替换 FAISS/pgvector。
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from chapter07_cs2_coach.models import (
    EngagementRecord,
    Evidence,
    KnowledgeReference,
    MatchRecord,
)


KNOWLEDGE_PATH = Path(__file__).resolve().parent / "knowledge" / "dust2_tactics.json"


class TacticalKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    map: str = Field(min_length=1, max_length=80)
    sides: list[Literal["T", "CT"]] = Field(min_length=1, max_length=2)
    locations: list[str] = Field(default_factory=list, max_length=30)
    topics: list[str] = Field(min_length=1, max_length=12)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    principle: str = Field(min_length=1, max_length=600)
    action: str = Field(min_length=1, max_length=400)
    source: str = Field(min_length=1, max_length=200)


TOPIC_TERMS = {
    "isolation": ("孤立", "单摸", "前压", "距离"),
    "trade": ("补枪", "交换", "队友", "同步"),
    "engagement": ("接战", "决策", "对枪", "peek", "死亡"),
    "utility": ("道具", "闪光", "烟雾", "燃烧弹", "手雷"),
    "opening_duel": ("首杀", "首死", "突破", "开局"),
    "economy": ("经济", "购买", "强起", "半起", "eco"),
    "clutch": ("残局", "拆包", "保枪", "时间"),
    "conversion": ("转化", "多打少", "人数优势"),
    "survival": ("生存", "撤退", "换位", "重复"),
}


@lru_cache(maxsize=1)
def load_knowledge() -> tuple[TacticalKnowledge, ...]:
    payload = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    entries = tuple(TacticalKnowledge.model_validate(item) for item in payload)
    ids = [item.id for item in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("战术知识 ID 不能重复。")
    return entries


def _query_context(
    match: MatchRecord,
    question: str,
    evidence: list[Evidence],
) -> tuple[str, set[str], set[str], set[str]]:
    evidence_text = " ".join(
        f"{item.finding} {item.metric} {item.suggestion}" for item in evidence
    )
    query_text = question.lower()
    context_text = f"{question} {evidence_text}".lower()
    topics = {
        topic
        for topic, terms in TOPIC_TERMS.items()
        if any(term.lower() in context_text for term in terms)
    }
    priority_evidence = [item for item in evidence if item.severity == "high"] or evidence
    evidence_rounds = {
        number for item in priority_evidence for number in item.round_numbers
    }
    relevant = [
        item for item in match.engagements if item.round_number in evidence_rounds
    ] or list(match.engagements)
    if "isolation" in topics:
        isolated_advances = [
            item for item in relevant if item.classification == "isolated_advance"
        ]
        isolated = isolated_advances or [
            item for item in relevant if item.classification.startswith("isolated")
        ]
        relevant = isolated or relevant
    locations = {item.location for item in relevant if item.location}
    sides = {item.side for item in relevant}
    return query_text, locations, sides, topics


def retrieve_tactical_knowledge(
    match: MatchRecord,
    question: str,
    evidence: list[Evidence],
    *,
    limit: int = 3,
) -> list[KnowledgeReference]:
    """检索与本场事实最相关的知识，不让知识条目伪装成比赛事实。"""

    if match.map_name != "de_dust2" or limit <= 0:
        return []
    text, locations, sides, topics = _query_context(match, question, evidence)
    if os.getenv("ROUNDMIND_KNOWLEDGE_BACKEND", "local").lower() == "pgvector":
        from chapter07_cs2_coach.vector_knowledge import retrieve_pgvector_knowledge

        return retrieve_pgvector_knowledge(
            match=match,
            question=question,
            evidence=evidence,
            locations=locations,
            sides=sides,
            topics=topics,
            limit=limit,
        )
    scored: list[tuple[int, TacticalKnowledge, set[str]]] = []
    for entry in load_knowledge():
        if entry.map != match.map_name:
            continue
        matched_topics = set(entry.topics) & topics
        matched_locations = set(entry.locations) & locations
        matched_keywords = {
            keyword for keyword in entry.keywords if keyword.lower() in text
        }
        score = 10
        score += len(matched_topics) * 6
        score += len(matched_locations) * 8
        score += len(matched_keywords) * 3
        if sides and set(entry.sides) & sides:
            score += 2
        if not (matched_topics or matched_locations or matched_keywords):
            continue
        scored.append((min(score, 100), entry, matched_topics))

    scored.sort(key=lambda item: (-item[0], item[1].id))
    return [
        KnowledgeReference(
            knowledge_id=entry.id,
            title=entry.title,
            principle=f"{entry.principle} 可执行动作：{entry.action}",
            source=entry.source,
            matched_topics=sorted(matched_topics),
            score=score,
        )
        for score, entry, matched_topics in scored[:limit]
    ]


def retrieve_for_engagement(
    match: MatchRecord,
    engagement: EngagementRecord,
    *,
    limit: int = 2,
) -> list[KnowledgeReference]:
    """只基于单次接战快照检索，避免其他回合污染决策卡依据。"""

    if match.map_name != "de_dust2" or limit <= 0:
        return []
    topics = {"engagement"}
    if engagement.classification.startswith("isolated"):
        topics.update({"isolation", "trade"})
    elif engagement.classification == "supported_contact":
        topics.add("trade")
    if engagement.effective_team_flashes_5s == 0:
        topics.add("utility")

    scored: list[tuple[int, TacticalKnowledge, set[str]]] = []
    for entry in load_knowledge():
        if entry.map != match.map_name:
            continue
        matched_topics = set(entry.topics) & topics
        matched_location = engagement.location in entry.locations
        if not (matched_topics or matched_location):
            continue
        score = 10 + len(matched_topics) * 6
        if matched_location:
            score += 12
        elif entry.locations:
            score -= 12
        if engagement.side in entry.sides:
            score += 3
        scored.append((min(score, 100), entry, matched_topics))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    return [
        KnowledgeReference(
            knowledge_id=entry.id,
            title=entry.title,
            principle=f"{entry.principle} 可执行动作：{entry.action}",
            source=entry.source,
            matched_topics=sorted(matched_topics),
            score=score,
        )
        for score, entry, matched_topics in scored[:limit]
    ]


__all__ = [
    "KNOWLEDGE_PATH",
    "TacticalKnowledge",
    "load_knowledge",
    "retrieve_for_engagement",
    "retrieve_tactical_knowledge",
]
