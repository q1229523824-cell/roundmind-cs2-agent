import os
import unittest
from unittest.mock import Mock, patch

from chapter07_cs2_coach.local_server import (
    PUBLIC_WEB_URL,
    browser_target,
    configure_console_output,
    configure_deepseek_for_session,
    configure_local_environment,
)


class LocalServerTests(unittest.TestCase):
    def test_console_output_replaces_unsupported_characters(self):
        stream = Mock()

        configure_console_output((stream,))

        stream.reconfigure.assert_called_once_with(errors="replace")

    def test_public_browser_target_requests_local_processing(self):
        target = browser_target("http://127.0.0.1:8765", False)

        self.assertEqual(
            target,
            f"{PUBLIC_WEB_URL}/?processing=local#workspace",
        )
        self.assertEqual(
            browser_target("http://127.0.0.1:8765", True),
            "http://127.0.0.1:8765",
        )

    def test_desktop_launcher_forces_local_storage_boundaries(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://must-not-be-used",
                "ROUNDMIND_JOB_BACKEND": "celery",
                "ROUNDMIND_OBJECT_STORAGE": "s3",
                "ROUNDMIND_AUTH_REQUIRED": "true",
            },
            clear=False,
        ):
            configure_local_environment()

            self.assertNotIn("DATABASE_URL", os.environ)
            self.assertEqual(os.environ["ROUNDMIND_LOCAL_BRIDGE"], "true")
            self.assertEqual(os.environ["ROUNDMIND_JOB_BACKEND"], "local")
            self.assertEqual(os.environ["ROUNDMIND_OBJECT_STORAGE"], "local")
            self.assertEqual(os.environ["ROUNDMIND_KNOWLEDGE_BACKEND"], "local")
            self.assertEqual(os.environ["ROUNDMIND_AUTH_REQUIRED"], "false")

    def test_deepseek_opt_in_uses_user_key_for_current_process(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_deepseek_for_session(
                input_fn=lambda _prompt: "YES",
                secret_fn=lambda _prompt: "friend-owned-key",
            )

            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "friend-owned-key")
            self.assertEqual(os.environ["DEEPSEEK_MODEL"], "deepseek-chat")
            self.assertEqual(os.environ["DEEPSEEK_BASE_URL"], "https://api.deepseek.com")
            self.assertEqual(os.environ["ROUNDMIND_ENABLE_LLM_COACH"], "true")

    def test_deepseek_opt_in_requires_explicit_consent(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, "未发送任何数据"):
                configure_deepseek_for_session(
                    input_fn=lambda _prompt: "no",
                    secret_fn=lambda _prompt: self.fail("拒绝后不应读取 API Key"),
                )

            self.assertNotIn("DEEPSEEK_API_KEY", os.environ)


if __name__ == "__main__":
    unittest.main()
