"""Account editing/deletion and per-account storage limits."""

import pytest

from app.core.config import get_settings
from tests.conftest import register, upload_csv

CSV = "id,city,amount\n" + "\n".join(f"{i},{'ABC'[i % 3]},{i}" for i in range(1, 301)) + "\n"


def test_edit_profile_and_password(client, auth):
    r = client.patch("/api/v1/auth/me", headers=auth, json={"display_name": "Ada Lovelace"})
    assert r.json()["display_name"] == "Ada Lovelace"
    bad = client.post(
        "/api/v1/auth/me/password",
        headers=auth,
        json={"current_password": "nope", "new_password": "brand-new-pass"},
    )
    assert bad.status_code == 401
    ok = client.post(
        "/api/v1/auth/me/password",
        headers=auth,
        json={"current_password": "correct-horse-1", "new_password": "brand-new-pass"},
    )
    assert ok.status_code == 204
    login = client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": "brand-new-pass"}
    )
    assert login.status_code == 200


def test_delete_account_removes_everything(client, auth):
    p = upload_csv(client, auth, CSV)
    r = client.request(
        "DELETE",
        "/api/v1/auth/me",
        headers=auth,
        json={"confirm_email": "wrong@example.com", "password": "correct-horse-1"},
    )
    assert r.status_code == 422
    r = client.request(
        "DELETE",
        "/api/v1/auth/me",
        headers=auth,
        json={"confirm_email": "ADA@example.com", "password": "correct-horse-1"},
    )
    assert r.status_code == 204
    assert client.get(f"/api/v1/projects/{p['id']}", headers=auth).status_code == 401
    login = client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": "correct-horse-1"}
    )
    assert login.status_code == 401


def test_last_admin_cannot_delete_self(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_emails", "boss@example.com")
    h = register(client, "boss@example.com")
    r = client.request(
        "DELETE",
        "/api/v1/auth/me",
        headers=h,
        json={"confirm_email": "boss@example.com", "password": "correct-horse-1"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "LAST_ADMIN"


def test_storage_usage_and_quota(client, auth, monkeypatch):
    p = upload_csv(client, auth, CSV)
    st = client.get("/api/v1/auth/me/storage", headers=auth).json()
    assert st["quota_bytes"] == 3 * 1024**3  # free plan
    assert st["used_bytes"] > 0 and st["projects"][0]["id"] == p["id"]

    # Shrink the limit below current usage: new uploads, steps and exports are refused.
    monkeypatch.setattr("app.services.quota.MB", 1)  # 1 "MB" = 1 byte for this test
    client.patch("/api/v1/auth/me", headers=auth, json={"display_name": "x"})
    pl = client.get(f"/api/v1/projects/{p['id']}/pipeline", headers=auth).json()
    r = client.post(
        f"/api/v1/pipeline/{pl['id']}/steps",
        headers=auth,
        json={"step_type": "drop_duplicates", "params": {}},
    )
    assert r.status_code == 413 and r.json()["error"]["code"] == "STORAGE_QUOTA_EXCEEDED"
    r = client.post(f"/api/v1/projects/{p['id']}/exports", headers=auth, json={"kind": "script"})
    assert r.status_code == 413
    q = client.post("/api/v1/projects", json={"name": "Q"}, headers=auth).json()
    r = client.post(
        f"/api/v1/projects/{q['id']}/datasets",
        headers=auth,
        files={"file": ("d.csv", CSV.encode(), "text/csv")},
    )
    assert r.status_code == 413
    assert "Storage limit reached" in r.json()["error"]["message"]


def test_free_space_removes_undone_versions(client, auth):
    p = upload_csv(client, auth, CSV)
    pl = client.get(f"/api/v1/projects/{p['id']}/pipeline", headers=auth).json()
    for st in ("drop_duplicates", "trim_text"):
        params = {"columns": ["city"], "case": "lower"} if st == "trim_text" else {}
        r = client.post(
            f"/api/v1/pipeline/{pl['id']}/steps",
            headers=auth,
            json={"step_type": st, "params": params},
        )
        assert (
            client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=auth).json()["status"]
            == "succeeded"
        )
    client.post(f"/api/v1/pipeline/{pl['id']}/undo", headers=auth)
    before = client.get("/api/v1/auth/me/storage", headers=auth).json()["used_bytes"]
    r = client.post(f"/api/v1/projects/{p['id']}/free-space", headers=auth).json()
    assert r["deleted_versions"] == 1 and r["freed_bytes"] > 0
    after = client.get("/api/v1/auth/me/storage", headers=auth).json()["used_bytes"]
    assert after == before - r["freed_bytes"]
    versions = client.get(f"/api/v1/datasets/{p['dataset']['id']}/versions", headers=auth).json()
    assert len(versions) == 2  # original + the still-applied step
    rows = client.get(f"/api/v1/versions/{versions[-1]['id']}/rows?limit=1", headers=auth)
    assert rows.status_code == 200


@pytest.mark.parametrize("quota", [1, 0])
def test_admin_sets_user_quota(client, monkeypatch, quota):
    monkeypatch.setattr(get_settings(), "admin_emails", "boss@example.com")
    admin = register(client, "boss@example.com")
    register(client, "bob@example.com")
    bob = client.get("/api/v1/admin/users?q=bob", headers=admin).json()["items"][0]
    assert bob["storage_quota"] == 3 * 1024**3 and bob["custom_quota_mb"] is None  # free plan
    r = client.patch(
        f"/api/v1/admin/users/{bob['id']}", headers=admin, json={"storage_quota_mb": quota}
    ).json()
    if quota:
        assert r["custom_quota_mb"] == 1 and r["storage_quota"] == 1024 * 1024
    else:
        assert r["custom_quota_mb"] is None


PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def test_avatar_upload_serve_and_remove(client, auth):
    bad = client.post(
        "/api/v1/auth/me/avatar",
        headers=auth,
        files={"file": ("x.png", b"not an image", "image/png")},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "AVATAR_BAD_TYPE"
    big = client.post(
        "/api/v1/auth/me/avatar",
        headers=auth,
        files={"file": ("x.png", PNG_1PX + b"\0" * (2 * 1024 * 1024), "image/png")},
    )
    assert big.status_code == 422
    r = client.post(
        "/api/v1/auth/me/avatar", headers=auth, files={"file": ("me.png", PNG_1PX, "image/png")}
    )
    assert r.status_code == 200, r.text
    url = r.json()["avatar_url"]
    assert url.startswith("/api/v1/auth/avatars/") and url.endswith(".png")
    img = client.get(url)  # no auth header: <img> tags can't send one
    assert img.status_code == 200 and img.content == PNG_1PX
    assert img.headers["content-type"] == "image/png"
    assert client.get(url.replace(".png", "x.png")).status_code == 404
    gone = client.delete("/api/v1/auth/me/avatar", headers=auth)
    assert gone.json()["avatar_url"] is None
    assert client.get(url).status_code == 404
