import io
import json
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from chapter07_cs2_coach.api import MAX_DEMO_BYTES, MAX_DEMO_MB, create_app
from chapter07_cs2_coach.annotations import (
    HumanAnnotation,
    create_annotation_package,
    evaluate_annotations,
)
from chapter07_cs2_coach.demo_jobs import DemoJobManager
from chapter07_cs2_coach.demo_parser import CS2DemoMatchParser, DemoParseError
from chapter07_cs2_coach.decision_scoring import build_decision_cards, score_engagement
from chapter07_cs2_coach.evaluation import (
    load_evaluation_cases,
    run_decision_evaluation,
)
from chapter07_cs2_coach.knowledge_base import (
    load_knowledge,
    retrieve_tactical_knowledge,
)
from chapter07_cs2_coach.models import EngagementRecord, MatchRecord
from chapter07_cs2_coach.runtime import CS2CoachRuntime
from chapter07_cs2_coach.sample_data import SAMPLE_MATCH
from chapter07_cs2_coach.tools import analyze_engagement_decisions, get_match_summary


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
                },
                {
                    "tick": 1480,
                    "total_rounds_played": 1,
                    "attacker_name": "Teammate",
                    "attacker_steamid": "3",
                    "attacker_team_name": "CT",
                    "user_name": "Enemy",
                    "user_steamid": "2",
                    "user_team_name": "TERRORIST",
                    "blind_duration": 1.5,
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
        if "X" in wanted_props:
            rows = []
            for tick in ticks:
                second_half = tick >= 1000
                team = "CT" if second_half else "TERRORIST"
                enemy_team = "TERRORIST" if second_half else "CT"
                rows.extend(
                    [
                        {
                            "tick": tick,
                            "steamid": "1",
                            "name": "Learner",
                            "team_name": team,
                            "is_alive": True,
                            "X": 400 if tick % 1000 > 400 else 0,
                            "Y": 0,
                            "Z": 0,
                            "health": 80,
                            "armor_value": 90,
                            "last_place_name": "TestArea",
                            "active_weapon_name": "AK-47",
                        },
                        {
                            "tick": tick,
                            "steamid": "3",
                            "name": "Teammate",
                            "team_name": team,
                            "is_alive": True,
                            "X": 500,
                            "Y": 0,
                            "Z": 0,
                        },
                        {
                            "tick": tick,
                            "steamid": "2",
                            "name": "Enemy",
                            "team_name": enemy_team,
                            "is_alive": True,
                            "X": 800,
                            "Y": 0,
                            "Z": 0,
                        },
                    ]
                )
            return rows
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
    @staticmethod
    def _annotation_match() -> MatchRecord:
        cases = load_evaluation_cases()
        engagements = [
            case.engagement.model_copy(
                update={"round_number": index, "tick": index * 1000}
            )
            for index, case in enumerate(cases, start=1)
        ]
        return MatchRecord.model_validate(
            {
                "match_id": "private-real-match-id",
                "player_name": "PrivatePlayerName",
                "player_steamid": "76561198000000000",
                "map_name": "de_dust2",
                "team_name": "Private Team",
                "opponent_name": "Opponent Team",
                "team_score": 0,
                "opponent_score": len(cases),
                "rounds": [
                    {
                        "number": index,
                        "side": engagement.side,
                        "won": False,
                        "died": True,
                    }
                    for index, engagement in enumerate(engagements, start=1)
                ],
                "engagements": [item.model_dump() for item in engagements],
            }
        )

    def test_annotation_package_is_stratified_and_anonymous(self):
        package = create_annotation_package(self._annotation_match(), limit=6)
        serialized = package.model_dump_json()

        self.assertEqual(len(package.cases), 6)
        self.assertTrue(any(item.prediction.risk_level == "high" for item in package.cases))
        self.assertTrue(any(item.prediction.risk_level == "low" for item in package.cases))
        self.assertEqual(len({item.case_id for item in package.cases}), 6)
        self.assertNotIn("PrivatePlayerName", serialized)
        self.assertNotIn("76561198000000000", serialized)
        self.assertNotIn("private-real-match-id", serialized)

    def test_annotation_metrics_ignore_uncertain_human_labels(self):
        package = create_annotation_package(self._annotation_match(), limit=6)
        first, second, third = package.cases[:3]
        first.human_annotation = HumanAnnotation(verdict=first.prediction.verdict)
        second.human_annotation = HumanAnnotation(
            verdict=(
                "reasonable"
                if second.prediction.verdict != "reasonable"
                else "high_risk"
            )
        )
        third.human_annotation = HumanAnnotation(verdict="uncertain")

        metrics = evaluate_annotations(package)

        self.assertEqual(metrics.labeled_cases, 3)
        self.assertEqual(metrics.scorable_cases, 2)
        self.assertEqual(metrics.uncertain_cases, 1)
        self.assertEqual(metrics.exact_agreement, 0.5)
        self.assertEqual(metrics.coverage, 0.5)

    def test_decision_risk_distinguishes_isolation_from_real_support(self):
        base = {
            "round_number": 3,
            "tick": 100,
            "location": "LongA",
            "side": "T",
            "position_x": 0,
            "position_y": 0,
            "position_z": 0,
            "health": 100,
            "armor": 100,
            "weapon": "AK-47",
            "alive_teammates": 3,
            "alive_enemies": 4,
        }
        isolated = EngagementRecord(
            **base,
            classification="isolated_advance",
            nearest_teammate_distance=1600,
            nearby_support=False,
            moved_distance_5s=700,
            effective_team_flashes_5s=0,
            was_traded=False,
        )
        supported = EngagementRecord(
            **base,
            classification="supported_contact",
            nearest_teammate_distance=300,
            nearby_support=True,
            moved_distance_5s=100,
            effective_team_flashes_5s=1,
            was_traded=True,
        )
        match = SAMPLE_MATCH.model_copy(
            update={"map_name": "de_dust2", "engagements": [isolated, supported]}
        )

        isolated_card = score_engagement(match, isolated)
        supported_card = score_engagement(match, supported)

        self.assertEqual(isolated_card.risk_level, "high")
        self.assertGreaterEqual(isolated_card.risk_score, 85)
        self.assertEqual(supported_card.risk_level, "low")
        self.assertLess(supported_card.risk_score, 20)
        self.assertIn("dust2-isolation-001", isolated_card.knowledge_ids)

    def test_decision_cards_are_sorted_by_risk(self):
        match = SAMPLE_MATCH.model_copy(
            update={
                "map_name": "de_dust2",
                "engagements": [
                    EngagementRecord(
                        round_number=3,
                        tick=100,
                        classification="supported_contact",
                        location="LongA",
                        side="T",
                        position_x=0,
                        position_y=0,
                        position_z=0,
                        health=100,
                        armor=100,
                        weapon="AK-47",
                        alive_teammates=3,
                        alive_enemies=4,
                        nearest_teammate_distance=300,
                        nearby_support=True,
                        moved_distance_5s=100,
                        effective_team_flashes_5s=1,
                        was_traded=True,
                    ),
                    EngagementRecord(
                        round_number=6,
                        tick=200,
                        classification="isolated_advance",
                        location="UpperTunnel",
                        side="T",
                        position_x=0,
                        position_y=0,
                        position_z=0,
                        health=100,
                        armor=100,
                        weapon="AK-47",
                        alive_teammates=3,
                        alive_enemies=4,
                        nearest_teammate_distance=1600,
                        nearby_support=False,
                        moved_distance_5s=700,
                        effective_team_flashes_5s=0,
                        was_traded=False,
                    ),
                ],
            }
        )

        cards = build_decision_cards(match)

        self.assertEqual([card.round_number for card in cards], [6, 3])

    def test_decision_evaluation_dataset_passes(self):
        cases = load_evaluation_cases()
        result = run_decision_evaluation()

        self.assertGreaterEqual(len(cases), 8)
        self.assertEqual(result.passed, result.total, result.failures)
        self.assertEqual(result.accuracy, 1.0)

    def test_dust2_knowledge_base_has_unique_valid_entries(self):
        entries = load_knowledge()

        self.assertGreaterEqual(len(entries), 10)
        self.assertEqual(len({item.id for item in entries}), len(entries))
        self.assertTrue(all(item.source for item in entries))

    def test_knowledge_retrieval_uses_location_and_question(self):
        match = SAMPLE_MATCH.model_copy(
            update={
                "map_name": "de_dust2",
                "engagements": [
                    EngagementRecord(
                        round_number=3,
                        tick=100,
                        classification="isolated_advance",
                        location="LongA",
                        side="T",
                        position_x=0,
                        position_y=0,
                        position_z=0,
                        health=100,
                        armor=100,
                        weapon="AK-47",
                        alive_teammates=3,
                        alive_enemies=4,
                        nearest_teammate_distance=1400,
                        nearby_support=False,
                        moved_distance_5s=600,
                        effective_team_flashes_5s=0,
                        was_traded=False,
                    )
                ],
            }
        )
        evidence = analyze_engagement_decisions(match)

        references = retrieve_tactical_knowledge(
            match,
            "分析 A 大孤立前压和补枪问题",
            evidence,
        )

        self.assertEqual(len(references), 3)
        self.assertEqual(references[0].knowledge_id, "dust2-isolation-001")
        self.assertIn("isolation", references[0].matched_topics)

    def test_knowledge_retrieval_is_map_scoped(self):
        references = retrieve_tactical_knowledge(
            SAMPLE_MATCH,
            "分析补枪问题",
            [],
        )

        self.assertEqual(references, [])

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

    def test_engagement_tool_separates_isolation_from_failed_trade(self):
        base = {
            "tick": 100,
            "location": "LongA",
            "side": "T",
            "position_x": 0,
            "position_y": 0,
            "position_z": 0,
            "health": 100,
            "armor": 100,
            "weapon": "AK-47",
            "alive_teammates": 2,
            "alive_enemies": 3,
            "moved_distance_5s": 500,
            "effective_team_flashes_5s": 0,
            "was_traded": False,
        }
        match = SAMPLE_MATCH.model_copy(
            update={
                "engagements": [
                    EngagementRecord(
                        **base,
                        round_number=3,
                        classification="isolated_advance",
                        nearest_teammate_distance=1300,
                        nearby_support=False,
                    ),
                    EngagementRecord(
                        **base,
                        round_number=6,
                        classification="isolated_advance",
                        nearest_teammate_distance=1500,
                        nearby_support=False,
                    ),
                    EngagementRecord(
                        **base,
                        round_number=7,
                        classification="supported_contact",
                        nearest_teammate_distance=300,
                        nearby_support=True,
                    ),
                    EngagementRecord(
                        **base,
                        round_number=10,
                        classification="supported_contact",
                        nearest_teammate_distance=400,
                        nearby_support=True,
                    ),
                ]
            }
        )

        evidence = analyze_engagement_decisions(match)

        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence[0].severity, "high")
        self.assertEqual(evidence[0].round_numbers, [3, 6])
        self.assertIn("附近已有队友", evidence[1].finding)


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
        self.assertEqual(len(match.engagements), 1)
        self.assertEqual(match.engagements[0].classification, "supported_contact")
        self.assertEqual(match.engagements[0].location, "TestArea")
        self.assertEqual(match.engagements[0].moved_distance_5s, 400)
        self.assertEqual(match.engagements[0].effective_team_flashes_5s, 1)

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

        self.assertEqual(len(result.tools_used), 6)
        self.assertLessEqual(len(result.tools_used), 6)
        self.assertTrue(any(item.severity == "high" for item in result.evidence))
        self.assertEqual(result.confidence, "high")
        self.assertTrue(result.execution_trace[-1].startswith("reporter:"))

    def test_unknown_match_is_rejected(self):
        with self.assertRaises(KeyError):
            self.runtime.analyze(match_id="missing", question="复盘")

    def test_engagement_question_selects_situational_tool(self):
        result = self.runtime.analyze(
            match_id=SAMPLE_MATCH.match_id,
            question="分析我的接战局势和队友距离",
        )

        self.assertEqual(result.tools_used, ["engagements"])

    def test_dust2_report_exposes_knowledge_sources(self):
        match = SAMPLE_MATCH.model_copy(
            update={"match_id": "demo-dust2-kb", "map_name": "de_dust2"}
        )
        self.runtime.add_match(match)

        result = self.runtime.analyze(
            match_id=match.match_id,
            question="分析我的补枪和队友同步问题",
        )

        self.assertGreaterEqual(len(result.knowledge_references), 1)
        self.assertIn("Dust2 战术知识参考", result.answer)
        self.assertTrue(
            any("knowledge_retriever:" in step for step in result.execution_trace)
        )

    def test_report_exposes_round_decision_cards(self):
        engagement = EngagementRecord(
            round_number=3,
            tick=100,
            classification="isolated_advance",
            location="LongA",
            side="T",
            position_x=0,
            position_y=0,
            position_z=0,
            health=100,
            armor=100,
            weapon="AK-47",
            alive_teammates=3,
            alive_enemies=4,
            nearest_teammate_distance=1600,
            nearby_support=False,
            moved_distance_5s=700,
            effective_team_flashes_5s=0,
            was_traded=False,
        )
        match = SAMPLE_MATCH.model_copy(
            update={
                "match_id": "demo-dust2-cards",
                "map_name": "de_dust2",
                "engagements": [engagement],
            }
        )
        self.runtime.add_match(match)

        result = self.runtime.analyze(
            match_id=match.match_id,
            question="分析我的接战和孤立前压",
        )

        self.assertEqual(result.decision_cards[0].round_number, 3)
        self.assertEqual(result.decision_cards[0].risk_level, "high")
        self.assertIn("风险", result.answer)
        self.assertTrue(
            any("decision_scorer:" in step for step in result.execution_trace)
        )


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
        self.assertIn("decision_cards", body)
        self.assertIn("knowledge_references", body)

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
