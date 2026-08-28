"""生成可复现的工程评测报告，避免用测试数量冒充产品效果。"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from chapter07_cs2_coach.evaluation import (
    DecisionEvaluationResult,
    load_evaluation_cases,
    run_decision_evaluation,
)
from chapter07_cs2_coach.models import MatchRecord
from chapter07_cs2_coach.runtime import CS2CoachRuntime, MatchRepository
from chapter07_cs2_coach.sample_data import SAMPLE_MATCH
from chapter07_cs2_coach.workflow import CS2CoachWorkflow


ReportStatus = Literal["measured", "not_evaluated"]


class CoverageMetric(BaseModel):
    """一个维度实际覆盖了多少种场景。"""

    model_config = ConfigDict(extra="forbid")

    dimension: str = Field(min_length=1, max_length=80)
    required: list[str] = Field(min_length=1, max_length=30)
    observed: list[str] = Field(default_factory=list, max_length=30)
    covered: int = Field(ge=0)
    total: int = Field(ge=1)
    coverage: float = Field(ge=0, le=1)


class RuntimeVariantMetric(BaseModel):
    """一次工作流变体运行的可观察指标。"""

    model_config = ConfigDict(extra="forbid")

    variant: Literal["baseline_without_critic", "treatment_with_critic"]
    critic_enabled: bool
    match_count: int = Field(ge=1)
    critic_invocations: int = Field(ge=0)
    critic_trigger_rate: float = Field(ge=0, le=1)
    mean_tool_calls: float = Field(ge=0)
    mean_evidence_count: float = Field(ge=0)
    stage_covered: list[str] = Field(min_length=1, max_length=20)
    stage_missing: list[str] = Field(default_factory=list, max_length=20)
    stage_coverage: float = Field(ge=0, le=1)
    confidence_counts: dict[str, int]


class ABComparison(BaseModel):
    """Critic 开关的操作性对照；不声称它改善了人工判断准确率。"""

    model_config = ConfigDict(extra="forbid")

    baseline: RuntimeVariantMetric
    treatment: RuntimeVariantMetric
    critic_invocation_delta: int
    tool_call_delta: float
    evidence_delta: float
    accuracy_effect: Literal["not_evaluated"] = "not_evaluated"
    note: str


class EvaluationReport(BaseModel):
    """适合 CI、面试和 README 引用的匿名评测摘要。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["roundmind.evaluation-report.v1"] = (
        "roundmind.evaluation-report.v1"
    )
    status: ReportStatus
    decision_regression: DecisionEvaluationResult
    scenario_coverage: list[CoverageMetric] = Field(min_length=1, max_length=20)
    runtime_ab: ABComparison
    measured_claims: list[str] = Field(min_length=1, max_length=20)
    not_evaluated: list[str] = Field(min_length=1, max_length=20)


STAGES = (
    "prepare",
    "data_quality_check",
    "coach_agent",
    "tool_executor",
    "evidence_validator",
    "decision_scorer",
    "knowledge_retriever",
    "critic_gate",
    "reporter",
)

# 这些是评测集当前刻意要求的边界，不是“已经覆盖全部 CS2”。
REQUIRED_SCENARIOS: dict[str, tuple[str, ...]] = {
    "阵营": ("T", "CT"),
    "接战类型": (
        "isolated_advance",
        "isolated_contact",
        "last_alive",
        "supported_contact",
        "uncertain_support",
    ),
    "期望风险": ("high", "medium", "low"),
    # unknown 也要作为边界值保留：它代表解析信息缺失，不能被隐藏成已覆盖。
    "炸弹状态": ("not_planted", "planted", "defused", "unknown"),
    "支援条件": ("nearby", "distant", "none"),
}


def _support_bucket(case) -> str:
    engagement = case.engagement
    if engagement.nearby_support:
        return "nearby"
    if engagement.nearest_teammate_distance is not None:
        return "distant"
    return "none"


def _coverage_metrics() -> list[CoverageMetric]:
    cases = load_evaluation_cases()
    observed: dict[str, set[str]] = {
        name: set() for name in REQUIRED_SCENARIOS
    }
    for case in cases:
        observed["阵营"].add(case.engagement.side)
        observed["接战类型"].add(case.engagement.classification)
        observed["期望风险"].add(case.expected_level)
        observed["炸弹状态"].add(case.engagement.bomb_state or "not_planted")
        observed["支援条件"].add(_support_bucket(case))
    metrics: list[CoverageMetric] = []
    for dimension, required in REQUIRED_SCENARIOS.items():
        values = sorted(observed[dimension])
        covered = len(set(required) & observed[dimension])
        metrics.append(
            CoverageMetric(
                dimension=dimension,
                required=list(required),
                observed=values,
                covered=covered,
                total=len(required),
                coverage=round(covered / len(required), 4),
            )
        )
    return metrics


def _run_variant(
    match: MatchRecord,
    *,
    critic_enabled: bool,
    variant: Literal["baseline_without_critic", "treatment_with_critic"],
) -> RuntimeVariantMetric:
    runtime = CS2CoachRuntime(
        repository=MatchRepository(),
        workflow=CS2CoachWorkflow(enable_critic=critic_enabled),
    )
    runtime.add_match(match)
    result = runtime.analyze(
        match_id=match.match_id,
        question="请综合复盘并找出最需要改进的问题",
    )
    traces = result.execution_trace
    covered = [stage for stage in STAGES if any(item.startswith(f"{stage}:") for item in traces)]
    invocations = sum(
        item.agent_id == "critic" and item.status in {"completed", "warning"}
        for item in result.agent_runs
    )
    return RuntimeVariantMetric(
        variant=variant,
        critic_enabled=critic_enabled,
        match_count=1,
        critic_invocations=invocations,
        critic_trigger_rate=round(invocations, 4),
        mean_tool_calls=float(len(result.tools_used)),
        mean_evidence_count=float(len(result.evidence)),
        stage_covered=covered,
        stage_missing=[stage for stage in STAGES if stage not in covered],
        stage_coverage=round(len(covered) / len(STAGES), 4),
        confidence_counts=Counter({result.confidence: 1}),
    )


def run_evaluation_report(match: MatchRecord = SAMPLE_MATCH) -> EvaluationReport:
    """运行离线、无外部模型调用的工程评测。"""

    decision = run_decision_evaluation()
    coverage = _coverage_metrics()
    baseline = _run_variant(
        match,
        critic_enabled=False,
        variant="baseline_without_critic",
    )
    treatment = _run_variant(
        match,
        critic_enabled=True,
        variant="treatment_with_critic",
    )
    comparison = ABComparison(
        baseline=baseline,
        treatment=treatment,
        critic_invocation_delta=treatment.critic_invocations - baseline.critic_invocations,
        tool_call_delta=round(treatment.mean_tool_calls - baseline.mean_tool_calls, 4),
        evidence_delta=round(treatment.mean_evidence_count - baseline.mean_evidence_count, 4),
        note="A/B 只测量 Critic 对资源和执行路径的影响；没有人工标签时不推断准确率提升。",
    )
    measured = [
        f"决策边界回归 {decision.passed}/{decision.total} 通过",
        f"运行时关键阶段覆盖 {treatment.stage_coverage:.1%}",
        f"评测集覆盖 {sum(item.covered for item in coverage)}/{sum(item.total for item in coverage)} 个边界值",
    ]
    not_evaluated = [
        "真实 Demo 解析准确率：尚无 verified 金标准批量报告",
        "人工教练动作一致率：尚无已标注决策卡",
        "玩家分数或胜率提升：尚无前后测数据",
    ]
    return EvaluationReport(
        status="measured",
        decision_regression=decision,
        scenario_coverage=coverage,
        runtime_ab=comparison,
        measured_claims=measured,
        not_evaluated=not_evaluated,
    )


def report_markdown(report: EvaluationReport) -> str:
    """将报告压缩成不会误导的 Markdown 摘要。"""

    decision = report.decision_regression
    lines = [
        "# RoundMind 离线评测报告",
        "",
        "> 下面是工程回归与运行时覆盖指标，不等同于真实用户提升效果。",
        "",
        "## 可引用指标",
        "",
        f"- 决策边界回归：**{decision.passed}/{decision.total} ({decision.accuracy:.1%})**；"
        "这是人工设计场景的规则回归，不是泛化准确率。",
        f"- 运行时阶段覆盖：**{report.runtime_ab.treatment.stage_coverage:.1%}** "
        f"（{len(report.runtime_ab.treatment.stage_covered)}/{len(STAGES)} 个阶段）。",
        f"- 边界场景覆盖：**{sum(item.covered for item in report.scenario_coverage)}/"
        f"{sum(item.total for item in report.scenario_coverage)}** 个维度值。",
        "",
        "## 场景覆盖",
        "",
        "| 维度 | 已观察 | 覆盖率 |",
        "| --- | --- | ---: |",
    ]
    for item in report.scenario_coverage:
        lines.append(
            f"| {item.dimension} | {', '.join(item.observed) or '无'} | {item.coverage:.1%} |"
        )
    lines.extend(
        [
            "",
            "## Coach / Critic 对照",
            "",
            f"- Critic 调用变化：{report.runtime_ab.baseline.critic_invocations} → "
            f"{report.runtime_ab.treatment.critic_invocations}；工具调用变化："
            f"{report.runtime_ab.tool_call_delta:+.1f}。",
            f"- 当前样例的 Critic 触发率：{report.runtime_ab.treatment.critic_invocations / report.runtime_ab.treatment.match_count:.1%}。",
            "- 该对照只说明何时增加复核成本；没有人工标签时，准确率效果记为 not_evaluated。",
            "",
            "## 暂不能声称",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report.not_evaluated)
    return "\n".join(lines) + "\n"


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 RoundMind 可复现离线评测报告。")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=str, help="写入文件；省略时输出到终端")
    return parser


def main() -> None:
    args = _argument_parser().parse_args()
    report = run_evaluation_report()
    content = (
        report.model_dump_json(indent=2)
        if args.format == "json"
        else report_markdown(report)
    )
    if args.output:
        from pathlib import Path

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(f"评测报告：{output.resolve()}")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()


__all__ = [
    "ABComparison",
    "CoverageMetric",
    "EvaluationReport",
    "RuntimeVariantMetric",
    "report_markdown",
    "run_evaluation_report",
]
