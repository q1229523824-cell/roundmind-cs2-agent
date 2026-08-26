import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from chapter07_cs2_coach.gold_cli import evaluate_manifest

from chapter07_cs2_coach.gold_standard import (
    DemoGoldStandard,
    compare_with_gold,
    create_gold_draft,
    current_parser_provenance,
    extract_key_facts,
)
from chapter07_cs2_coach.sample_data import SAMPLE_MATCH


class DemoGoldStandardTests(unittest.TestCase):
    def test_draft_is_anonymous_and_contains_manual_check_fields(self):
        match = SAMPLE_MATCH.model_copy(update={"player_steamid": "76561198000000001"})
        gold = create_gold_draft(match)

        serialized = gold.model_dump_json()
        self.assertEqual(gold.status, "draft")
        self.assertTrue(gold.player_ref.startswith("player_"))
        self.assertNotIn(match.player_name, serialized)
        self.assertNotIn(match.player_steamid, serialized)
        self.assertEqual(gold.expected.round_count, 22)
        self.assertEqual(gold.expected.kills, 24)
        self.assertEqual(gold.expected.deaths, 12)
        self.assertEqual(gold.expected.assists, 4)

    def test_verified_exact_match_passes(self):
        gold = create_gold_draft(SAMPLE_MATCH).model_copy(update={"status": "verified"})
        report = compare_with_gold(gold, SAMPLE_MATCH)

        self.assertTrue(report.passed)
        self.assertEqual(report.overall.accuracy, 1)
        self.assertEqual(report.critical.accuracy, 1)
        self.assertEqual(report.round_level.accuracy, 1)

    def test_draft_is_rejected_by_default(self):
        with self.assertRaisesRegex(ValueError, "draft"):
            compare_with_gold(create_gold_draft(SAMPLE_MATCH), SAMPLE_MATCH)

    def test_score_and_round_drift_are_reported(self):
        gold = create_gold_draft(SAMPLE_MATCH).model_copy(update={"status": "verified"})
        facts = extract_key_facts(SAMPLE_MATCH)
        changed_round = facts.rounds[0].model_copy(update={"opening_duel": "none"})
        expected = facts.model_copy(
            update={"team_score": 9, "opponent_score": 13, "rounds": [changed_round, *facts.rounds[1:]]}
        )
        changed_gold = DemoGoldStandard.model_validate(
            {**gold.model_dump(), "expected": expected.model_dump()}
        )
        report = compare_with_gold(changed_gold, SAMPLE_MATCH)

        mismatches = {item.path for item in report.comparisons if not item.matched}
        self.assertFalse(report.passed)
        self.assertIn("team_score", mismatches)
        self.assertIn("opponent_score", mismatches)
        self.assertIn("rounds.1.opening_duel", mismatches)

    def test_parser_provenance_is_stable_and_strict(self):
        first = current_parser_provenance()
        second = current_parser_provenance()
        self.assertEqual(first, second)
        self.assertEqual(len(first.parser_source_sha256), 64)

    def test_wrong_match_is_rejected(self):
        gold = create_gold_draft(SAMPLE_MATCH).model_copy(update={"status": "verified"})
        other = SAMPLE_MATCH.model_copy(update={"match_id": "different-match"})
        with self.assertRaisesRegex(ValueError, "不匹配"):
            compare_with_gold(gold, other)

    def test_batch_failure_does_not_copy_local_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            secret_name = "private-user-demo.dem"
            manifest = root / "manifest.json"
            manifest.write_text(
                """{
                  "schema_version": "roundmind.demo-regression-manifest.v1",
                  "cases": [{
                    "case_id": "missing-demo",
                    "demo_path": "private-user-demo.dem",
                    "player_steamid": "76561198000000001",
                    "gold_path": "private-gold.json"
                  }]
                }""",
                encoding="utf-8",
            )

            report = evaluate_manifest(manifest)
            serialized = report.model_dump_json()
            self.assertEqual(report.failed, 1)
            self.assertNotIn(secret_name, serialized)
            self.assertNotIn(str(root), serialized)


if __name__ == "__main__":
    unittest.main()
