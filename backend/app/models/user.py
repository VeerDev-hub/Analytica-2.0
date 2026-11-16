import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import created_at, uuid_pk


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    # One mailbox → one account: plus-tags and Gmail dots removed (app/core/emails.py).
    email_canonical: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    # NULL for accounts created through Google/GitHub that never set a password.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    # free | pro | business (app/services/plans.py). Decides storage and assistant access.
    plan: Mapped[str] = mapped_column(
        String(16), nullable=False, default="free", server_default="free"
    )
    # Per-user storage override in MB; NULL = the plan's limit.
    storage_quota_mb: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user", server_default="user"
    )  # user | admin
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = created_at()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OAuthAccount(Base):
    """A Google or GitHub identity linked to a user (one user can link both)."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)  # google | github
    provider_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = created_at()


class AppSetting(Base):
    """Runtime settings an admin can change without redeploying."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
