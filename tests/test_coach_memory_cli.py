import tempfile
import unittest
from pathlib import Path

from chapter07_cs2_coach.coach_cli import format_coach_report
from chapter07_cs2_coach.coach_memory import (
    CoachSession,
    CoachSessionStore,
    ConversationMessage,
    MAX_HISTORY_MESSAGES,
    history_payload,
    trim_history,
)
from chapter07_cs2_coach.models import CoachChatResponse


class CoachMemoryTests(unittest.TestCase):
    def test_session_round_trip_uses_anonymous_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CoachSessionStore(Path(directory))
            session = CoachSession(
                session_id="training-week",
                player_ref="player_0123456789ab",
                map_name="de_dust2",
            )
            path = store.append_exchange(
                session,
                question="把第三点展开讲讲",
                answer="第三点是受伤后重置枪线。",
            )

            self.assertNotIn("7656119", path.name)
            loaded = store.load(
                session_id="training-week",
                player_ref="player_0123456789ab",
                map_name="de_dust2",
            )
            self.assertEqual(len(loaded.messages), 2)
            self.assertEqual(history_payload(loaded)[0]["role"], "user")

    def test_history_keeps_only_recent_bounded_messages(self):
        messages = [
            ConversationMessage(role="user", content=f"问题 {index}")
            for index in range(MAX_HISTORY_MESSAGES + 5)
        ]

        trimmed = trim_history(messages)

        self.assertEqual(len(trimmed), MAX_HISTORY_MESSAGES)
        self.assertEqual(trimmed[-1].content, f"问题 {MAX_HISTORY_MESSAGES + 4}")

    def test_invalid_session_id_is_rejected(self):
        store = CoachSessionStore(Path("unused"))
        with self.assertRaisesRegex(ValueError, "会话名称"):
            store.load(
                session_id="../escape",
                player_ref="player_0123456789ab",
                map_name="de_dust2",
            )


class CoachCliFormattingTests(unittest.TestCase):
    def test_human_report_contains_readable_sections(self):
        response = CoachChatResponse(
            mode="llm",
            answer="优先练习受伤后重置枪线。",
            player_ref="player_0123456789ab",
            context_schema="roundmind.coach-context.v1",
            model_name="deepseek-chat",
            evidence_refs=["match_01:R3"],
            knowledge_ids=["dust2-isolation-001"],
            follow_up_questions=["要生成一周计划吗？"],
        )

        report = format_coach_report(response)

        self.assertIn("【教练结论】", report)
        self.assertIn("【关键证据】", report)
        self.assertIn("DeepSeek 智能教练", report)
        self.assertNotIn('"mode"', report)


if __name__ == "__main__":
    unittest.main()
