from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Unauthorized, ValidationFailed
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import OAuthAccount, Project, User
from app.schemas.common import LoginIn, RegisterIn, TokenOut, UserOut
from app.services import app_settings, oauth, quota
from app.services import auth as auth_service
from app.storage.backend import get_storage

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "analytica_refresh"
STATE_COOKIE = "analytica_oauth_state"
COOKIE_PATH = "/api/v1/auth"


def _set_refresh(response: Response, user: User) -> None:
    s = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        create_refresh_token(user.id),
        max_age=s.refresh_token_days * 86400,
        httponly=True,
        secure=not s.is_local,
        samesite="lax",
        path=COOKIE_PATH,
    )


def user_out(db, user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.providers = sorted(
        {
            a.provider
            for a in db.scalars(select(OAuthAccount).where(OAuthAccount.user_id == user.id))
        }
    )
    out.has_password = user.password_hash is not None
    return out


def _issue(db, response: Response, user: User) -> TokenOut:
    _set_refresh(response, user)
    s = get_settings()
    return TokenOut(
        access_token=create_access_token(user.id),
        expires_in=s.access_token_minutes * 60,
        user=user_out(db, user),
    )


@router.get("/providers")
def providers(db: DB) -> dict:
    """What the sign-in page can offer. Public."""
    return {
        "providers": oauth.enabled_providers(),
        "signups_open": app_settings.get(db, "signups_open"),
    }


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, response: Response, db: DB) -> TokenOut:
    user = auth_service.register(db, body.email, body.password, body.display_name)
    return _issue(db, response, user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, response: Response, db: DB) -> TokenOut:
    user = auth_service.authenticate(db, body.email, body.password)
    return _issue(db, response, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, db: DB) -> TokenOut:
    token = request.cookies.get(REFRESH_COOKIE)
    user_id = decode_token(token, "refresh") if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
        raise Unauthorized("Session expired", code="REFRESH_INVALID")
    return _issue(db, response, user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser, db: DB) -> UserOut:
    return user_out(db, user)


# ------------------------------------------------------------------ OAuth
@router.get("/oauth/{provider}/start", include_in_schema=False)
def oauth_start(provider: str) -> RedirectResponse:
    url, state = oauth.start(provider)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=not get_settings().is_local,
        samesite="lax",
        path=COOKIE_PATH,
    )
    return resp


@router.get("/oauth/{provider}/callback", include_in_schema=False)
def oauth_callback(
    provider: str,
    request: Request,
    db: DB,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    app_url = get_settings().public_app_url.rstrip("/")
    try:
        if error or not code:
            raise oauth.OAuthError("Sign-in was cancelled.")
        oauth.check_state(provider, request.cookies.get(STATE_COOKIE), state)
        user = oauth.complete(db, provider, code)
    except AppError as e:
        resp = RedirectResponse(f"{app_url}/login?error={e.code}", status_code=302)
        resp.delete_cookie(STATE_COOKIE, path=COOKIE_PATH)
        return resp
    resp = RedirectResponse(f"{app_url}/auth/callback", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path=COOKIE_PATH)
    _set_refresh(resp, user)
    return resp


# ------------------------------------------------------------------ account management
class ProfilePatch(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class PasswordIn(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=8, max_length=128)


class DeleteAccountIn(BaseModel):
    confirm_email: str
    password: str | None = None


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfilePatch, user: CurrentUser, db: DB) -> UserOut:
    user.display_name = body.display_name.strip()
    db.commit()
    return user_out(db, user)


@router.post("/me/password", status_code=204)
def change_password(body: PasswordIn, user: CurrentUser, db: DB) -> Response:
    """Change the password, or set one for a Google/GitHub-only account."""
    if user.password_hash is not None and not verify_password(
        body.current_password or "", user.password_hash
    ):
        raise Unauthorized("Current password is wrong", code="BAD_CREDENTIALS")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return Response(status_code=204)


@router.get("/me/storage")
def my_storage(user: CurrentUser, db: DB) -> dict:
    by_project = quota.usage_by_project(db, user.id)
    names = (
        dict(
            db.execute(
                select(Project.id, Project.name).where(Project.id.in_(list(by_project)))
            ).all()
        )
        if by_project
        else {}
    )
    return {
        **quota.summary(db, user),
        "projects": sorted(
            (
                {"id": str(pid), "name": names.get(pid, "?"), "bytes": n}
                for pid, n in by_project.items()
            ),
            key=lambda r: r["bytes"],
            reverse=True,
        ),
    }


@router.delete("/me", status_code=204)
def delete_me(body: DeleteAccountIn, response: Response, user: CurrentUser, db: DB) -> Response:
    """Permanently delete the account, its projects, files and chat history."""
    if body.confirm_email.strip().lower() != user.email.lower():
        raise ValidationFailed(
            "Type your email address exactly to confirm", code="CONFIRM_MISMATCH"
        )
    if user.password_hash is not None and not verify_password(
        body.password or "", user.password_hash
    ):
        raise Unauthorized("Password is wrong", code="BAD_CREDENTIALS")
    if user.role == "admin":
        admins = (
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "admin", User.is_active.is_(True))
            )
            or 0
        )
        if admins <= 1:
            raise Conflict(
                "You are the only admin. Make someone else admin first.", code="LAST_ADMIN"
            )
    get_storage().delete_prefix(f"users/{user.id}/")
    db.delete(user)  # cascades to projects, datasets, versions, jobs, chats, recipes
    db.commit()
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    response.status_code = 204
    return response
