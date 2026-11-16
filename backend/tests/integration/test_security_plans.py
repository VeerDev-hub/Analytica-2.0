"""Sign-up protections (password strength, disposable emails, mailbox aliases), rate
limiting, and plan-based storage / assistant access."""

import pytest

from app.core import emails, passwords
from app.core.ratelimit import limiter
from tests.conftest import register


def _register(client, email, password="correct-horse-1", name="Ada"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": name},
    )


# ---------------------------------------------------------------- passwords
@pytest.mark.parametrize(
    "pw",
    ["password", "Password1", "12345678", "qwertyuiop", "aaaaaaaa", "abcdefgh", "short1!"],
)
def test_weak_passwords_rejected(pw):
    assert passwords.problems(pw)


@pytest.mark.parametrize(
    "pw", ["correct-horse-1", "brand-new-pass", "Tr0ub4dor&3", "a" * 8 + "B1!"]
)
def test_acceptable_passwords(pw):
    assert passwords.problems(pw) == []


def test_password_cannot_contain_name_or_email():
    assert passwords.problems("ada.lovelace-2026", email="ada.lovelace@example.com")
    assert passwords.problems("Lovelace#2026x", name="Ada Lovelace")


def test_register_rejects_weak_password(client):
    r = _register(client, "ada@example.com", password="password123")
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEAK_PASSWORD"


def test_change_password_rejects_weak(client, auth):
    r = client.post(
        "/api/v1/auth/me/password",
        headers=auth,
        json={"current_password": "correct-horse-1", "new_password": "qwerty123"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEAK_PASSWORD"


# ---------------------------------------------------------------- emails
def test_disposable_detection():
    assert emails.is_disposable("x@mailinator.com")
    assert emails.is_disposable("x@sub.yopmail.com")
    assert not emails.is_disposable("x@gmail.com")
    assert emails.is_disposable("x@corp.example", "corp.example, other.test")


def test_list_is_large_and_spares_real_providers():
    assert len(emails._builtin_domains()) > 50_000
    for real in ("x@gmail.com", "x@outlook.com", "x@yahoo.com", "x@proton.me", "x@icloud.com"):
        assert not emails.is_disposable(real), real


def _fake_mx(table):
    def resolve(domain):
        return table.get(domain, ("nxdomain", ()))

    return resolve


def test_mx_layer(monkeypatch):
    monkeypatch.setattr(
        emails,
        "_resolve_mx",
        _fake_mx(
            {
                # a brand-new mail.tm domain that no list knows yet
                "fresh-rotating.com": ("ok", ("in.mail.tm",)),
                "nomail.com": ("nomail", ()),
                "dnsdown.com": ("error", ()),
                "company.com": ("ok", ("company-com.mail.protection.outlook.com",)),
                "selfhosted.org": ("ok", ("mx1.selfhosted.org",)),
            }
        ),
    )

    def code(addr):
        try:
            emails.check_allowed(addr)
        except Exception as exc:  # noqa: BLE001
            return exc.code
        return "ok"

    assert code("a@fresh-rotating.com") == "DISPOSABLE_EMAIL"
    assert code("a@made-up-domain.com") == "EMAIL_DOMAIN_INVALID"
    assert code("a@nomail.com") == "EMAIL_DOMAIN_INVALID"
    assert code("a@dnsdown.com") == "ok"  # fail open on resolver trouble
    assert code("a@company.com") == "ok"  # Microsoft 365 custom domain
    assert code("a@selfhosted.org") == "ok"
    assert code("a@gmail.com") == "ok"  # allowlisted: no lookup at all
    # admin-blocked mail host also catches every domain that points at it
    with pytest.raises(Exception) as e:
        emails.check_allowed("a@selfhosted.org", "selfhosted.org")
    assert e.value.code == "DISPOSABLE_EMAIL"


def test_register_uses_dns_check(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "email_dns_check", True)
    monkeypatch.setattr(
        emails, "_resolve_mx", _fake_mx({"fresh-rotating.com": ("ok", ("in.mail.tm",))})
    )
    r = _register(client, "someone@fresh-rotating.com")
    assert r.status_code == 422 and r.json()["error"]["code"] == "DISPOSABLE_EMAIL"
    r = _register(client, "someone@no-such-domain-xyz.com")
    assert r.status_code == 422 and r.json()["error"]["code"] == "EMAIL_DOMAIN_INVALID"


def test_canonical_email():
    assert emails.canonical("Ada.Love+news@GMail.com") == "adalove@gmail.com"
    assert emails.canonical("ada+tag@outlook.com") == "ada@outlook.com"
    assert emails.canonical("a.d.a@outlook.com") == "a.d.a@outlook.com"


def test_register_rejects_disposable_email(client):
    r = _register(client, "someone@10minutemail.com")
    assert r.status_code == 422 and r.json()["error"]["code"] == "DISPOSABLE_EMAIL"


def test_register_rejects_alias_of_existing_mailbox(client):
    assert _register(client, "ada.lovelace@gmail.com").status_code == 201
    aliases = (
        "adalovelace@gmail.com",
        "ada.lovelace+two@gmail.com",
        "a.d.a.lovelace@googlemail.com",
    )
    for alias in aliases:
        r = _register(client, alias)
        assert r.status_code == 409, alias
        assert r.json()["error"]["code"] == "EMAIL_TAKEN"


def test_admin_blocked_domains(client):
    admin = register(client, "admin@example.com")
    client.patch("/api/v1/auth/me", headers=admin, json={"display_name": "Admin"})
    from sqlalchemy import select

    from app.core.db import session_scope
    from app.models import User

    with session_scope() as db:
        db.scalars(select(User).where(User.email == "admin@example.com")).one().role = "admin"
        db.commit()
    r = client.put(
        "/api/v1/admin/settings", headers=admin, json={"blocked_email_domains": "evil.example"}
    )
    assert r.status_code == 200, r.text
    assert _register(client, "bob@evil.example").status_code == 422
    assert _register(client, "bob@fine.example").status_code == 201


# ---------------------------------------------------------------- rate limits
def test_login_rate_limit(client, auth, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    body = {"email": "ada@example.com", "password": "wrong-password-xx"}
    codes = [client.post("/api/v1/auth/login", json=body).status_code for _ in range(9)]
    assert codes[:8] == [401] * 8
    assert codes[8] == 429
    last = client.post("/api/v1/auth/login", json=body)
    assert last.json()["error"]["code"] == "RATE_LIMITED"
    assert int(last.headers["retry-after"]) > 0
    limiter.reset()


def test_register_rate_limit_per_ip(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    codes = [_register(client, f"u{i}@example.com").status_code for i in range(6)]
    assert codes[:5] == [201] * 5 and codes[5] == 429
    limiter.reset()


# ---------------------------------------------------------------- plans
def test_free_plan_storage_and_assistant(client, auth):
    me = client.get("/api/v1/auth/me", headers=auth).json()
    assert me["plan"] == "free"
    storage = client.get("/api/v1/auth/me/storage", headers=auth).json()
    assert storage["quota_bytes"] == 3 * 1024**3 and storage["plan"] == "free"
    status = client.get("/api/v1/chat/status", headers=auth).json()
    assert status["allowed"] is False and status["plan"] == "free"
    p = client.post("/api/v1/projects", json={"name": "P"}, headers=auth).json()
    r = client.post(f"/api/v1/projects/{p['id']}/chat/sessions", headers=auth)
    assert r.status_code == 403 and r.json()["error"]["code"] == "PLAN_REQUIRED"


def test_admin_assigns_plan(client):
    admin = register(client, "admin@example.com")
    from sqlalchemy import select

    from app.core.db import session_scope
    from app.models import User

    with session_scope() as db:
        db.scalars(select(User).where(User.email == "admin@example.com")).one().role = "admin"
        db.commit()
    bob = register(client, "bob@example.com")
    bob_id = client.get("/api/v1/auth/me", headers=bob).json()["id"]
    r = client.patch(f"/api/v1/admin/users/{bob_id}", headers=admin, json={"plan": "pro"})
    assert r.status_code == 200 and r.json()["plan"] == "pro"
    assert r.json()["storage_quota"] == 25 * 1024**3
    assert client.get("/api/v1/chat/status", headers=bob).json()["allowed"] is True
    bad = client.patch(f"/api/v1/admin/users/{bob_id}", headers=admin, json={"plan": "gold"})
    assert bad.status_code == 422
    plans = client.get("/api/v1/plans").json()["plans"]
    assert [p["id"] for p in plans] == ["free", "pro", "business"]
    assert plans[0]["storage_gb"] == 3 and plans[0]["assistant"] is False
