"""pgvector 战术知识存储；使用可复现的本地哈希向量作为零费用基线。"""

from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, MetaData, String, Table, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from chapter07_cs2_coach.database import create_database_engine
from chapter07_cs2_coach.models import KnowledgeReference


EMBEDDING_DIMENSIONS = 384
metadata = MetaData()
knowledge_vectors = Table(
    "knowledge_vectors",
    metadata,
    Column("knowledge_id", String(80), primary_key=True),
    Column("map_name", String(80), nullable=False, index=True),
    Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
    Column("payload", JSON, nullable=False),
)


def local_text_embedding(text: str) -> list[float]:
    """字符 bigram + 英文词哈希；不是语义模型，但可离线复现和评测。"""

    normalized = " ".join(text.casefold().split())
    latin = re.findall(r"[a-z0-9_]+", normalized)
    cjk = [char for char in normalized if "\u4e00" <= char <= "\u9fff"]
    tokens = latin + cjk + ["".join(pair) for pair in zip(cjk, cjk[1:])]
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def knowledge_document(entry) -> str:
    return " ".join(
        [
            entry.title,
            entry.principle,
            entry.action,
            *entry.topics,
            *entry.keywords,
            *entry.locations,
            *entry.sides,
        ]
    )


@dataclass
class PgVectorKnowledgeStore:
    engine: Engine

    def sync(self, entries) -> None:
        entries = tuple(entries)
        with self.engine.begin() as connection:
            ids = [entry.id for entry in entries]
            if ids:
                connection.execute(
                    delete(knowledge_vectors).where(
                        knowledge_vectors.c.knowledge_id.not_in(ids)
                    )
                )
            for entry in entries:
                values = {
                    "knowledge_id": entry.id,
                    "map_name": entry.map,
                    "embedding": local_text_embedding(knowledge_document(entry)),
                    "payload": entry.model_dump(mode="json"),
                }
                statement = insert(knowledge_vectors).values(**values)
                statement = statement.on_conflict_do_update(
                    index_elements=[knowledge_vectors.c.knowledge_id],
                    set_={
                        "map_name": statement.excluded.map_name,
                        "embedding": statement.excluded.embedding,
                        "payload": statement.excluded.payload,
                    },
                )
                connection.execute(statement)

    def search(
        self,
        query: str,
        *,
        map_name: str,
        sides: set[str],
        locations: set[str],
        topics: set[str],
        limit: int,
    ) -> list[KnowledgeReference]:
        distance = knowledge_vectors.c.embedding.cosine_distance(
            local_text_embedding(query)
        ).label("distance")
        statement = (
            select(knowledge_vectors.c.payload, distance)
            .where(knowledge_vectors.c.map_name == map_name)
            .order_by(distance)
            .limit(max(limit * 4, 12))
        )
        candidates = []
        with self.engine.connect() as connection:
            for payload, vector_distance in connection.execute(statement):
                matched_topics = set(payload["topics"]) & topics
                metadata_bonus = len(matched_topics) * 4
                metadata_bonus += len(set(payload["locations"]) & locations) * 6
                metadata_bonus += 2 if sides & set(payload["sides"]) else 0
                similarity = max(0.0, 1.0 - float(vector_distance))
                score = min(100, round(similarity * 70 + metadata_bonus))
                candidates.append((score, payload, matched_topics))
        candidates.sort(key=lambda item: (-item[0], item[1]["id"]))
        return [
            KnowledgeReference(
                knowledge_id=payload["id"],
                title=payload["title"],
                principle=f"{payload['principle']} 可执行动作：{payload['action']}",
                source=payload["source"],
                matched_topics=sorted(matched_topics),
                score=score,
            )
            for score, payload, matched_topics in candidates[:limit]
        ]


def pgvector_store_from_environment() -> PgVectorKnowledgeStore:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("pgvector 检索需要 DATABASE_URL。")
    return PgVectorKnowledgeStore(create_database_engine(database_url))


def retrieve_pgvector_knowledge(
    *, match, question, evidence, locations, sides, topics, limit
) -> list[KnowledgeReference]:
    from chapter07_cs2_coach.knowledge_base import load_knowledge

    store = pgvector_store_from_environment()
    store.sync(load_knowledge())
    evidence_text = " ".join(
        f"{item.finding} {item.metric} {item.suggestion}" for item in evidence
    )
    query = " ".join([question, evidence_text, *sorted(topics), *sorted(locations)])
    return store.search(
        query,
        map_name=match.map_name,
        sides=sides,
        locations=locations,
        topics=topics,
        limit=limit,
    )
