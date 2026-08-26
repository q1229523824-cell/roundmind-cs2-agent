"""本地网页使用的短期 Demo 目录会话。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import monotonic
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from chapter07_cs2_coach.demo_catalog import (
    DemoCatalogEntry,
    DemoCatalogStats,
    Inspector,
    build_demo_catalog,
    compute_demo_sha256,
)


class DirectorySelectionCancelled(RuntimeError):
    """用户关闭了系统文件夹选择框。"""


class LocalCatalogEntry(DemoCatalogEntry):
    entry_id: str


class LocalCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    root_name: str
    stats: DemoCatalogStats
    entries: list[LocalCatalogEntry]


@dataclass(frozen=True)
class _CatalogSession:
    created_at: float
    response: LocalCatalogResponse
    paths: dict[str, Path]


DirectoryChooser = Callable[[], Path | None]


def choose_demo_directory() -> Path | None:
    """打开系统原生文件夹选择框；绝对路径不会返回给网页。"""

    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as error:  # pragma: no cover - Windows 打包环境通常自带
        raise RuntimeError("当前 Python 环境缺少系统文件夹选择组件。") from error
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            parent=root,
            title="选择包含 CS2 Demo 的文件夹",
            mustexist=True,
        )
    finally:
        root.destroy()
    return Path(selected).resolve() if selected else None


class LocalDemoCatalogManager:
    """只在内存中保存目录授权，并使用随机编号代替本地路径。"""

    def __init__(
        self,
        *,
        chooser: DirectoryChooser | None = None,
        inspector: Inspector | None = None,
        session_ttl_seconds: float = 60 * 60,
        max_sessions: int = 5,
    ) -> None:
        self._chooser = chooser or choose_demo_directory
        self._inspector = inspector
        self._session_ttl_seconds = session_ttl_seconds
        self._max_sessions = max_sessions
        self._sessions: dict[str, _CatalogSession] = {}
        self._lock = RLock()

    def select_and_scan(self, *, max_files: int = 1000) -> LocalCatalogResponse:
        directory = self._chooser()
        if directory is None:
            raise DirectorySelectionCancelled("已取消选择文件夹。")
        directory = directory.resolve()
        catalog = build_demo_catalog(
            directory,
            recursive=True,
            max_files=max_files,
            inspector=self._inspector,
        )
        session_id = uuid4().hex
        entries: list[LocalCatalogEntry] = []
        paths: dict[str, Path] = {}
        for item in catalog.entries:
            entry_id = uuid4().hex
            entries.append(
                LocalCatalogEntry(
                    **item.model_dump(),
                    entry_id=entry_id,
                )
            )
            candidate = (directory / item.relative_path).resolve()
            if directory == candidate or directory in candidate.parents:
                paths[entry_id] = candidate
        response = LocalCatalogResponse(
            session_id=session_id,
            root_name=catalog.root_name,
            stats=catalog.stats,
            entries=entries,
        )
        with self._lock:
            self._evict_expired_unlocked()
            while len(self._sessions) >= self._max_sessions:
                oldest = min(
                    self._sessions,
                    key=lambda key: self._sessions[key].created_at,
                )
                del self._sessions[oldest]
            self._sessions[session_id] = _CatalogSession(
                created_at=monotonic(),
                response=response,
                paths=paths,
            )
        return response

    def resolve(
        self, session_id: str, entry_id: str
    ) -> tuple[Path, LocalCatalogEntry]:
        with self._lock:
            self._evict_expired_unlocked()
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            path = session.paths.get(entry_id)
            entry = next(
                (item for item in session.response.entries if item.entry_id == entry_id),
                None,
            )
        if path is None or entry is None or not path.is_file():
            raise KeyError(entry_id)
        try:
            if f"sha256:{compute_demo_sha256(path)}" != entry.demo_id:
                raise KeyError(entry_id)
        except OSError as error:
            raise KeyError(entry_id) from error
        return path, entry

    def _evict_expired_unlocked(self) -> None:
        now = monotonic()
        expired = [
            key
            for key, session in self._sessions.items()
            if now - session.created_at > self._session_ttl_seconds
        ]
        for key in expired:
            del self._sessions[key]
