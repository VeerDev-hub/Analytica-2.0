"""Sign in with Google or GitHub (OAuth 2.0 authorization-code flow).

1. /auth/oauth/{provider}/start  -> sets a short-lived signed `state` cookie and redirects to
   the provider's consent screen.
2. /auth/oauth/{provider}/callback -> checks state, exchanges the code server-side, reads the
   *verified* email, then links to an existing account with that email or creates one.
3. The API sets the normal refresh cookie and redirects to the SPA (/auth/callback), which
   calls /auth/refresh to get an access token. No token ever appears in a URL.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, Forbidden, NotFound
from app.models import OAuthAccount, User


@dataclass(frozen=True)
class Provider:
    name: str
    authorize_url: str
    token_url: str
    scope: str


PROVIDERS = {
    "google": Provider(
        "google",
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "openid email profile",
    ),
    "github": Provider(
        "github",
        "https://github.com/login/oauth/authorize",
        "https://github.com/login/oauth/access_token",
        "read:user user:email",
    ),
}


class OAuthError(AppError):
    status_code = 400
    code = "OAUTH_FAILED"


def credentials(name: str) -> tuple[str, str] | None:
    s = get_settings()
    cid, secret = {
        "google": (s.google_client_id, s.google_client_secret),
        "github": (s.github_client_id, s.github_client_secret),
    }.get(name, (None, None))
    return (cid, secret) if cid and secret else None


def enabled_providers() -> list[str]:
    return [p for p in PROVIDERS if credentials(p)]


def redirect_uri(name: str) -> str:
    return f"{get_settings().public_app_url.rstrip('/')}/api/v1/auth/oauth/{name}/callback"


def _provider(name: str) -> tuple[Provider, str, str]:
    if name not in PROVIDERS:
        raise NotFound("Unknown sign-in provider")
    creds = credentials(name)
    if creds is None:
        raise AppError(
            f"{name.title()} sign-in is not configured on this server",
            code="OAUTH_NOT_CONFIGURED",
            status_code=501,
        )
    return PROVIDERS[name], creds[0], creds[1]


def start(name: str) -> tuple[str, str]:
    """Return (provider URL to redirect to, signed state for the cookie)."""
    p, cid, _ = _provider(name)
    nonce = secrets.token_urlsafe(24)
    s = get_settings()
    state = jwt.encode(
        {"n": nonce, "p": name, "exp": datetime.now(UTC) + timedelta(minutes=10)},
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri(name),
        "response_type": "code",
        "scope": p.scope,
        "state": nonce,
    }
    if name == "google":
        params["prompt"] = "select_account"
    return f"{p.authorize_url}?{urlencode(params)}", state


def check_state(name: str, cookie: str | None, returned: str | None) -> None:
    s = get_settings()
    try:
        data = jwt.decode(cookie or "", s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise OAuthError("Sign-in expired. Please try again.") from e
    if data.get("p") != name or not returned or not secrets.compare_digest(data["n"], returned):
        raise OAuthError("Sign-in could not be verified. Please try again.")


def _profile(name: str, code: str) -> tuple[str, str, str, str | None]:
    """Exchange the code; return (provider_user_id, verified email, display name, avatar)."""
    p, cid, secret = _provider(name)
    with httpx.Client(timeout=10) as http:
        tok = http.post(
            p.token_url,
            headers={"Accept": "application/json"},
            data={
                "client_id": cid,
                "client_secret": secret,
                "code": code,
                "redirect_uri": redirect_uri(name),
                "grant_type": "authorization_code",
            },
        )
        access = tok.json().get("access_token") if tok.status_code == 200 else None
        if not access:
            raise OAuthError(f"{name.title()} did not accept the sign-in. Please try again.")
        auth = {"Authorization": f"Bearer {access}", "Accept": "application/json"}
        if name == "google":
            info = http.get("https://openidconnect.googleapis.com/v1/userinfo", headers=auth).json()
            if not info.get("email_verified"):
                raise OAuthError("Your Google email address is not verified.")
            return (
                str(info["sub"]),
                info["email"],
                info.get("name") or info["email"],
                info.get("picture"),
            )
        user = http.get("https://api.github.com/user", headers=auth).json()
        emails = http.get("https://api.github.com/user/emails", headers=auth).json()
        primary = next(
            (
                e["email"]
                for e in emails
                if isinstance(e, dict) and e.get("primary") and e.get("verified")
            ),
            None,
        )
        if not primary:
            raise OAuthError("Your GitHub account has no verified primary email.")
        return (
            str(user["id"]),
            primary,
            user.get("name") or user.get("login") or primary,
            user.get("avatar_url"),
        )


def complete(db: Session, name: str, code: str) -> User:
    from app.services import app_settings
    from app.services.auth import apply_admin_bootstrap

    pid, email, display, avatar = _profile(name, code)
    email = email.strip().lower()
    link = db.scalars(
        select(OAuthAccount).where(
            OAuthAccount.provider == name, OAuthAccount.provider_user_id == pid
        )
    ).first()
    user = db.get(User, link.user_id) if link else None
    if user is None:
        # Same verified mailbox as an existing account: link instead of duplicating.
        from app.core import emails

        canon = emails.canonical(email)
        user = db.scalars(
            select(User).where((User.email == email) | (User.email_canonical == canon))
        ).first()
    if user is None:
        if not app_settings.get(db, "signups_open"):
            raise Forbidden(
                "New sign-ups are closed. Ask the administrator for access.", code="SIGNUPS_CLOSED"
            )
        # Google/GitHub verified this address, so skip the DNS layer; still refuse
        # temp-mail domains (GitHub allows them as account emails).
        emails.check_allowed(
            email, app_settings.get(db, "blocked_email_domains") or "", check_dns=False
        )
        user = User(
            email=email,
            email_canonical=canon,
            password_hash=None,
            display_name=display[:120],
            avatar_url=avatar,
        )
        db.add(user)
        db.flush()
    if not user.is_active:
        raise Forbidden("This account is disabled.", code="ACCOUNT_DISABLED")
    if link is None:
        db.add(OAuthAccount(user_id=user.id, provider=name, provider_user_id=pid, email=email))
    if avatar and not user.avatar_url:
        user.avatar_url = avatar
    user.last_login_at = datetime.now(UTC)
    apply_admin_bootstrap(user)
    db.commit()
    return user
