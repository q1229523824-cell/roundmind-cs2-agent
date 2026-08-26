import os
import unittest
from unittest.mock import patch

from chapter07_cs2_coach.local_server import (
    PUBLIC_WEB_URL,
    browser_target,
    configure_local_environment,
)


class LocalServerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
