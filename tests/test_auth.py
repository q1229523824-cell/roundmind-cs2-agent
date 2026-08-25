import unittest

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from chapter07_cs2_coach.api import create_app
from chapter07_cs2_coach.auth import AuthService
from chapter07_cs2_coach.database import DatabaseBase
from chapter07_cs2_coach.runtime import CS2CoachRuntime
from chapter07_cs2_coach.sample_data import SAMPLE_MATCH


class AuthAndOwnershipTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        DatabaseBase.metadata.create_all(engine)
        auth = AuthService(
            enabled=True,
            engine=engine,
            jwt_secret="test-secret-that-is-at-least-32-characters-long",
        )
        self.client = TestClient(create_app(CS2CoachRuntime.create(), auth_service=auth))

    def _register(self, email):
        response = self.client.post(
            "/api/auth/register",
            json={"email": email, "password": "correct-horse-battery-staple"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    def test_protected_endpoint_requires_login(self):
        response = self.client.get("/api/matches")
        self.assertEqual(response.status_code, 401)

    def test_register_login_and_me(self):
        token = self._register("Player@Example.com")
        me = self.client.get("/api/auth/me", headers=self._headers(token))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "player@example.com")

        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "player@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
        self.assertEqual(login.status_code, 200)

    def test_matches_and_analysis_are_isolated_by_owner(self):
        first = self._register("first@example.com")
        second = self._register("second@example.com")
        match = SAMPLE_MATCH.model_copy(update={"match_id": "private-match"})

        created = self.client.post(
            "/api/matches", json=match.model_dump(mode="json"), headers=self._headers(first)
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(len(self.client.get("/api/matches", headers=self._headers(first)).json()), 1)
        self.assertEqual(self.client.get("/api/matches", headers=self._headers(second)).json(), [])

        forbidden = self.client.post(
            "/api/analyze",
            json={"match_id": "private-match", "question": "分析"},
            headers=self._headers(second),
        )
        self.assertEqual(forbidden.status_code, 404)


if __name__ == "__main__":
    unittest.main()
