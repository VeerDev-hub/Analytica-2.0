from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, Unauthorized
from app.core.security import hash_password, needs_rehash, verify_password
from app.models import User
from app.services import app_settings

# Verifying against a dummy hash keeps response time similar for unknown emails.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def apply_admin_bootstrap(user: User) -> None:
    """Emails listed in ADMIN_EMAILS are promoted on sign-in (first admin, recovery)."""
    if user.email.lower() in get_settings().admin_email_set:
        user.role = "admin"


def register(db: Session, email: str, password: str, display_name: str | None) -> User:
    if not app_settings.get(db, "signups_open"):
        raise Forbidden(
            "New sign-ups are closed. Ask the administrator for access.", code="SIGNUPS_CLOSED"
        )
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        display_name=(display_name or email.split("@")[0]).strip()[:120],
        last_login_at=datetime.now(UTC),
    )
    apply_admin_bootstrap(user)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("An account with this email already exists", code="EMAIL_TAKEN") from exc
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalars(select(User).where(User.email == email.strip().lower())).first()
    if user is None or user.password_hash is None:
        verify_password(password, _DUMMY_HASH)
        if user is not None:
            raise Unauthorized(
                "This account uses Google or GitHub sign-in. Use that button instead.",
                code="USE_OAUTH",
            )
        raise Unauthorized("Wrong email or password", code="BAD_CREDENTIALS")
    if not verify_password(password, user.password_hash):
        raise Unauthorized("Wrong email or password", code="BAD_CREDENTIALS")
    if not user.is_active:
        raise Forbidden("This account is disabled.", code="ACCOUNT_DISABLED")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    apply_admin_bootstrap(user)
    db.commit()
    return user
