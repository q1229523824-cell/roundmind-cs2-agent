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
from chapter07_cs2_coach.contact_analysis import (
    compare_contact_outcomes,
    evaluate_contact_coverage,
    find_contact_hotspots,
)
from chapter07_cs2_coach.coach_context import MAX_CONTEXT_BYTES, build_coach_context
from chapter07_cs2_coach.coach_llm import CoachService
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
from chapter07_cs2_coach.models import ContactEpisode, EngagementRecord, MatchRecord
from chapter07_cs2_coach.player_profile import build_player_profile
from chapter07_cs2_coach.personal_baseline import build_personal_contact_contrasts
from chapter07_cs2_coach.profile_cli import (
    build_profile_from_demos,
    collect_demo_paths,
)
from chapter07_cs2_coach.quality_audit import audit_match, audit_matches
from chapter07_cs2_coach.runtime import CS2CoachRuntime
from chapter07_cs2_coach.sample_data import SAMPLE_MATCH
from chapter07_cs2_coach.tools import analyze_engagement_decisions, get_match_summary
from chapter07_cs2_coach.weapon_role_profile import (
    build_first_damage_disadvantage_segments,
    build_weapon_profile,
    infer_role_profile,
    weapon_category,
)


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
                            "yaw": 0,
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
                            "yaw": 0,
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
                            "yaw": 180,
                            "last_place_name": "EnemyArea",
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


class ContextAwareDemoParser(FakeDemoParser):
    """提供炸弹与烟雾事件，验证增强接战快照。"""

    def __init__(self, path: str):
        super().__init__(path)
        self.events.update(
            {
                "bomb_planted": [
                    {
                        "tick": 1400,
                        "total_rounds_played": 1,
                        "site": 96,
                    }
                ],
                "bomb_defused": [],
                "bomb_exploded": [],
                "smokegrenade_detonate": [
                    {
                        "tick": 1450,
                        "total_rounds_played": 1,
                        "entityid": 10,
                        "x": 450,
                        "y": 0,
                        "z": 0,
                    }
                ],
                "smokegrenade_expired": [
                    {
                        "tick": 1700,
                        "total_rounds_played": 1,
                        "entityid": 10,
                        "x": 450,
                        "y": 0,
                        "z": 0,
                    }
                ],
            }
        )
        self.events["player_hurt"].append(
            {
                "tick": 1490,
                "total_rounds_played": 1,
                "attacker_name": "Enemy",
                "attacker_steamid": "2",
                "attacker_team_name": "TERRORIST",
                "user_name": "Learner",
                "user_steamid": "1",
                "user_team_name": "CT",
                "dmg_health": 30,
                "weapon": "ak47",
            }
        )


class InlineExecutor:
    def submit(self, function, *args, **kwargs):
        future = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except Exception as error:  # pragma: no cover - Future 行为兼容
            future.set_exception(error)
        return future


class FakeCoachModel:
    model_name = "fake-coach"

    def __init__(self, response: dict):
        self.response = response
        self.context_json = ""
        self.question = ""

    def complete(self, *, context_json: str, question: str) -> str:
        self.context_json = context_json
        self.question = question
        return json.dumps(self.response, ensure_ascii=False)


class DuplicateNameDemoParser(FakeDemoParser):
    def parse_player_info(self):
        return super().parse_player_info() + [{"name": "Learner", "steamid": "4"}]


class WarmupRoundEndDemoParser(FakeDemoParser):
    def __init__(self, path: str):
        super().__init__(path)
        self.events["round_end"].insert(
            0,
            {
                "tick": 1,
                "round": 0,
                "total_rounds_played": 0,
                "winner": None,
            },
        )
        self.events["round_announce_match_start"] = [
            {"tick": 100, "total_rounds_played": 0}
        ]
        self.events["player_death"].insert(
            0,
            {
                "tick": 50,
                "total_rounds_played": 0,
                "attacker_name": "Learner",
                "attacker_steamid": "1",
                "attacker_team_name": "TERRORIST",
                "user_name": "WarmupEnemy",
                "user_steamid": "9",
                "user_team_name": "CT",
                "assister_name": "",
            },
        )


def quality_ready_match(
    *, match_id: str = "quality-pass", player_steamid: str = "42"
) -> MatchRecord:
    engagement = EngagementRecord(
        round_number=1, tick=200, classification="supported_contact",
        location="LongA", side="T", position_x=0, position_y=0, position_z=0,
        health=0, armor=80, weapon="ak47", alive_teammates=3, alive_enemies=2,
        nearest_teammate_distance=400, nearby_support=True,
        moved_distance_5s=100, effective_team_flashes_5s=1, was_traded=True,
    )
    contacts = [
        ContactEpisode(
            round_number=1, start_tick=100, end_tick=150, location="LongA",
            side="T", first_damage_by_player=True, damage_dealt=100,
            damage_taken=0, outcome="kill", duration_seconds=1, weapon="ak47",
            health_before_contact=100, armor_before_contact=100,
            opponent_distance=600, alive_teammates=0,
            nearest_teammate_distance=None, player_view_angle_error=5,
            support_ready_teammates_proxy=None,
        ),
        ContactEpisode(
            round_number=1, start_tick=180, end_tick=200, location="LongA",
            side="T", first_damage_by_player=False, damage_dealt=0,
            damage_taken=100, outcome="death", duration_seconds=0.5,
            weapon="ak47", health_before_contact=100, armor_before_contact=80,
            opponent_distance=700, alive_teammates=3,
            nearest_teammate_distance=400, player_view_angle_error=15,
            support_ready_teammates_proxy=1,
        ),
    ]
    return MatchRecord.model_validate(
        {
            "match_id": match_id, "player_name": "Learner",
            "player_steamid": player_steamid, "map_name": "de_dust2",
            "team_name": "A", "opponent_name": "B",
            "team_score": 1, "opponent_score": 0,
            "rounds": [{"number": 1, "side": "T", "won": True,
                        "kills": 1, "died": True}],
            "engagements": [engagement.model_dump()],
            "contact_episodes": [item.model_dump() for item in contacts],
        }
    )


class CS2CoachToolTests(unittest.TestCase):
    def test_llm_coach_accepts_only_whitelisted_citations(self):
        steamid = "76561198012345678"
        matches = [
            quality_ready_match(
                match_id=f"coach-match-{index}", player_steamid=steamid
            )
            for index in range(1, 4)
        ]
        model = FakeCoachModel(
            {
                "answer": "先处理步枪被先手后的二次接触。",
                "evidence_refs": ["match_01:R1"],
                "knowledge_ids": [],
                "follow_up_questions": ["要生成训练计划吗？"],
            }
        )

        response = CoachService(model).answer(
            matches,
            player_steamid=steamid,
            map_name="de_dust2",
            question="我下一步练什么？",
        )

        self.assertEqual(response.mode, "llm")
        self.assertEqual(response.model_name, "fake-coach")
        self.assertNotIn(steamid, model.context_json)
        self.assertNotIn("Learner", model.context_json)
        self.assertEqual(model.question, "我下一步练什么？")

    def test_llm_coach_falls_back_on_fabricated_citation(self):
        steamid = "76561198012345678"
        matches = [
            quality_ready_match(
                match_id=f"coach-match-{index}", player_steamid=steamid
            )
            for index in range(1, 4)
        ]
        model = FakeCoachModel(
            {
                "answer": "虚构回答",
                "evidence_refs": ["match_99:R99"],
                "knowledge_ids": ["invented-knowledge"],
                "follow_up_questions": [],
            }
        )

        response = CoachService(model).answer(
            matches,
            player_steamid=steamid,
            map_name="de_dust2",
            question="分析我",
        )

        self.assertEqual(response.mode, "offline")
        self.assertTrue(response.validation_warnings)
        self.assertNotIn("虚构回答", response.answer)

    def test_coach_context_is_bounded_and_anonymous(self):
        steamid = "76561198012345678"
        matches = [
            quality_ready_match(
                match_id=f"secret-match-{index}", player_steamid=steamid
            )
            for index in range(1, 4)
        ]

        package = build_coach_context(
            matches, player_steamid=steamid, map_name="de_dust2"
        )
        serialized = package.model_dump_json()

        self.assertLessEqual(len(serialized.encode("utf-8")), MAX_CONTEXT_BYTES)
        self.assertNotIn(steamid, serialized)
        self.assertNotIn("Learner", serialized)
        self.assertNotIn("secret-match", serialized)
        self.assertEqual(package.sample.matches, 3)
        self.assertGreaterEqual(len(package.evidence_cases), 1)
        self.assertGreaterEqual(len(package.training_priorities), 1)
        self.assertTrue(
            all(item.match_ref.startswith("match_") for item in package.evidence_cases)
        )

    def test_weapon_role_profile_is_evidence_based(self):
        self.assertEqual(weapon_category("weapon_awp"), "sniper")
        self.assertEqual(weapon_category("M4A1-Silencer"), "rifle")
        episodes = []
        for index in range(30):
            own_first = index % 12 < 6
            strong_outcome = "kill" if index % 6 != 5 else "death"
            weak_outcome = "kill" if index % 6 == 0 else "death"
            episodes.append(
                ContactEpisode(
                    round_number=1,
                    start_tick=index * 100,
                    end_tick=index * 100 + 20,
                    location="LongA",
                    side="T",
                    first_damage_by_player=own_first,
                    damage_dealt=100 if own_first else 20,
                    damage_taken=20 if own_first else 100,
                    outcome=strong_outcome if own_first else weak_outcome,
                    duration_seconds=0.3,
                    weapon="awp" if index < 20 else "ak47",
                    health_before_contact=100,
                    armor_before_contact=100,
                    opponent_distance=900,
                    alive_teammates=2,
                    nearest_teammate_distance=400,
                    player_view_angle_error=10,
                    support_ready_teammates_proxy=1,
                )
            )
        weapons = build_weapon_profile(episodes)
        role = infer_role_profile(
            [quality_ready_match(match_id=f"role-{index}") for index in range(3)],
            weapons,
        )
        segments = build_first_damage_disadvantage_segments(episodes)

        self.assertEqual(weapons[0].category, "sniper")
        self.assertEqual(weapons[0].contacts, 20)
        self.assertEqual(role.role, "primary_awper")
        self.assertEqual(role.confidence, "medium")
        self.assertTrue(
            any(item.dimension == "distance" for item in segments)
        )

    def test_quality_gate_passes_complete_match(self):
        match = quality_ready_match()

        audit = audit_match(match)
        batch = audit_matches([match])

        self.assertEqual(audit.gate, "pass")
        self.assertEqual(audit.quality_score, 100)
        self.assertEqual(batch.passed, 1)

    def test_quality_gate_rejects_missing_event_coverage(self):
        audit = audit_match(SAMPLE_MATCH)

        self.assertEqual(audit.gate, "fail")
        self.assertTrue(any(
            item.key == "contact_death_coverage" and item.status == "fail"
            for item in audit.checks
        ))

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

    def test_smoke_obstruction_reduces_confidence_in_nearby_support(self):
        engagement = EngagementRecord(
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
            was_traded=False,
            smoke_between_player_and_nearest_teammate=False,
        )
        blocked = engagement.model_copy(
            update={"smoke_between_player_and_nearest_teammate": True}
        )
        match = SAMPLE_MATCH.model_copy(
            update={"map_name": "de_dust2", "engagements": [engagement, blocked]}
        )

        clear_card = score_engagement(match, engagement)
        blocked_card = score_engagement(match, blocked)

        self.assertEqual(blocked_card.risk_score, clear_card.risk_score + 12)
        self.assertEqual(blocked_card.confidence, "medium")
        self.assertTrue(any("烟雾" in factor for factor in blocked_card.factors))

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

    def test_contact_comparison_uses_kills_deaths_and_keeps_disengagements(self):
        outcomes = [
            ("kill", True, 1),
            ("kill", True, 2),
            ("kill", True, 3),
            ("death", True, 4),
            ("kill", False, 5),
            ("death", False, 6),
            ("death", False, 7),
            ("death", False, 8),
            ("disengaged", False, 9),
        ]
        contacts = [
            ContactEpisode(
                round_number=round_number,
                start_tick=round_number * 100,
                end_tick=round_number * 100 + 10,
                location="LongA",
                side="T",
                first_damage_by_player=first_damage,
                damage_dealt=80 if outcome == "kill" else 20,
                damage_taken=80 if outcome == "death" else 20,
                outcome=outcome,
                duration_seconds=0.2,
                health_before_contact=100,
                armor_before_contact=100,
                alive_teammates=2,
                nearest_teammate_distance=300,
                support_ready_teammates_proxy=1 if first_damage else 0,
            )
            for outcome, first_damage, round_number in outcomes
        ]

        comparison = compare_contact_outcomes(contacts)

        self.assertEqual(comparison.all_contacts.total, 9)
        self.assertEqual(comparison.all_contacts.disengaged, 1)
        self.assertEqual(comparison.first_damage_by_player.kill_rate, 0.75)
        self.assertEqual(comparison.first_damage_by_opponent.kill_rate, 0.25)
        self.assertEqual(
            comparison.first_damage_by_player.smoothed_kill_rate, 0.6667
        )
        lower, upper = comparison.first_damage_by_player.kill_rate_interval
        self.assertLess(lower, comparison.first_damage_by_player.kill_rate)
        self.assertGreater(upper, comparison.first_damage_by_player.kill_rate)
        self.assertEqual(comparison.first_damage_by_player.evidence_strength, "low")

        hotspots = find_contact_hotspots(contacts, min_resolved=3)
        self.assertEqual(hotspots[0].location, "LongA")
        self.assertEqual(hotspots[0].stats.resolved, 8)

        match = SAMPLE_MATCH.model_copy(update={"contact_episodes": contacts})
        evidence = analyze_engagement_decisions(match)
        findings = "\n".join(item.finding for item in evidence)
        self.assertIn("先取得有效伤害", findings)
        self.assertIn("队友空间距离近", findings)
        self.assertIn("95% 区间", "\n".join(item.metric for item in evidence))
        contrasts = build_personal_contact_contrasts(match)
        self.assertGreaterEqual(len(contrasts), 1)
        self.assertEqual(contrasts[0].location, "LongA")
        self.assertGreaterEqual(contrasts[0].similarity_score, 65)

        matches = [
            SAMPLE_MATCH.model_copy(
                update={
                    "match_id": f"profile-{index}",
                    "player_steamid": "42",
                    "map_name": "de_dust2",
                    "contact_episodes": contacts,
                }
            )
            for index in range(3)
        ]
        profile = build_player_profile(
            matches,
            player_steamid="42",
            map_name="de_dust2",
            enforce_quality=False,
        )

        self.assertEqual(profile.match_count, 3)
        self.assertEqual(profile.contact_count, 27)
        recurring = {item.key: item for item in profile.findings}
        self.assertEqual(recurring["first-damage-conversion"].status, "recurring")
        self.assertEqual(
            recurring["support-readiness-conversion"].confidence, "medium"
        )
        single_profile = build_player_profile(
            matches[:1],
            player_steamid="42",
            map_name="de_dust2",
            enforce_quality=False,
        )
        self.assertTrue(
            all(
                item.title.startswith("本场")
                for item in single_profile.findings
            )
        )
        deduplicated = build_player_profile(
            [matches[0], matches[0]],
            player_steamid="42",
            map_name="de_dust2",
            enforce_quality=False,
        )
        self.assertEqual(deduplicated.match_count, 1)

    def test_player_profile_quality_gate_rejects_bad_matches(self):
        accepted = quality_ready_match(match_id="accepted")
        rejected = SAMPLE_MATCH.model_copy(
            update={
                "match_id": "rejected",
                "player_steamid": "42",
                "map_name": "de_dust2",
            }
        )

        profile = build_player_profile(
            [accepted, rejected],
            player_steamid="42",
            map_name="de_dust2",
        )

        self.assertEqual(profile.source_match_count, 2)
        self.assertEqual(profile.match_count, 1)
        self.assertEqual(profile.rejected_match_count, 1)
        self.assertEqual(profile.quality_gate, "review")
        self.assertGreaterEqual(len(profile.quality_warnings), 1)

    def test_player_profile_keeps_review_match_with_warning(self):
        accepted = quality_ready_match(match_id="accepted")
        review_source = quality_ready_match(match_id="review")
        review_contacts = list(review_source.contact_episodes)
        review_contacts[1] = review_contacts[1].model_copy(
            update={"support_ready_teammates_proxy": None}
        )
        review = review_source.model_copy(
            update={"contact_episodes": review_contacts}
        )

        profile = build_player_profile(
            [accepted, review],
            player_steamid="42",
            map_name="de_dust2",
        )

        self.assertEqual(profile.match_count, 2)
        self.assertEqual(profile.review_match_count, 1)
        self.assertEqual(profile.rejected_match_count, 0)
        self.assertEqual(profile.quality_gate, "review")
        self.assertLess(profile.quality_score_average, 100)

    def test_player_profile_refuses_all_failed_matches(self):
        rejected = SAMPLE_MATCH.model_copy(
            update={"player_steamid": "42", "map_name": "de_dust2"}
        )

        with self.assertRaisesRegex(KeyError, "质量门禁"):
            build_player_profile(
                [rejected], player_steamid="42", map_name="de_dust2"
            )

    def test_local_profile_batch_deduplicates_paths_and_parses_matches(self):
        parser = CS2DemoMatchParser(FakeDemoParser)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.dem"
            second = root / "second.dem"
            ignored = root / "notes.txt"
            first.write_bytes(b"PBDEMS2\x00first")
            second.write_bytes(b"PBDEMS2\x00second")
            ignored.write_text("ignore", encoding="utf-8")

            paths = collect_demo_paths(
                [first, first],
                root,
                max_files=20,
            )
            profile, failures = build_profile_from_demos(
                paths,
                player_steamid="1",
                map_name="de_mirage",
                parser=parser,
                enforce_quality=False,
            )

        self.assertEqual(paths, [first.resolve(), second.resolve()])
        self.assertEqual(profile.match_count, 2)
        self.assertEqual(failures, [])

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
    def test_warmup_round_end_is_not_counted_as_official_round(self):
        parser = CS2DemoMatchParser(WarmupRoundEndDemoParser)
        with tempfile.NamedTemporaryFile(suffix=".dem", delete=False) as handle:
            handle.write(b"PBDEMS2\x00fake-demo")
            path = Path(handle.name)
        try:
            match = parser.parse(path, player_name="Learner", player_steamid="1")
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(len(match.rounds), 2)
        self.assertEqual([item.kills for item in match.rounds], [1, 0])
        self.assertEqual([item.died for item in match.rounds], [False, True])

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
        self.assertEqual(match.engagements[0].bomb_state, "unknown")
        self.assertIsNone(
            match.engagements[0].smoke_between_player_and_nearest_teammate
        )
        self.assertEqual(len(match.contact_episodes), 1)
        self.assertEqual(match.contact_episodes[0].outcome, "kill")
        coverage = evaluate_contact_coverage(1, 1, match.contact_episodes)
        self.assertEqual(coverage.kill_coverage, 1.0)
        self.assertEqual(coverage.death_coverage, 0.0)

    def test_context_events_enrich_engagement_snapshot(self):
        parser = CS2DemoMatchParser(ContextAwareDemoParser)
        with tempfile.NamedTemporaryFile(suffix=".dem", delete=False) as handle:
            handle.write(b"PBDEMS2\x00fake-demo")
            path = Path(handle.name)
        try:
            match = parser.parse(path, "Learner", "1")
        finally:
            path.unlink(missing_ok=True)

        engagement = match.engagements[0]
        self.assertEqual(engagement.round_elapsed_seconds, 6.2)
        self.assertEqual(engagement.bomb_state, "planted")
        self.assertEqual(engagement.bombsite, "A")
        self.assertEqual(engagement.seconds_since_bomb_plant, 1.5)
        self.assertEqual(engagement.active_smokes_nearby, 1)
        self.assertTrue(engagement.smoke_between_player_and_nearest_teammate)
        self.assertEqual(engagement.killer_distance, 400)
        self.assertEqual(engagement.killer_location, "EnemyArea")
        self.assertIsNone(engagement.killing_weapon)
        self.assertEqual(engagement.seconds_from_killer_first_damage_to_death, 0.2)
        self.assertEqual(engagement.nearest_teammate_view_angle_error, 0)
        self.assertTrue(engagement.nearest_teammate_facing_killer)
        self.assertEqual(engagement.support_ready_teammates_proxy, 0)
        self.assertEqual(
            [item.outcome for item in match.contact_episodes], ["kill", "death"]
        )
        coverage = evaluate_contact_coverage(1, 1, match.contact_episodes)
        self.assertEqual(coverage.kill_coverage, 1.0)
        self.assertEqual(coverage.death_coverage, 1.0)

    def test_smoke_segment_proxy_respects_distance_and_height(self):
        blocks = CS2DemoMatchParser._smoke_blocks_segment

        self.assertTrue(blocks((0, 0, 0), (500, 0, 0), (250, 100, 0)))
        self.assertFalse(blocks((0, 0, 0), (500, 0, 0), (250, 250, 0)))
        self.assertFalse(blocks((0, 0, 0), (500, 0, 0), (250, 0, 400)))

    def test_view_angle_proxy_handles_wraparound(self):
        row = {"X": 0, "Y": 0, "Z": 0, "yaw": -179}

        error = CS2DemoMatchParser._view_angle_error(row, (-100, 1, 0))

        self.assertLessEqual(error, 2)

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
        health = self.client.get("/health").json()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["version"], "local")

    def test_player_profile_endpoint_uses_steamid_and_map_filter(self):
        match = quality_ready_match(match_id="profile-api-test")
        self.client.app.state.runtime.add_match(match)

        response = self.client.get(
            "/api/player-profiles/42",
            params={"map_name": "de_dust2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["match_count"], 1)
        self.assertEqual(response.json()["confidence"], "low")
        self.assertEqual(response.json()["findings"], [])
        self.assertEqual(response.json()["quality_gate"], "pass")
        self.assertEqual(response.json()["quality_score_average"], 100.0)
        self.assertGreaterEqual(len(response.json()["weapon_profile"]), 1)
        self.assertIsNotNone(response.json()["role_profile"])
        self.assertIn("first_damage_disadvantage_segments", response.json())
        self.assertEqual(
            self.client.get("/api/player-profiles/missing").status_code, 404
        )

    def test_coach_chat_defaults_to_safe_offline_mode(self):
        steamid = "76561198012345678"
        for index in range(1, 4):
            self.client.app.state.runtime.add_match(
                quality_ready_match(
                    match_id=f"api-coach-{index}", player_steamid=steamid
                )
            )

        response = self.client.post(
            "/api/coach/chat",
            json={
                "player_steamid": steamid,
                "map_name": "de_dust2",
                "question": "我下一步练什么？",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "offline")
        self.assertTrue(response.json()["evidence_refs"])
        self.assertNotIn(steamid, response.json()["answer"])

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
        self.assertIn("personal_contact_contrasts", body)

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
