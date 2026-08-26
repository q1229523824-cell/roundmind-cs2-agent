import unittest

from starlette.requests import Request

from chapter07_cs2_coach.request_controls import (
    InMemoryRateLimiter,
    client_identifier,
)


class RequestControlTests(unittest.TestCase):
    def test_disabled_limiter_never_blocks(self):
        limiter = InMemoryRateLimiter(enabled=False)

        for _ in range(10):
            self.assertIsNone(
                limiter.check("demo:client", limit=1, window_seconds=60, now=0)
            )

    def test_fixed_window_returns_retry_after_and_resets(self):
        limiter = InMemoryRateLimiter(enabled=True)

        self.assertIsNone(
            limiter.check("demo:client", limit=2, window_seconds=60, now=100)
        )
        self.assertIsNone(
            limiter.check("demo:client", limit=2, window_seconds=60, now=110)
        )
        self.assertEqual(
            limiter.check("demo:client", limit=2, window_seconds=60, now=125),
            35,
        )
        self.assertIsNone(
            limiter.check("demo:client", limit=2, window_seconds=60, now=160)
        )

    def test_buckets_are_isolated(self):
        limiter = InMemoryRateLimiter(enabled=True)

        self.assertIsNone(limiter.check("a", limit=1, window_seconds=60, now=0))
        self.assertEqual(limiter.check("a", limit=1, window_seconds=60, now=1), 59)
        self.assertIsNone(limiter.check("b", limit=1, window_seconds=60, now=1))

    def test_proxy_client_uses_valid_rightmost_forwarded_address(self):
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [
                    (b"x-forwarded-for", b"198.51.100.2, 203.0.113.9")
                ],
                "client": ("10.0.0.5", 1234),
            }
        )

        self.assertEqual(
            client_identifier(request, trust_proxy_headers=True), "203.0.113.9"
        )
        self.assertEqual(
            client_identifier(request, trust_proxy_headers=False), "10.0.0.5"
        )


if __name__ == "__main__":
    unittest.main()
