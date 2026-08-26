"""快速扫描本地 CS2 Demo，并生成可复核的目录清单。"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from chapter07_cs2_coach.demo_parser import CS2DemoMatchParser, DemoParseError
from chapter07_cs2_coach.models import DemoPlayerOption


class DemoInspection(BaseModel):
    """解析器快速读取出的可信元数据。"""

    model_config = ConfigDict(extra="forbid")

    header: dict[str, Any]
    players: list[DemoPlayerOption]


class DemoCatalogEntry(BaseModel):
    """一份 Demo 的目录记录。"""

    model_config = ConfigDict(extra="forbid")

    demo_id: str
    relative_path: str
    file_size_bytes: int = Field(ge=0)
    file_modified_at: str
    map_name: str | None = None
    server_name: str | None = None
    source: str = "unknown"
    source_confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    source_evidence: str | None = None
    demo_type: Literal["server_demo", "pov_demo", "unknown"] = "unknown"
    demo_format: str | None = None
    patch_version: str | None = None
    players: list[DemoPlayerOption] = Field(default_factory=list)
    player_count: int = Field(default=0, ge=0)
    match_date: str | None = None
    status: Literal["metadata_ready", "duplicate", "failed"]
    duplicate_of: str | None = None
    error: str | None = None


class DemoCatalogStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: int = Field(ge=0)
    unique_files: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    metadata_ready: int = Field(ge=0)
    failed: int = Field(ge=0)


class DemoCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.demo-catalog.v1"] = "roundmind.demo-catalog.v1"
    generated_at: str
    root_name: str
    stats: DemoCatalogStats
    entries: list[DemoCatalogEntry]


Inspector = Callable[[Path], DemoInspection]


def compute_demo_sha256(path: Path, *, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _text(header: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = str(header.get(key, "")).strip().strip("\x00")
        if value:
            return value
    return None


def infer_source(
    *, file_name: str, server_name: str | None, client_name: str | None
) -> tuple[str, Literal["high", "medium", "low", "unknown"], str | None]:
    """只给出有文本证据的来源提示，不把文件时间猜成比赛时间。"""

    server = (server_name or "").casefold()
    combined = " ".join((file_name, server_name or "", client_name or "")).casefold()
    known = (
        ("faceit", "FACEIT"),
        ("hltv", "HLTV"),
        ("perfect world", "Perfect World"),
        ("完美世界", "Perfect World"),
        ("blast", "BLAST"),
        ("pgl", "PGL"),
        ("esl", "ESL"),
    )
    for marker, label in known:
        if marker in server:
            return label, "high", "server_name"
        if marker in combined:
            return label, "low", "filename_or_client"
    if "valve" in server or "matchmaking" in server or "premier" in server:
        return "Valve matchmaking", "medium", "server_name"
    return "unknown", "unknown", None


def _demo_type(header: dict[str, Any], player_count: int) -> Literal[
    "server_demo", "pov_demo", "unknown"
]:
    client = (_text(header, "client_name") or "").casefold()
    if "sourcetv" in client or "gotv" in client or player_count > 2:
        return "server_demo"
    if client and client not in {"source2 demo", "counter-strike 2"}:
        return "pov_demo"
    return "unknown"


def _default_inspector(path: Path) -> DemoInspection:
    header, players = CS2DemoMatchParser().inspect_metadata(path)
    return DemoInspection(header=header, players=players)


def collect_demo_files(
    directory: Path, *, recursive: bool = True, max_files: int = 1000
) -> list[Path]:
    root = directory.resolve()
    iterator: Iterable[Path] = root.rglob("*.dem") if recursive else root.glob("*.dem")
    return sorted(
        (path for path in iterator if path.is_file() and not path.is_symlink()),
        key=lambda path: str(path.relative_to(root)).casefold(),
    )[:max_files]


def build_demo_catalog(
    directory: Path,
    *,
    recursive: bool = True,
    max_files: int = 1000,
    inspector: Inspector | None = None,
) -> DemoCatalog:
    root = directory.resolve()
    if not root.is_dir():
        raise ValueError("Demo 目录不存在或不是文件夹。")
    inspect = inspector or _default_inspector
    entries: list[DemoCatalogEntry] = []
    first_by_hash: dict[str, DemoCatalogEntry] = {}

    for path in collect_demo_files(root, recursive=recursive, max_files=max_files):
        stat = path.stat()
        relative_path = path.relative_to(root).as_posix()
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        try:
            fingerprint = compute_demo_sha256(path)
        except OSError:
            entries.append(
                DemoCatalogEntry(
                    demo_id="unavailable",
                    relative_path=relative_path,
                    file_size_bytes=stat.st_size,
                    file_modified_at=modified,
                    status="failed",
                    error="文件无法读取或已被其他程序占用。",
                )
            )
            continue

        demo_id = f"sha256:{fingerprint}"
        original = first_by_hash.get(fingerprint)
        if original is not None:
            duplicate = original.model_copy(
                update={
                    "relative_path": relative_path,
                    "file_size_bytes": stat.st_size,
                    "file_modified_at": modified,
                    "status": "duplicate",
                    "duplicate_of": original.relative_path,
                },
                deep=True,
            )
            entries.append(duplicate)
            continue

        try:
            result = inspect(path)
            header = result.header
            server_name = _text(header, "server_name")
            client_name = _text(header, "client_name")
            source, confidence, evidence = infer_source(
                file_name=path.name,
                server_name=server_name,
                client_name=client_name,
            )
            entry = DemoCatalogEntry(
                demo_id=demo_id,
                relative_path=relative_path,
                file_size_bytes=stat.st_size,
                file_modified_at=modified,
                map_name=_text(header, "map_name"),
                server_name=server_name,
                source=source,
                source_confidence=confidence,
                source_evidence=evidence,
                demo_type=_demo_type(header, len(result.players)),
                demo_format=_text(header, "demo_version_name", "demo_file_stamp"),
                patch_version=_text(header, "patch_version"),
                players=result.players,
                player_count=len(result.players),
                status="metadata_ready",
            )
        except (DemoParseError, ValueError, TypeError):
            entry = DemoCatalogEntry(
                demo_id=demo_id,
                relative_path=relative_path,
                file_size_bytes=stat.st_size,
                file_modified_at=modified,
                status="failed",
                error="无法读取 Demo 元数据，文件可能不完整或版本暂不兼容。",
            )
        first_by_hash[fingerprint] = entry
        entries.append(entry)

    stats = DemoCatalogStats(
        files=len(entries),
        unique_files=len(first_by_hash),
        duplicates=sum(item.status == "duplicate" for item in entries),
        metadata_ready=sum(item.status == "metadata_ready" for item in entries),
        failed=sum(item.status == "failed" for item in entries),
    )
    return DemoCatalog(
        generated_at=datetime.now(timezone.utc).isoformat(),
        root_name=root.name,
        stats=stats,
        entries=entries,
    )


def write_catalog_json(catalog: DemoCatalog, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")


def write_catalog_csv(catalog: DemoCatalog, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "demo_id",
        "relative_path",
        "file_size_mb",
        "map_name",
        "server_name",
        "source",
        "source_confidence",
        "demo_type",
        "demo_format",
        "patch_version",
        "player_count",
        "players",
        "steamids",
        "match_date",
        "file_modified_at",
        "status",
        "duplicate_of",
        "error",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for item in catalog.entries:
            writer.writerow(
                {
                    "demo_id": item.demo_id,
                    "relative_path": item.relative_path,
                    "file_size_mb": f"{item.file_size_bytes / 1024 / 1024:.2f}",
                    "map_name": item.map_name or "",
                    "server_name": item.server_name or "",
                    "source": item.source,
                    "source_confidence": item.source_confidence,
                    "demo_type": item.demo_type,
                    "demo_format": item.demo_format or "",
                    "patch_version": item.patch_version or "",
                    "player_count": item.player_count,
                    "players": " | ".join(player.name for player in item.players),
                    "steamids": " | ".join(player.steamid for player in item.players),
                    "match_date": item.match_date or "",
                    "file_modified_at": item.file_modified_at,
                    "status": item.status,
                    "duplicate_of": item.duplicate_of or "",
                    "error": item.error or "",
                }
            )
