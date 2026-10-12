"""One shared password: constant-time check and a small in-memory limiter on failures."""

from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque

MAX_FAILURES = 5
WINDOW_SECONDS = 600


def password_ok(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode(), expected.encode())


class LoginLimiter:
    """Blocks a client after MAX_FAILURES failed logins within WINDOW_SECONDS."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, client: str) -> deque[float]:
        q = self._failures[client]
        while q and self._clock() - q[0] > WINDOW_SECONDS:
            q.popleft()
        return q

    def blocked(self, client: str) -> bool:
        return len(self._recent(client)) >= MAX_FAILURES

    def fail(self, client: str) -> None:
        self._recent(client).append(self._clock())

    def reset(self, client: str) -> None:
        self._failures.pop(client, None)
