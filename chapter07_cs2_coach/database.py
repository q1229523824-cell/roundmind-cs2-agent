"""可选 PostgreSQL 持久化层；本地未配置数据库时仍可使用内存仓库。"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from chapter07_cs2_coach.models import MatchRecord


class MatchOwnershipConflictError(RuntimeError):
    """同一业务 ID 已属于另一个用户，禁止覆盖其数据。"""


class MatchRepositoryProtocol(Protocol):
    backend_name: str

    def save(self, match: MatchRecord, owner_id: str | None = None) -> MatchRecord: ...

    def get(self, match_id: str) -> MatchRecord | None: ...

    def list(self) -> list[MatchRecord]: ...

    def get_for_owner(self, match_id: str, owner_id: str) -> MatchRecord | None: ...

    def list_for_owner(self, owner_id: str) -> list[MatchRecord]: ...


class DatabaseBase(DeclarativeBase):
    pass


class StoredUser(DatabaseBase):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StoredMatch(DatabaseBase):
    """第一阶段用 JSON 保存完整领域对象，同时保留常用查询列。"""

    __tablename__ = "matches"

    match_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    player_steamid: Mapped[str | None] = mapped_column(String(32), nullable=True)
    map_name: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_matches_player_map", "player_steamid", "map_name"),
        Index("idx_matches_owner_created", "owner_id", "created_at"),
        Index("idx_matches_created_at", "created_at"),
    )


def normalize_database_url(url: str) -> str:
    """兼容部分云平台仍提供的 postgres:// URL。"""
    normalized = url.strip()
    if normalized.startswith("postgres://"):
        return "postgresql+psycopg://" + normalized[len("postgres://") :]
    if normalized.startswith("postgresql://"):
        return "postgresql+psycopg://" + normalized[len("postgresql://") :]
    return normalized


def create_database_engine(url: str) -> Engine:
    normalized = normalize_database_url(url)
    options: dict[str, object] = {"pool_pre_ping": True}
    if normalized.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(normalized, **options)


class SqlAlchemyMatchRepository:
    backend_name = "postgresql"

    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: Engine | None = None,
        create_schema: bool = False,
    ) -> None:
        if engine is None and not database_url:
            raise ValueError("必须提供 database_url 或 SQLAlchemy engine。")
        self.engine = engine or create_database_engine(database_url or "")
        if self.engine.dialect.name == "sqlite":
            self.backend_name = "sqlite"
        if create_schema:
            DatabaseBase.metadata.create_all(self.engine)

    def save(self, match: MatchRecord, owner_id: str | None = None) -> MatchRecord:
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            stored = session.get(StoredMatch, match.match_id)
            if stored is None:
                stored = StoredMatch(
                    match_id=match.match_id,
                    owner_id=owner_id,
                    player_steamid=match.player_steamid,
                    map_name=match.map_name,
                    payload=match.model_dump(mode="json"),
                    created_at=now,
                    updated_at=now,
                )
                session.add(stored)
            else:
                if stored.owner_id is not None and stored.owner_id != owner_id:
                    raise MatchOwnershipConflictError("该比赛 ID 已被其他账户使用。")
                if owner_id is not None:
                    stored.owner_id = owner_id
                stored.player_steamid = match.player_steamid
                stored.map_name = match.map_name
                stored.payload = match.model_dump(mode="json")
                stored.updated_at = now
        return match

    def get(self, match_id: str) -> MatchRecord | None:
        with Session(self.engine) as session:
            stored = session.get(StoredMatch, match_id)
            return MatchRecord.model_validate(stored.payload) if stored else None

    def list(self) -> list[MatchRecord]:
        statement = select(StoredMatch).order_by(StoredMatch.created_at, StoredMatch.match_id)
        with Session(self.engine) as session:
            return [
                MatchRecord.model_validate(item.payload)
                for item in session.scalars(statement).all()
            ]

    def get_for_owner(self, match_id: str, owner_id: str) -> MatchRecord | None:
        statement = select(StoredMatch).where(
            StoredMatch.match_id == match_id, StoredMatch.owner_id == owner_id
        )
        with Session(self.engine) as session:
            stored = session.scalar(statement)
            return MatchRecord.model_validate(stored.payload) if stored else None

    def list_for_owner(self, owner_id: str) -> list[MatchRecord]:
        statement = (
            select(StoredMatch)
            .where(StoredMatch.owner_id == owner_id)
            .order_by(StoredMatch.created_at, StoredMatch.match_id)
        )
        with Session(self.engine) as session:
            return [
                MatchRecord.model_validate(item.payload)
                for item in session.scalars(statement).all()
            ]


def repository_from_environment() -> SqlAlchemyMatchRepository | None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return SqlAlchemyMatchRepository(database_url)


__all__ = [
    "DatabaseBase",
    "MatchRepositoryProtocol",
    "MatchOwnershipConflictError",
    "SqlAlchemyMatchRepository",
    "StoredMatch",
    "StoredUser",
    "create_database_engine",
    "normalize_database_url",
    "repository_from_environment",
]
