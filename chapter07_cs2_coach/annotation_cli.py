"""真实 Demo 标注包命令行工具。"""

from __future__ import annotations

import argparse
from pathlib import Path

from chapter07_cs2_coach.annotations import (
    AnnotationPackage,
    create_annotation_package,
    evaluate_annotations,
)
from chapter07_cs2_coach.demo_parser import CS2DemoMatchParser


def _export(args: argparse.Namespace) -> None:
    match = CS2DemoMatchParser().parse(
        Path(args.demo),
        args.player_name,
        args.player_steamid,
    )
    package = create_annotation_package(match, limit=args.limit)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(package.model_dump_json(indent=2), encoding="utf-8")
    print(
        f"已生成 {len(package.cases)} 个匿名待标注场景：{output}\n"
        "包内不包含玩家昵称、SteamID、Demo 路径或原始文件。"
    )


def _evaluate(args: argparse.Namespace) -> None:
    package = AnnotationPackage.model_validate_json(
        Path(args.input).read_text(encoding="utf-8")
    )
    print(evaluate_annotations(package).model_dump_json(indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="RoundMind 决策标注与真实评测")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export", help="从 Demo 生成匿名待标注包")
    export.add_argument("--demo", required=True)
    export.add_argument("--player-name", required=True)
    export.add_argument("--player-steamid")
    export.add_argument("--output", required=True)
    export.add_argument("--limit", type=int, default=8, choices=range(1, 21))
    export.set_defaults(handler=_export)

    evaluate = subparsers.add_parser("evaluate", help="计算已标注包的质量指标")
    evaluate.add_argument("--input", required=True)
    evaluate.set_defaults(handler=_evaluate)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
