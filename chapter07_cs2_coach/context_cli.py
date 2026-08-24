"""从本地多份 Demo 生成隐私裁剪后的大模型教练上下文。"""

from __future__ import annotations

import argparse
from pathlib import Path

from chapter07_cs2_coach.coach_context import build_coach_context
from chapter07_cs2_coach.profile_cli import collect_demo_paths
from chapter07_cs2_coach.quality_cli import parse_matches_for_audit


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量解析 Demo，生成不含昵称、SteamID 和文件路径的教练上下文。"
    )
    parser.add_argument("--demo", action="append", default=[], help="可重复传入 Demo 路径")
    parser.add_argument("--demo-dir", type=Path, help="读取目录第一层的 .dem")
    parser.add_argument("--player-steamid", required=True)
    parser.add_argument("--map-name", default="de_dust2")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-files", type=int, default=20, choices=range(1, 101))
    return parser


def main() -> None:
    args = _argument_parser().parse_args()
    paths = collect_demo_paths(
        [Path(item) for item in args.demo], args.demo_dir, max_files=args.max_files
    )
    if not paths:
        raise SystemExit("没有找到可读取的 .dem 文件。")
    matches, failures = parse_matches_for_audit(
        paths, player_steamid=args.player_steamid.strip()
    )
    if not matches:
        raise SystemExit("没有成功解析的比赛。")
    try:
        package = build_coach_context(
            matches,
            player_steamid=args.player_steamid.strip(),
            map_name=args.map_name.strip() if args.map_name else None,
        )
    except (KeyError, ValueError) as error:
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = package.model_dump_json(indent=2)
    args.output.write_text(serialized, encoding="utf-8")
    print(
        f"已生成 {len(serialized.encode('utf-8'))} 字节教练上下文："
        f"{args.output.resolve()}"
    )
    print(
        f"包含 {package.sample.matches} 场、{len(package.evidence_cases)} 个证据案例、"
        f"{len(package.knowledge_references)} 条知识和 "
        f"{len(package.training_priorities)} 个训练重点。"
    )
    if failures:
        print(f"跳过 {len(failures)} 个无法解析的 Demo。")


if __name__ == "__main__":
    main()
