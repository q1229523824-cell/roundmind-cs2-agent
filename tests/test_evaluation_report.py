import unittest

from chapter07_cs2_coach.evaluation_report import (
    run_evaluation_report,
    report_markdown,
)
from chapter07_cs2_coach.runtime import CS2CoachRuntime
from chapter07_cs2_coach.sample_data import SAMPLE_MATCH


class EvaluationReportTests(unittest.TestCase):
    def test_report_exposes_measured_metrics_and_limits_claims(self):
        report = run_evaluation_report()

        self.assertEqual(report.schema_version, "roundmind.evaluation-report.v1")
        self.assertEqual(report.decision_regression.total, 14)
        self.assertEqual(report.decision_regression.passed, 14)
        self.assertEqual(report.runtime_ab.baseline.critic_invocations, 0)
        self.assertEqual(report.runtime_ab.treatment.critic_invocations, 1)
        self.assertEqual(report.runtime_ab.treatment.stage_coverage, 1.0)
        self.assertEqual(report.runtime_ab.accuracy_effect, "not_evaluated")
        self.assertTrue(any("前后测" in item for item in report.not_evaluated))
        self.assertEqual(sum(item.covered for item in report.scenario_coverage), 17)

    def test_markdown_labels_engineering_regression_boundary(self):
        markdown = report_markdown(run_evaluation_report())

        self.assertIn("14/14 (100.0%)", markdown)
        self.assertIn("不是泛化准确率", markdown)
        self.assertIn("not_evaluated", markdown)

    def test_critic_can_be_disabled_for_a_control_variant(self):
        runtime = CS2CoachRuntime.create(enable_critic=False)

        result = runtime.analyze(
            match_id=SAMPLE_MATCH.match_id,
            question="请综合复盘并找出最需要改进的问题",
        )

        self.assertEqual(result.critic_trigger_reasons, [])
        self.assertEqual(result.agent_runs[-1].agent_id, "critic")
        self.assertEqual(result.agent_runs[-1].status, "skipped")
        self.assertTrue(any("A/B 基线" in item for item in result.execution_trace))


if __name__ == "__main__":
    unittest.main()
