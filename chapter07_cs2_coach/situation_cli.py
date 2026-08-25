"""本地批量生成真实 Demo 局势覆盖报告。"""

from __future__ import annotations

import argparse
from pathlib import Path

from chapter07_cs2_coach.profile_cli import collect_demo_paths
from chapter07_cs2_coach.quality_cli import parse_matches_for_audit
from chapter07_cs2_coach.situation_audit import audit_situation_coverage


def main() -> None:
    parser = argparse.ArgumentParser(description="批量检查真实 Demo 的局势状态覆盖。")
    parser.add_argument("--demo-dir", type=Path, required=True)
    parser.add_argument("--player-steamid", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-files", type=int, default=20, choices=range(1, 101))
    args = parser.parse_args()
    paths = collect_demo_paths([], args.demo_dir, max_files=args.max_files)
    if not paths:
        raise SystemExit("没有找到可读取的 .dem 文件。")
    matches, failures = parse_matches_for_audit(
        paths, player_steamid=args.player_steamid.strip()
    )
    if not matches:
        raise SystemExit("没有成功解析的比赛。")
    report = audit_situation_coverage(matches)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(
        f"已审计 {report.match_count} 场、{report.engagement_count} 次接战；"
        f"平均信息完整度 {report.average_information_completeness}。"
    )
    print(f"报告：{args.output.resolve()}")
    for warning in report.warnings:
        print(f"- {warning}")
    for path, reason in failures:
        print(f"- 跳过 {path.name}: {reason}")


if __name__ == "__main__":
    main()
