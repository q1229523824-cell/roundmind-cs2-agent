"""导出并评测本地 Demo 金标准。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from chapter07_cs2_coach.demo_parser import CS2DemoMatchParser, DemoParseError
from chapter07_cs2_coach.gold_standard import (
    DemoGoldStandard,
    DemoRegressionReport,
    compare_with_gold,
    create_gold_draft,
)


class RegressionManifestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    demo_path: Path
    player_steamid: str = Field(min_length=1, max_length=32)
    gold_path: Path


class RegressionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.demo-regression-manifest.v1"] = (
        "roundmind.demo-regression-manifest.v1"
    )
    cases: list[RegressionManifestCase] = Field(min_length=1, max_length=100)


class BatchCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    passed: bool
    overall_accuracy: float | None = None
    critical_accuracy: float | None = None
    parser_version_changed: bool | None = None
    error: str | None = None


class BatchRegressionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.demo-regression-batch.v1"] = (
        "roundmind.demo-regression-batch.v1"
    )
    total: int
    passed: int
    failed: int
    cases: list[BatchCaseResult]


def _parse_demo(path: Path, player_steamid: str):
    return CS2DemoMatchParser().parse(
        path.resolve(),
        player_name=player_steamid,
        player_steamid=player_steamid,
    )


def export_draft(demo: Path, player_steamid: str, output: Path) -> DemoGoldStandard:
    match = _parse_demo(demo, player_steamid)
    gold = create_gold_draft(match)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(gold.model_dump_json(indent=2), encoding="utf-8")
    return gold


def evaluate_case(
    demo: Path,
    player_steamid: str,
    gold_path: Path,
    *,
    allow_draft: bool = False,
) -> DemoRegressionReport:
    gold = DemoGoldStandard.model_validate_json(gold_path.read_text(encoding="utf-8"))
    match = _parse_demo(demo, player_steamid)
    return compare_with_gold(gold, match, allow_draft=allow_draft)


def evaluate_manifest(
    manifest_path: Path,
    *,
    allow_draft: bool = False,
) -> BatchRegressionReport:
    manifest = RegressionManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    base = manifest_path.resolve().parent
    results: list[BatchCaseResult] = []
    for case in manifest.cases:
        try:
            report = evaluate_case(
                base / case.demo_path,
                case.player_steamid,
                base / case.gold_path,
                allow_draft=allow_draft,
            )
            results.append(
                BatchCaseResult(
                    case_id=case.case_id,
                    passed=report.passed,
                    overall_accuracy=report.overall.accuracy,
                    critical_accuracy=report.critical.accuracy,
                    parser_version_changed=report.parser_version_changed,
                )
            )
        except (OSError, ValueError, DemoParseError) as error:
            if isinstance(error, OSError):
                safe_error = "本地 Demo、金标准或 manifest 引用文件无法读取。"
            elif isinstance(error, DemoParseError):
                safe_error = "Demo 解析失败，请单独运行 evaluate 查看本地详细错误。"
            else:
                safe_error = str(error)
            results.append(
                BatchCaseResult(case_id=case.case_id, passed=False, error=safe_error)
            )
    passed = sum(item.passed for item in results)
    return BatchRegressionReport(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        cases=results,
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="建立并回归 CS2 Demo 人工金标准。")
    commands = parser.add_subparsers(dest="command", required=True)

    export = commands.add_parser("export", help="解析 Demo 并导出待人工核对草稿")
    export.add_argument("--demo", type=Path, required=True)
    export.add_argument("--player-steamid", required=True)
    export.add_argument("--output", type=Path, required=True)

    evaluate = commands.add_parser("evaluate", help="对一份已核对金标准生成差异报告")
    evaluate.add_argument("--demo", type=Path, required=True)
    evaluate.add_argument("--player-steamid", required=True)
    evaluate.add_argument("--gold", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--allow-draft", action="store_true")

    batch = commands.add_parser("batch", help="按本地 manifest 批量回归")
    batch.add_argument("--manifest", type=Path, required=True)
    batch.add_argument("--output", type=Path, required=True)
    batch.add_argument("--allow-draft", action="store_true")
    return parser


def main() -> None:
    args = _argument_parser().parse_args()
    try:
        if args.command == "export":
            gold = export_draft(args.demo, args.player_steamid.strip(), args.output)
            print(f"已导出待核对草稿：{args.output.resolve()}")
            print(f"匿名比赛指纹：{gold.source_fingerprint}；状态：{gold.status}")
            return
        if args.command == "evaluate":
            report = evaluate_case(
                args.demo,
                args.player_steamid.strip(),
                args.gold,
                allow_draft=args.allow_draft,
            )
        else:
            report = evaluate_manifest(args.manifest, allow_draft=args.allow_draft)
    except (OSError, ValueError, DemoParseError) as error:
        raise SystemExit(str(error)) from error

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    if isinstance(report, DemoRegressionReport):
        print(
            f"关键字段 {report.critical.accuracy:.1%}，"
            f"回合字段 {report.round_level.accuracy:.1%}，"
            f"门禁：{'通过' if report.passed else '失败'}。"
        )
    else:
        print(f"批量回归 {report.total} 场：通过 {report.passed}，失败 {report.failed}。")
    print(f"报告：{args.output.resolve()}")


if __name__ == "__main__":
    main()
