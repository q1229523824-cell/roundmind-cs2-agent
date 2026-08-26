"""RoundMind 本地 Demo 目录整理命令。"""

from __future__ import annotations

import argparse
from pathlib import Path

from chapter07_cs2_coach.demo_catalog import (
    build_demo_catalog,
    write_catalog_csv,
    write_catalog_json,
)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="扫描本地 CS2 Demo，自动识别地图、玩家、版本并按指纹去重。"
    )
    parser.add_argument("--demo-dir", type=Path, required=True, help="Demo 所在目录")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".agent_data/catalog"),
        help="JSON 和 CSV 清单输出目录",
    )
    parser.add_argument("--no-recursive", action="store_true", help="只扫描目录第一层")
    parser.add_argument("--max-files", type=int, default=1000)
    return parser


def main() -> None:
    args = _argument_parser().parse_args()
    if args.max_files < 1 or args.max_files > 10000:
        raise SystemExit("--max-files 必须在 1 到 10000 之间。")
    try:
        catalog = build_demo_catalog(
            args.demo_dir,
            recursive=not args.no_recursive,
            max_files=args.max_files,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    json_output = args.output_dir / "demo-catalog.json"
    csv_output = args.output_dir / "demo-catalog.csv"
    write_catalog_json(catalog, json_output)
    write_catalog_csv(catalog, csv_output)
    stats = catalog.stats
    print(
        f"扫描完成：{stats.files} 个文件，{stats.unique_files} 个唯一 Demo，"
        f"{stats.duplicates} 个重复，{stats.failed} 个读取失败。"
    )
    print(f"JSON：{json_output.resolve()}")
    print(f"CSV：{csv_output.resolve()}")
    print("注意：file_modified_at 是文件时间，不等于比赛开赛时间。")


if __name__ == "__main__":
    main()
