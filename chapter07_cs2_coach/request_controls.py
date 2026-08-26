"""零外部依赖的单实例请求限流。"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from math import ceil
from threading import RLock
from time import monotonic

from fastapi import Request


@dataclass
class _Window:
    count: int
    reset_at: float


class InMemoryRateLimiter:
    """固定窗口限流；适合单实例低成本部署，扩容后应替换为 Redis。"""

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self._windows: dict[str, _Window] = {}
        self._lock = RLock()

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> int | None:
        """允许时返回 None；超限时返回建议等待秒数。"""
        if not self.enabled:
            return None
        current = monotonic() if now is None else now
        with self._lock:
            window = self._windows.get(key)
            if window is None or current >= window.reset_at:
                self._windows[key] = _Window(1, current + window_seconds)
                self._prune(current)
                return None
            if window.count >= limit:
                return max(1, ceil(window.reset_at - current))
            window.count += 1
            return None

    def _prune(self, now: float) -> None:
        if len(self._windows) <= 1000:
            return
        self._windows = {
            key: value for key, value in self._windows.items() if value.reset_at > now
        }


def client_identifier(request: Request, *, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        try:
            if forwarded:
                return str(ip_address(forwarded))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


__all__ = ["InMemoryRateLimiter", "client_identifier"]
