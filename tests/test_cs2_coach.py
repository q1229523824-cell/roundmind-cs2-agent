import io
import json
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from chapter07_cs2_coach.api import MAX_DEMO_BYTES, MAX_DEMO_MB, create_app
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
                {"tick": 1000, "round": 1, "total_rounds_played": 1, "winner": "T"},
                {"tick": 2000, "round": 2, "total_rounds_played": 2, "winner": "CT"},
            ],
            "round_freeze_end": [
                {"tick": 100, "total_rounds_played": 0},
                {"tick": 1100, "total_rounds_played": 1},
            ],
            "player_death": [
                {
                    "tick": 500,
                    "total_rounds_played": 0,
                    "attacker_name": "Learner",
                    "attacker_steamid": "1",
                    "attacker_team_name": "TERRORIST",
                    "user_name": "Enemy",
                    "user_steamid": "2",
                    "user_team_name": "CT",
                    "assister_name": "",
                },
                {
                    "tick": 1500,
                    "total_rounds_played": 1,
                    "attacker_name": "Enemy",
                    "attacker_steamid": "2",
                    "attacker_team_name": "TERRORIST",
                    "user_name": "Learner",
                    "user_steamid": "1",
                    "user_team_name": "CT",
                    "assister_name": "",
                },
                {
                    "tick": 1560,
                    "total_rounds_played": 1,
                    "attacker_name": "Teammate",
                    "attacker_steamid": "3",
                    "attacker_team_name": "CT",
                    "user_name": "Enemy",
                    "user_steamid": "2",
                    "user_team_name": "TERRORIST",
                    "assister_name": "",
                },
            ],
            "player_hurt": [
                {
                    "tick": 490,
                    "total_rounds_played": 0,
                    "attacker_name": "Learner",
                    "attacker_steamid": "1",
                    "attacker_team_name": "TERRORIST",
                    "user_name": "Enemy",
                    "user_steamid": "2",
                    "user_team_name": "CT",
                    "dmg_health": 86,
                    "weapon": "ak47",
                },
                {
                    "tick": 1480,
                    "total_rounds_played": 1,
                    "attacker_name": "Learner",
                    "attacker_steamid": "1",
                    "attacker_team_name": "CT",
                    "user_name": "Enemy",
                    "user_steamid": "2",
                    "user_team_name": "TERRORIST",
                    "dmg_health": 24,
                    "weapon": "hegrenade",
                },
            ],
            "player_blind": [
                {
                    "tick": 480,
                    "total_rounds_played": 0,
                    "attacker_name": "Learner",
                    "attacker_steamid": "1",
                    "attacker_team_name": "TERRORIST",
                    "user_name": "Enemy",
                    "user_steamid": "2",
                    "user_team_name": "CT",
                    "blind_duration": 2.5,
                }
            ],
        }

    def parse_header(self):
        return {"demo_file_stamp": "PBDEMS2\x00", "map_name": "de_mirage"}

    def parse_player_info(self):
        return [
            {"name": "Learner", "steamid": "1"},
            {"name": "Enemy", "steamid": "2"},
            {"name": "Teammate", "steamid": "3"},
        ]

    def parse_event(self, event_name, *, player=None, other=None):
        return self.events[event_name]

    def parse_ticks(self, wanted_props, *, ticks):
        return [
            {
                "tick": 100,
                "steamid": "1",
                "name": "Learner",
                "team_name": "TERRORIST",
                "current_equip_value": 4200,
            },
            {
                "tick": 1100,
                "steamid": "1",
                "name": "Learner",
                "team_name": "CT",
                "current_equip_value": 5100,
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


class DuplicateNameDemoParser(FakeDemoParser):
    def parse_player_info(self):
        return super().parse_player_info() + [{"name": "Learner", "steamid": "4"}]


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
        self.assertEqual(match.player_steamid, "1")
        self.assertEqual(match.team_score, 2)
        self.assertEqual(match.rounds[0].opening_duel, "won")
        self.assertEqual(match.rounds[0].damage, 86)
        self.assertEqual(match.rounds[0].equipment_value, 4200)
        self.assertEqual(match.rounds[0].enemies_flashed, 1)
        self.assertEqual(match.rounds[1].utility_damage, 24)
        self.assertTrue(match.rounds[1].was_traded)

    def test_player_names_can_be_discovered_before_analysis(self):
        with tempfile.NamedTemporaryFile(suffix=".dem", delete=False) as handle:
            handle.write(b"PBDEMS2\x00fake-demo")
            path = Path(handle.name)
        try:
            players = self.parser.list_players(path)
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(players, ["Enemy", "Learner", "Teammate"])

    def test_steamid_disambiguates_duplicate_player_names(self):
        parser = CS2DemoMatchParser(DuplicateNameDemoParser)
        with tempfile.NamedTemporaryFile(suffix=".dem", delete=False) as handle:
            handle.write(b"PBDEMS2\x00fake-demo")
            path = Path(handle.name)
        try:
            with self.assertRaisesRegex(DemoParseError, "找不到唯一玩家"):
                parser.parse(path, "Learner")
            match = parser.parse(path, "Learner", "1")
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(match.player_steamid, "1")
        self.assertEqual(match.rounds[0].kills, 1)

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
    def test_demo_upload_limit_is_500_mb(self):
        self.assertEqual(MAX_DEMO_MB, 500)
        self.assertEqual(MAX_DEMO_BYTES, 500 * 1024 * 1024)

    def setUp(self):
        self.client = TestClient(create_app(CS2CoachRuntime.create()))

    def test_homepage_and_health(self):
        homepage = self.client.get("/")
        self.assertEqual(homepage.status_code, 200)
        self.assertIn("上传 CS2 Demo 或 JSON", homepage.text)
        self.assertIn(".dem 最大 500 MB", homepage.text)
        self.assertIn('accept=".dem,.json,application/json"', homepage.text)

        script = self.client.get("/static/app.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn('request.open("POST", "/api/demo-jobs")', script.text)
        self.assertIn("500 * 1024 * 1024", script.text)
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

    def test_demo_job_discovers_players_then_accepts_selection(self):
        runtime = CS2CoachRuntime.create()
        jobs = DemoJobManager(
            runtime,
            parser=CS2DemoMatchParser(FakeDemoParser),
            executor=InlineExecutor(),
            player_selection_timeout_seconds=60,
        )
        client = TestClient(create_app(runtime, jobs))

        response = client.post(
            "/api/demo-jobs",
            files={
                "file": (
                    "match.dem",
                    io.BytesIO(b"PBDEMS2\x00fake-demo"),
                    "application/octet-stream",
                )
            },
        )

        self.assertEqual(response.status_code, 202)
        discovered = response.json()
        self.assertEqual(discovered["status"], "awaiting_player")
        self.assertEqual(discovered["available_players"], ["Enemy", "Learner", "Teammate"])
        self.assertEqual(discovered["player_options"][1], {"name": "Learner", "steamid": "1"})
        self.assertIsNone(discovered["player_name"])

        selected = client.post(
            f"/api/demo-jobs/{discovered['job_id']}/player",
            json={
                "player_name": "Learner",
                "player_steamid": "1",
                "question": "分析首轮交火",
            },
        )

        self.assertEqual(selected.status_code, 202)
        completed = selected.json()
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["match"]["player_name"], "Learner")
        self.assertEqual(completed["match"]["player_steamid"], "1")
        self.assertIn("opening_duels", completed["analysis"]["tools_used"])


if __name__ == "__main__":
    unittest.main()
