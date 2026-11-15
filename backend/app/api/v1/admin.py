"""Admin panel API: users & roles, usage & health stats, runtime app settings."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentUser
from app.chat.orchestrator import chat_enabled
from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.models import (
    ChatMessage,
    Dataset,
    DatasetVersion,
    Export,
    Job,
    OAuthAccount,
    PipelineStep,
    Project,
    User,
)
from app.services import app_settings, oauth, quota

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise Forbidden("Admins only", code="ADMIN_ONLY")
    return user


Admin = Annotated[User, Depends(require_admin)]


# ------------------------------------------------------------------ stats
@router.get("/stats")
def stats(_: Admin, db: DB) -> dict:
    now = datetime.now(UTC)
    week = now - timedelta(days=7)
    s = get_settings()

    def count(model, *where):
        return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)

    by_status = dict(
        db.execute(
            select(Job.status, func.count()).where(Job.created_at >= week).group_by(Job.status)
        ).all()
    )
    by_type = dict(
        db.execute(
            select(Job.job_type, func.count()).where(Job.created_at >= week).group_by(Job.job_type)
        ).all()
    )
    failed = db.execute(
        select(Job.id, Job.job_type, Job.error, Job.created_at, User.email)
        .join(User, User.id == Job.user_id)
        .where(Job.status == "failed")
        .order_by(Job.created_at.desc())
        .limit(8)
    ).all()
    tokens_in, tokens_out = db.execute(
        select(
            func.coalesce(func.sum(ChatMessage.tokens_in), 0),
            func.coalesce(func.sum(ChatMessage.tokens_out), 0),
        )
    ).one()
    tin7, tout7 = db.execute(
        select(
            func.coalesce(func.sum(ChatMessage.tokens_in), 0),
            func.coalesce(func.sum(ChatMessage.tokens_out), 0),
        ).where(ChatMessage.created_at >= week)
    ).one()

    def cost(i, o):
        return round(i / 1e6 * s.llm_price_in_per_mtok + o / 1e6 * s.llm_price_out_per_mtok, 4)

    providers = dict(
        db.execute(
            select(OAuthAccount.provider, func.count()).group_by(OAuthAccount.provider)
        ).all()
    )
    email_users = count(User, User.password_hash.is_not(None))
    signups = db.execute(
        select(func.date_trunc("day", User.created_at).label("d"), func.count())
        .where(User.created_at >= now - timedelta(days=14))
        .group_by("d")
        .order_by("d")
    ).all()
    storage = int(
        db.scalar(select(func.coalesce(func.sum(DatasetVersion.size_bytes), 0))) or 0
    ) + int(db.scalar(select(func.coalesce(func.sum(Dataset.original_size_bytes), 0))) or 0)
    return {
        "users": {
            "total": count(User),
            "active_7d": count(User, User.last_login_at >= week),
            "new_7d": count(User, User.created_at >= week),
            "admins": count(User, User.role == "admin"),
            "disabled": count(User, User.is_active.is_(False)),
            "by_method": {"email": email_users, **providers},
            "signups_14d": [{"day": d.date().isoformat(), "count": n} for d, n in signups],
        },
        "projects": {
            "total": count(Project, Project.deleted_at.is_(None)),
            "datasets": count(Dataset),
            "versions": count(DatasetVersion),
            "steps": count(PipelineStep),
            "exports": count(Export),
            "storage_bytes": storage,
        },
        "jobs_7d": {
            "by_status": by_status,
            "by_type": by_type,
            "recent_failures": [
                {"id": str(i), "type": t, "error": (e or "")[:300], "at": c.isoformat(), "user": u}
                for i, t, e, c, u in failed
            ],
        },
        "chat": {
            "messages": count(ChatMessage, ChatMessage.role == "assistant"),
            "tokens_in": int(tokens_in),
            "tokens_out": int(tokens_out),
            "cost_usd": cost(tokens_in, tokens_out),
            "tokens_in_7d": int(tin7),
            "tokens_out_7d": int(tout7),
            "cost_usd_7d": cost(tin7, tout7),
            "price_per_mtok": [s.llm_price_in_per_mtok, s.llm_price_out_per_mtok],
        },
    }


# ------------------------------------------------------------------ users
class UserRow(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    avatar_url: str | None
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    methods: list[str]
    projects: int
    storage_used: int
    storage_quota: int
    custom_quota_mb: int | None


class UserPatch(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    # MB; 0 or negative resets to the app-wide default.
    storage_quota_mb: int | None = None


def _row(db, u: User) -> UserRow:
    methods = sorted(
        {a.provider for a in db.scalars(select(OAuthAccount).where(OAuthAccount.user_id == u.id))}
    )
    if u.password_hash:
        methods.insert(0, "email")
    projects = int(
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(Project.owner_id == u.id, Project.deleted_at.is_(None))
        )
        or 0
    )
    return UserRow(
        storage_used=quota.usage_bytes(db, u.id),
        storage_quota=quota.quota_bytes(db, u),
        custom_quota_mb=u.storage_quota_mb,
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        avatar_url=u.avatar_url,
        role=u.role,
        is_active=u.is_active,
        created_at=u.created_at,
        last_login_at=u.last_login_at,
        methods=methods,
        projects=projects,
    )


@router.get("/users")
def users(
    _: Admin,
    db: DB,
    q: str = "",
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
) -> dict:
    stmt = select(User)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.display_name.ilike(like)))
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(stmt.order_by(User.created_at.desc()).offset(offset).limit(limit))
    return {"total": total, "items": [_row(db, u) for u in rows]}


@router.patch("/users/{user_id}", response_model=UserRow)
def patch_user(user_id: uuid.UUID, body: UserPatch, admin: Admin, db: DB) -> UserRow:
    u = db.get(User, user_id)
    if u is None:
        raise NotFound("User not found")
    if u.id == admin.id and (body.role == "user" or body.is_active is False):
        raise ValidationFailed(
            "You can't remove your own admin access or disable yourself", code="SELF_LOCKOUT"
        )
    if body.role is not None:
        if body.role not in ("user", "admin"):
            raise ValidationFailed("role must be user or admin")
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.storage_quota_mb is not None:
        if body.storage_quota_mb > 10_000_000:
            raise ValidationFailed("Quota is too large")
        u.storage_quota_mb = body.storage_quota_mb if body.storage_quota_mb > 0 else None
    db.commit()
    return _row(db, u)


# ------------------------------------------------------------------ settings
@router.get("/settings")
def get_app_settings(_: Admin, db: DB) -> dict:
    s = get_settings()
    return {
        "values": app_settings.all_settings(db, fresh=True),
        "schema": app_settings.SCHEMA,
        "environment": {
            "environment": s.environment,
            "chat_api_key_set": chat_enabled(),
            "oauth": {
                p: {
                    "configured": p in oauth.enabled_providers(),
                    "redirect_uri": oauth.redirect_uri(p),
                }
                for p in oauth.PROVIDERS
            },
            "public_app_url": s.public_app_url,
            "admin_emails": sorted(s.admin_email_set),
        },
    }


@router.put("/settings")
def put_app_settings(body: dict, admin: Admin, db: DB) -> dict:
    values = app_settings.update(db, body, admin.id)
    return {"values": values}
