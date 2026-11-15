"""Dependency checks used by the health endpoint."""

import time
from collections.abc import Callable

import redis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine
from app.storage.s3 import get_s3_client


def _check_database() -> None:
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))


def _check_redis() -> None:
    client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
    try:
        client.ping()
    finally:
        client.close()


def _check_storage() -> None:
    get_s3_client().head_bucket(Bucket=get_settings().s3_bucket)


CHECKS: dict[str, Callable[[], None]] = {
    "database": _check_database,
    "redis": _check_redis,
    "storage": _check_storage,
}


def run_checks(checks: dict[str, Callable[[], None]] | None = None) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for name, check in (checks or CHECKS).items():
        start = time.perf_counter()
        try:
            check()
            results[name] = {"status": "ok"}
        except Exception as exc:  # noqa: BLE001 - report any failure as "down"
            results[name] = {"status": "down", "error": f"{type(exc).__name__}: {exc}"[:300]}
        results[name]["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
    return results
