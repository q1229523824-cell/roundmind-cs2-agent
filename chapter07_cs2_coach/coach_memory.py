"""本地教练会话记忆：仅保存匿名玩家编号和有限轮次的问答。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 18_000
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=6000)


class CoachSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.coach-session.v1"] = (
        "roundmind.coach-session.v1"
    )
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    player_ref: str = Field(pattern=r"^player_[a-f0-9]{12}$")
    map_name: str = Field(min_length=1, max_length=80)
    messages: list[ConversationMessage] = Field(default_factory=list)


def trim_history(
    messages: list[ConversationMessage],
) -> list[ConversationMessage]:
    """按消息数和字符数保留最近历史，控制隐私面与 token 成本。"""
    selected: list[ConversationMessage] = []
    used_chars = 0
    for message in reversed(messages[-MAX_HISTORY_MESSAGES:]):
        if selected and used_chars + len(message.content) > MAX_HISTORY_CHARS:
            break
        selected.append(message)
        used_chars += len(message.content)
    return list(reversed(selected))


class CoachSessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    @staticmethod
    def _validate_session_id(session_id: str) -> str:
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("会话名称只能包含字母、数字、下划线和连字符，最长 40 位。")
        return session_id

    def _path(self, *, session_id: str, player_ref: str, map_name: str) -> Path:
        safe_session_id = self._validate_session_id(session_id)
        safe_map = re.sub(r"[^A-Za-z0-9_-]", "_", map_name)[:80]
        return self.root / f"{player_ref}-{safe_map}-{safe_session_id}.json"

    def load(
        self, *, session_id: str, player_ref: str, map_name: str
    ) -> CoachSession:
        path = self._path(
            session_id=session_id, player_ref=player_ref, map_name=map_name
        )
        if not path.exists():
            return CoachSession(
                session_id=session_id,
                player_ref=player_ref,
                map_name=map_name,
            )
        session = CoachSession.model_validate_json(path.read_text(encoding="utf-8"))
        if session.player_ref != player_ref or session.map_name != map_name:
            raise ValueError("会话文件与当前匿名玩家或地图不匹配。")
        session.messages = trim_history(session.messages)
        return session

    def save(self, session: CoachSession) -> Path:
        session.messages = trim_history(session.messages)
        path = self._path(
            session_id=session.session_id,
            player_ref=session.player_ref,
            map_name=session.map_name,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(
            session.model_dump_json(indent=2), encoding="utf-8"
        )
        temporary_path.replace(path)
        return path

    def append_exchange(
        self, session: CoachSession, *, question: str, answer: str
    ) -> Path:
        session.messages.extend(
            [
                ConversationMessage(role="user", content=question),
                ConversationMessage(role="assistant", content=answer),
            ]
        )
        return self.save(session)

    def clear(self, *, session_id: str, player_ref: str, map_name: str) -> None:
        self._path(
            session_id=session_id, player_ref=player_ref, map_name=map_name
        ).unlink(missing_ok=True)


def history_payload(session: CoachSession) -> list[dict[str, str]]:
    return [message.model_dump() for message in trim_history(session.messages)]


__all__ = [
    "CoachSession",
    "CoachSessionStore",
    "ConversationMessage",
    "MAX_HISTORY_CHARS",
    "MAX_HISTORY_MESSAGES",
    "history_payload",
    "trim_history",
]
