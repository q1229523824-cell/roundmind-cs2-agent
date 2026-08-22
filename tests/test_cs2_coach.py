import io
import json
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from chapter07_cs2_coach.api import create_app
from chapter07_cs2_coach.demo_jobs import DemoJobManager
from chapter07_cs2_coach.demo_parser import CS2DemoMatchParser, DemoParseError
from chapter07_cs2_coach.models import MatchRecord
from chapter07_cs2_coach.runtime import CS2CoachRuntime
from chapter07_cs2_coach.sample_data import SAMPLE_MATCH
from chapter07_cs2_coach.tools import get_match_summary


class FakeDemoParser:
    def __init__(self, _path: str):
        self.events = {
            "round_end": [
                {"tick": 1000, "total_rounds_played": 0, "winner": "T"},
                {"tick": 2000, "total_rounds_played": 1, "winner": "CT"},
            ],
            "player_death": [
                {
                    "tick": 500,
                    "total_rounds_played": 0,
                    "attacker_name": "Learner",
                    "attacker_team_name": "TERRORIST",
                    "user_name": "Enemy",
                    "user_team_name": "CT",
                    "assister_name": "",
                },
                {
                    "tick": 1500,
                    "total_rounds_played": 1,
                    "attacker_name": "Enemy",
                    "attacker_team_name": "TERRORIST",
                    "user_name": "Learner",
                    "user_team_name": "CT",
                    "assister_name": "",
                },
                {
                    "tick": 1560,
                    "total_rounds_played": 1,
                    "attacker_name": "Teammate",
                    "attacker_team_name": "CT",
                    "user_name": "Enemy",
                    "user_team_name": "TERRORIST",
                    "assister_name": "",
                },
            ],
            "player_hurt": [
                {
                    "tick": 490,
                    "total_rounds_played": 0,
                    "attacker_name": "Learner",
                    "user_name": "Enemy",
                    "dmg_health": 86,
                    "weapon": "ak47",
                },
                {
                    "tick": 1480,
                    "total_rounds_played": 1,
                    "attacker_name": "Learner",
                    "user_name": "Enemy",
                    "dmg_health": 24,
                    "weapon": "hegrenade",
                },
            ],
            "player_blind": [
                {
                    "tick": 480,
                    "total_rounds_played": 0,
                    "attacker_name": "Learner",
                    "user_name": "Enemy",
                }
            ],
        }

    def parse_header(self):
        return {"demo_file_stamp": "PBDEMS2\x00", "map_name": "de_mirage"}

    def parse_player_info(self):
        return [{"name": "Learner"}, {"name": "Enemy"}, {"name": "Teammate"}]

    def parse_event(self, event_name, *, player=None, other=None):
        return self.events[event_name]

    def parse_ticks(self, wanted_props, *, ticks):
        return [
            {
                "tick": 1000,
                "name": "Learner",
                "team_name": "TERRORIST",
                "round_start_equip_value": 4200,
            },
            {
                "tick": 2000,
                "name": "Learner",
                "team_name": "CT",
                "round_start_equip_value": 5100,
            },
        ]


class InlineExecutor:
    def submit(self, function, *args, **kwargs):
        future = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except Exception as error:  # pragma: no cover - Future 行为兼容
            future.set_exception(error)
        return future


class CS2CoachToolTests(unittest.TestCase):
    def test_summary_is_calculated_from_round_facts(self):
        summary = get_match_summary(SAMPLE_MATCH)

        self.assertEqual(summary["score"], "10:12")
        self.assertEqual(summary["kills"], 24)
        self.assertEqual(summary["deaths"], 12)
        self.assertEqual(summary["adr"], 102.6)

    def test_match_rejects_score_inconsistent_with_rounds(self):
        payload = SAMPLE_MATCH.model_dump()
        payload["team_score"] = 11

        with self.assertRaises(ValidationError):
            MatchRecord.model_validate(payload)


class CS2DemoParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = CS2DemoMatchParser(FakeDemoParser)

    def test_demo_events_are_converted_to_match_facts(self):
        with tempfile.NamedTemporaryFile(suffix=".dem", delete=False) as handle:
            handle.write(b"PBDEMS2\x00fake-demo")
            path = Path(handle.name)
        try:
            match = self.parser.parse(path, "learner")
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(match.map_name, "de_mirage")
        self.assertEqual(match.team_score, 2)
        self.assertEqual(match.rounds[0].opening_duel, "won")
        self.assertEqual(match.rounds[0].damage, 86)
        self.assertEqual(match.rounds[1].utility_damage, 24)
        self.assertTrue(match.rounds[1].was_traded)

    def test_unknown_player_returns_available_names(self):
        with tempfile.NamedTemporaryFile(suffix=".dem", delete=False) as handle:
            handle.write(b"PBDEMS2\x00fake-demo")
            path = Path(handle.name)
        try:
            with self.assertRaisesRegex(DemoParseError, "Learner"):
                self.parser.parse(path, "missing")
        finally:
            path.unlink(missing_ok=True)


class CS2CoachWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.runtime = CS2CoachRuntime.create()

    def test_question_dynamically_selects_clutch_tool(self):
        result = self.runtime.analyze(
            match_id=SAMPLE_MATCH.match_id,
            question="为什么我杀了很多人还是输了？",
        )

        self.assertEqual(result.tools_used, ["clutches"])
        self.assertEqual(result.evidence[0].round_numbers, [9, 14, 19])
        self.assertIn("R9、R14、R19", result.answer)

    def test_comprehensive_review_runs_bounded_tool_loop(self):
        result = self.runtime.analyze(
            match_id=SAMPLE_MATCH.match_id,
            question="请综合复盘并找出最需要改进的问题",
        )

        self.assertEqual(len(result.tools_used), 5)
        self.assertLessEqual(len(result.tools_used), 5)
        self.assertTrue(any(item.severity == "high" for item in result.evidence))
        self.assertEqual(result.confidence, "high")
        self.assertTrue(result.execution_trace[-1].startswith("reporter:"))

    def test_unknown_match_is_rejected(self):
        with self.assertRaises(KeyError):
            self.runtime.analyze(match_id="missing", question="复盘")


class CS2CoachApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(CS2CoachRuntime.create()))

    def test_homepage_and_health(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/health").json()["status"], "ok")

    def test_analyze_endpoint(self):
        response = self.client.post(
            "/api/analyze",
            json={
                "match_id": SAMPLE_MATCH.match_id,
                "question": "分析我的首杀和补枪问题",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["tools_used"], ["opening_duels", "tradeability"])
        self.assertGreaterEqual(len(body["evidence"]), 1)

    def test_upload_json_rejects_wrong_extension(self):
        response = self.client.post(
            "/api/upload-json",
            files={"file": ("match.txt", io.BytesIO(b"{}"), "text/plain")},
        )

        self.assertEqual(response.status_code, 400)

    def test_upload_json_accepts_valid_match(self):
        payload = SAMPLE_MATCH.model_copy(update={"match_id": "uploaded-demo"}).model_dump()
        response = self.client.post(
            "/api/upload-json",
            files={
                "file": (
                    "match.json",
                    io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
                    "application/json",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["match_id"], "uploaded-demo")

    def test_demo_upload_rejects_invalid_header(self):
        response = self.client.post(
            "/api/demo-jobs",
            data={"player_name": "Learner"},
            files={"file": ("match.dem", io.BytesIO(b"not-a-demo"), "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 422)

    def test_demo_job_parses_and_deletes_temporary_file(self):
        runtime = CS2CoachRuntime.create()
        jobs = DemoJobManager(
            runtime,
            parser=CS2DemoMatchParser(FakeDemoParser),
            executor=InlineExecutor(),
        )
        client = TestClient(create_app(runtime, jobs))

        response = client.post(
            "/api/demo-jobs",
            data={"player_name": "Learner", "question": "分析首轮交火"},
            files={
                "file": (
                    "match.dem",
                    io.BytesIO(b"PBDEMS2\x00fake-demo"),
                    "application/octet-stream",
                )
            },
        )

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["match"]["player_name"], "Learner")
        self.assertIn("opening_duels", body["analysis"]["tools_used"])


if __name__ == "__main__":
    unittest.main()
