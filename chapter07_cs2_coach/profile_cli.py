"""在本地批量解析多份 Demo 并导出玩家画像。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from chapter07_cs2_coach.demo_parser import CS2DemoMatchParser, DemoParseError
from chapter07_cs2_coach.models import MatchRecord, PlayerProfileResponse
from chapter07_cs2_coach.player_profile import build_player_profile


def collect_demo_paths(
    explicit_paths: Iterable[Path],
    demo_directory: Path | None,
    *,
    max_files: int,
) -> list[Path]:
    candidates = [*explicit_paths]
    if demo_directory is not None:
        candidates.extend(sorted(demo_directory.glob("*.dem")))
    unique: dict[str, Path] = {}
    for path in candidates:
        resolved = path.resolve()
        if resolved.is_file() and resolved.suffix.casefold() == ".dem":
            unique[str(resolved).casefold()] = resolved
    return list(unique.values())[:max_files]


def build_profile_from_demos(
    paths: Iterable[Path],
    *,
    player_steamid: str,
    map_name: str | None = None,
    parser: CS2DemoMatchParser | None = None,
    enforce_quality: bool = True,
) -> tuple[PlayerProfileResponse, list[tuple[Path, str]]]:
    parser = parser or CS2DemoMatchParser()
    matches: list[MatchRecord] = []
    failures: list[tuple[Path, str]] = []
    for path in paths:
        try:
            match = parser.parse(
                path,
                player_name=player_steamid,
                player_steamid=player_steamid,
            )
        except DemoParseError as error:
            failures.append((path, str(error)))
            continue
        if map_name is None or match.map_name == map_name:
            matches.append(match)
    profile = build_player_profile(
        matches,
        player_steamid=player_steamid,
        map_name=map_name,
        enforce_quality=enforce_quality,
    )
    return profile, failures


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="本地批量解析 CS2 Demo，生成跨比赛玩家画像。"
    )
    parser.add_argument("--demo", action="append", default=[], help="可重复传入 Demo 路径")
    parser.add_argument("--demo-dir", type=Path, help="读取目录下第一层的 .dem 文件")
    parser.add_argument("--player-steamid", required=True, help="要分析的玩家 SteamID")
    parser.add_argument("--map-name", help="可选，例如 de_dust2")
    parser.add_argument("--output", type=Path, required=True, help="画像 JSON 输出路径")
    parser.add_argument("--max-files", type=int, default=20, choices=range(1, 101))
    return parser


def main() -> None:
    args = _argument_parser().parse_args()
    paths = collect_demo_paths(
        [Path(item) for item in args.demo],
        args.demo_dir,
        max_files=args.max_files,
    )
    if not paths:
        raise SystemExit("没有找到可读取的 .dem 文件。")
    try:
        profile, failures = build_profile_from_demos(
            paths,
            player_steamid=args.player_steamid.strip(),
            map_name=args.map_name.strip() if args.map_name else None,
        )
    except KeyError as error:
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    print(
        f"已从 {profile.match_count}/{profile.source_match_count} 场唯一比赛生成画像："
        f"{args.output.resolve()}"
    )
    print(
        f"质量门禁：{profile.quality_gate}，需复核 {profile.review_match_count} 场，"
        f"拒绝 {profile.rejected_match_count} 场，平均分 {profile.quality_score_average}。"
    )
    if failures:
        print(f"跳过 {len(failures)} 个无法解析或不包含该玩家的 Demo：")
        for path, reason in failures:
            print(f"- {path.name}: {reason}")


if __name__ == "__main__":
    main()
