"""本地运行离线/可选 DeepSeek 教练，不上传原始 Demo。"""

from __future__ import annotations

import argparse
from pathlib import Path

from chapter07_cs2_coach.coach_llm import CoachService
from chapter07_cs2_coach.profile_cli import collect_demo_paths
from chapter07_cs2_coach.quality_cli import parse_matches_for_audit


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="基于本地多场 Demo 运行教练问答。")
    parser.add_argument("--demo", action="append", default=[])
    parser.add_argument("--demo-dir", type=Path)
    parser.add_argument("--player-steamid", required=True)
    parser.add_argument("--map-name", default="de_dust2")
    parser.add_argument("--question", required=True)
    parser.add_argument("--output", type=Path)
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
        response = CoachService.from_environment().answer(
            matches,
            player_steamid=args.player_steamid.strip(),
            map_name=args.map_name.strip(),
            question=args.question.strip(),
        )
    except (KeyError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
    serialized = response.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(f"回答已保存：{args.output.resolve()}")
    else:
        print(serialized)
    print(f"回答模式：{response.mode}；模型：{response.model_name or '未调用'}")
    if failures:
        print(f"跳过 {len(failures)} 个无法解析的 Demo。")


if __name__ == "__main__":
    main()
