"""Fixed-window rate limiting, shared across API replicas through Redis.

Falls back to an in-process counter when Redis is unreachable (tests, a Redis outage), so
the API keeps working with a per-replica limit instead of failing closed.

Usage in a route:

    check(request, "login:ip", limit=20, window_s=600)
    check(request, "login:email", limit=8, window_s=900, ident=body.email)
"""

from __future__ import annotations

import logging
import threading
import time

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import TooManyRequests

logger = logging.getLogger("app.ratelimit")


class RateLimiter:
    def __init__(self) -> None:
        self.enabled = get_settings().rate_limit_enabled
        self._redis = None
        self._redis_checked = False
        self._mem: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()
        self._last_prune = time.monotonic()

    # -- backends -----------------------------------------------------------------
    def _get_redis(self):
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        try:
            import redis

            client = redis.Redis.from_url(
                get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
            )
            client.ping()
            self._redis = client
        except Exception as exc:  # noqa: BLE001 - any failure means "use memory"
            logger.warning("rate limiter using in-memory counters (redis unavailable: %s)", exc)
            self._redis = None
        return self._redis

    def _hit_redis(self, client, key: str, window_s: int) -> tuple[int, int]:
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_s, nx=True)
        pipe.ttl(key)
        count, _, ttl = pipe.execute()
        return int(count), max(int(ttl), 1)

    def _hit_memory(self, key: str, window_s: int) -> tuple[int, int]:
        now = time.monotonic()
        with self._lock:
            if now - self._last_prune > 60:
                self._mem = {k: v for k, v in self._mem.items() if v[1] > now}
                self._last_prune = now
            count, reset = self._mem.get(key, (0, now + window_s))
            if reset <= now:
                count, reset = 0, now + window_s
            count += 1
            self._mem[key] = (count, reset)
            return count, max(int(reset - now), 1)

    # -- public -------------------------------------------------------------------
    def hit(self, key: str, window_s: int) -> tuple[int, int]:
        """Count one hit; return (hits in the current window, seconds until it resets)."""
        client = self._get_redis()
        if client is not None:
            try:
                return self._hit_redis(client, f"rl:{key}", window_s)
            except Exception as exc:  # noqa: BLE001
                logger.warning("rate limiter falling back to memory: %s", exc)
                self._redis = None
        return self._hit_memory(key, window_s)

    def reset(self) -> None:
        """Tests only."""
        with self._lock:
            self._mem.clear()
        client = self._get_redis()
        if client is not None:
            try:
                for k in client.scan_iter("rl:*"):
                    client.delete(k)
            except Exception:  # noqa: BLE001
                pass


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check(
    request: Request, scope: str, *, limit: int, window_s: int, ident: str | None = None
) -> None:
    """Raise 429 when `ident` (default: the client IP) exceeds `limit` hits per window."""
    if not limiter.enabled:
        return
    who = (ident or client_ip(request)).strip().lower()
    count, retry_after = limiter.hit(f"{scope}:{who}", window_s)
    if count > limit:
        minutes = max(1, round(retry_after / 60))
        wait = f"{retry_after} seconds" if retry_after < 90 else f"{minutes} minutes"
        raise TooManyRequests(
            f"Too many attempts. Try again in {wait}.",
            details={"retry_after": retry_after, "scope": scope},
            retry_after=retry_after,
        )
