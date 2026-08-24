"""本地批量解析 Demo 并输出数据质量门禁报告。"""

from __future__ import annotations

import argparse
from pathlib import Path

from chapter07_cs2_coach.demo_parser import CS2DemoMatchParser, DemoParseError
from chapter07_cs2_coach.models import MatchRecord
from chapter07_cs2_coach.profile_cli import collect_demo_paths
from chapter07_cs2_coach.quality_audit import audit_matches


def parse_matches_for_audit(
    paths: list[Path],
    *,
    player_steamid: str,
    parser: CS2DemoMatchParser | None = None,
) -> tuple[list[MatchRecord], list[tuple[Path, str]]]:
    parser = parser or CS2DemoMatchParser()
    matches: dict[str, MatchRecord] = {}
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
        matches[match.match_id] = match
    return list(matches.values()), failures


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量解析 CS2 Demo，检查事件覆盖率、重复和上下文完整性。"
    )
    parser.add_argument("--demo", action="append", default=[], help="可重复传入 Demo 路径")
    parser.add_argument("--demo-dir", type=Path, help="读取目录下第一层的 .dem 文件")
    parser.add_argument("--player-steamid", required=True, help="要审计的玩家 SteamID")
    parser.add_argument("--output", type=Path, required=True, help="质量报告 JSON 输出路径")
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
    matches, failures = parse_matches_for_audit(
        paths,
        player_steamid=args.player_steamid.strip(),
    )
    if not matches:
        reasons = "；".join(reason for _, reason in failures)
        raise SystemExit(f"没有成功解析的比赛。{reasons}")
    report = audit_matches(matches)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(
        f"已审计 {report.match_count} 场：通过 {report.passed}，"
        f"需复核 {report.needs_review}，失败 {report.failed}，"
        f"平均质量分 {report.average_score}。"
    )
    print(f"报告：{args.output.resolve()}")
    for audit in report.audits:
        print(f"- {audit.match_id}: {audit.gate} / {audit.quality_score}")
    if failures:
        print(f"另有 {len(failures)} 个 Demo 无法解析：")
        for path, reason in failures:
            print(f"- {path.name}: {reason}")


if __name__ == "__main__":
    main()
