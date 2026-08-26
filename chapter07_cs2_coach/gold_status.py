"""把本地金标准批量报告压缩为可公开展示的匿名状态。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from chapter07_cs2_coach.gold_cli import BatchRegressionReport


class PublicGoldStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.demo-regression-status.v1"] = (
        "roundmind.demo-regression-status.v1"
    )
    available: bool
    gate: Literal["pass", "fail", "awaiting_verified_dataset"]
    verified_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    pass_rate: float | None = Field(default=None, ge=0, le=1)
    average_overall_accuracy: float | None = Field(default=None, ge=0, le=1)
    average_critical_accuracy: float | None = Field(default=None, ge=0, le=1)
    parser_version_changed_cases: int = Field(default=0, ge=0)
    message: str


def unavailable_status() -> PublicGoldStatus:
    return PublicGoldStatus(
        available=False,
        gate="awaiting_verified_dataset",
        verified_cases=0,
        passed_cases=0,
        failed_cases=0,
        message="尚未发布 verified Demo 金标准报告；不会用自动草稿冒充解析准确率。",
    )


def summarize_batch(report: BatchRegressionReport) -> PublicGoldStatus:
    scorable = [
        item
        for item in report.cases
        if item.overall_accuracy is not None and item.critical_accuracy is not None
    ]
    if not scorable:
        return unavailable_status()
    passed = sum(item.passed for item in scorable)
    failed = len(scorable) - passed
    return PublicGoldStatus(
        available=True,
        gate="pass" if failed == 0 else "fail",
        verified_cases=len(scorable),
        passed_cases=passed,
        failed_cases=failed,
        pass_rate=round(passed / len(scorable), 4),
        average_overall_accuracy=round(
            sum(item.overall_accuracy or 0 for item in scorable) / len(scorable), 4
        ),
        average_critical_accuracy=round(
            sum(item.critical_accuracy or 0 for item in scorable) / len(scorable), 4
        ),
        parser_version_changed_cases=sum(
            item.parser_version_changed is True for item in scorable
        ),
        message=(
            "全部 verified Demo 通过解析门禁。"
            if failed == 0
            else "存在 verified Demo 未通过解析门禁，应停止发布解析器变更。"
        ),
    )


def load_public_gold_status(report_path: str | None) -> PublicGoldStatus:
    if not report_path:
        return unavailable_status()
    try:
        payload = Path(report_path).read_text(encoding="utf-8")
        return summarize_batch(BatchRegressionReport.model_validate_json(payload))
    except (OSError, ValidationError, ValueError):
        return unavailable_status()


__all__ = [
    "PublicGoldStatus",
    "load_public_gold_status",
    "summarize_batch",
    "unavailable_status",
]
