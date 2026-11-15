from fastapi.testclient import TestClient

from app.main import create_app
from app.services import health as health_service


def _ok() -> None:
    return None


def _boom() -> None:
    raise ConnectionError("unreachable")


def test_health_all_ok(monkeypatch):
    monkeypatch.setattr(health_service, "CHECKS", {"database": _ok, "redis": _ok})
    client = TestClient(create_app())

    res = client.get("/api/v1/health")

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert set(body["dependencies"]) == {"database", "redis"}
    assert res.headers["X-Request-ID"]


def test_health_degraded_returns_503(monkeypatch):
    monkeypatch.setattr(health_service, "CHECKS", {"database": _ok, "redis": _boom})
    client = TestClient(create_app())

    res = client.get("/api/v1/health")

    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["redis"]["status"] == "down"
    assert "unreachable" in body["dependencies"]["redis"]["error"]


def test_request_id_is_echoed():
    client = TestClient(create_app())
    res = client.get("/api/v1/livez", headers={"X-Request-ID": "abc123"})
    assert res.headers["X-Request-ID"] == "abc123"
