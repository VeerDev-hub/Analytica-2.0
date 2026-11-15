"""Admin panel (users, stats, settings) and Google/GitHub sign-in."""

from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import get_settings
from app.services import oauth
from tests.conftest import register, upload_csv


@pytest.fixture
def admin(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_emails", "boss@example.com")
    return register(client, "boss@example.com")


def test_admin_only(client, auth):
    for path in ("/api/v1/admin/stats", "/api/v1/admin/users", "/api/v1/admin/settings"):
        r = client.get(path, headers=auth)
        assert r.status_code == 403 and r.json()["error"]["code"] == "ADMIN_ONLY"


def test_admin_bootstrap_users_and_stats(client, admin):
    me = client.get("/api/v1/auth/me", headers=admin).json()
    assert me["role"] == "admin" and me["has_password"] and me["providers"] == []
    bob = register(client, "bob@example.com")
    upload_csv(client, bob, "a,b\n1,x\n2,y\n")

    st = client.get("/api/v1/admin/stats", headers=admin).json()
    assert st["users"]["total"] == 2 and st["users"]["admins"] == 1
    assert st["projects"]["total"] == 1 and st["projects"]["storage_bytes"] > 0
    assert st["jobs_7d"]["by_status"]["succeeded"] >= 1

    lst = client.get("/api/v1/admin/users?q=bob", headers=admin).json()
    assert lst["total"] == 1
    row = lst["items"][0]
    assert row["methods"] == ["email"] and row["projects"] == 1

    r = client.patch(f"/api/v1/admin/users/{row['id']}", headers=admin, json={"is_active": False})
    assert r.json()["is_active"] is False
    assert client.get("/api/v1/projects", headers=bob).status_code == 401  # disabled
    login = client.post(
        "/api/v1/auth/login", json={"email": "bob@example.com", "password": "correct-horse-1"}
    )
    assert login.status_code == 403

    client.patch(f"/api/v1/admin/users/{row['id']}", headers=admin, json={"role": "admin"})
    me_id = client.get("/api/v1/auth/me", headers=admin).json()["id"]
    r = client.patch(f"/api/v1/admin/users/{me_id}", headers=admin, json={"role": "user"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "SELF_LOCKOUT"


def test_runtime_settings(client, admin):
    cfg = client.get("/api/v1/admin/settings", headers=admin).json()
    assert cfg["values"]["signups_open"] is True
    assert "redirect_uri" in cfg["environment"]["oauth"]["google"]

    r = client.put(
        "/api/v1/admin/settings",
        headers=admin,
        json={
            "signups_open": False,
            "max_upload_mb": 1,
            "announcement": {"text": "Maintenance at 6pm", "tone": "warn"},
        },
    )
    assert r.status_code == 200
    meta = client.get("/api/v1/meta").json()
    assert meta["announcement"]["text"] == "Maintenance at 6pm" and not meta["signups_open"]

    r = client.post(
        "/api/v1/auth/register", json={"email": "new@example.com", "password": "long-enough-1"}
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "SIGNUPS_CLOSED"

    p = client.post("/api/v1/projects", json={"name": "P"}, headers=admin).json()
    big = b"a\n" + b"1\n" * 600_000
    r = client.post(
        f"/api/v1/projects/{p['id']}/datasets",
        headers=admin,
        files={"file": ("big.csv", big, "text/csv")},
    )
    assert r.status_code == 413

    for bad in ({"max_upload_mb": 0}, {"chat_model": "gpt-4"}, {"nope": 1}):
        assert client.put("/api/v1/admin/settings", headers=admin, json=bad).status_code == 422


def test_oauth_flow_creates_and_links_accounts(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "github_client_id", "cid")
    monkeypatch.setattr(s, "github_client_secret", "secret")
    assert client.get("/api/v1/auth/providers").json()["providers"] == ["github"]
    assert client.get("/api/v1/auth/oauth/google/start", follow_redirects=False).status_code == 501

    r = client.get("/api/v1/auth/oauth/github/start", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://github.com/")
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]

    # Wrong state is rejected.
    r = client.get("/api/v1/auth/oauth/github/callback?code=x&state=forged", follow_redirects=False)
    assert "error=OAUTH_FAILED" in r.headers["location"]

    # Existing email/password account gets linked, not duplicated.
    register(client, "ada@example.com")
    monkeypatch.setattr(
        oauth, "_profile", lambda name, code: ("42", "Ada@Example.com", "Ada L", "https://a/x.png")
    )
    r = client.get("/api/v1/auth/oauth/github/start", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = client.get(
        f"/api/v1/auth/oauth/github/callback?code=ok&state={state}", follow_redirects=False
    )
    assert r.headers["location"].endswith("/auth/callback")
    tok = client.post("/api/v1/auth/refresh").json()
    assert tok["user"]["email"] == "ada@example.com"
    assert tok["user"]["providers"] == ["github"] and tok["user"]["avatar_url"]

    # A brand-new GitHub user gets an account without a password.
    monkeypatch.setattr(oauth, "_profile", lambda name, code: ("7", "gh@example.com", "GH", None))
    r = client.get("/api/v1/auth/oauth/github/start", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    client.get(f"/api/v1/auth/oauth/github/callback?code=ok&state={state}", follow_redirects=False)
    me = client.post("/api/v1/auth/refresh").json()["user"]
    assert me["email"] == "gh@example.com" and me["has_password"] is False
    r = client.post("/api/v1/auth/login", json={"email": "gh@example.com", "password": "x"})
    assert r.json()["error"]["code"] == "USE_OAUTH"


def test_projects_list_has_dataset_summary(client, auth):
    upload_csv(client, auth, "a,b\n1,x\n2,y\n", name="tiny.csv")
    row = client.get("/api/v1/projects", headers=auth).json()[0]
    assert row["dataset_name"] == "tiny.csv" and row["rows"] == 2 and row["columns"] == 2
