"""Password hashing (Argon2id) and JWT access/refresh tokens (design D-11)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def _encode(sub: uuid.UUID, kind: str, ttl: timedelta) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(sub), "type": kind, "iat": now, "exp": now + ttl, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_access_token(user_id: uuid.UUID) -> str:
    return _encode(user_id, "access", timedelta(minutes=get_settings().access_token_minutes))


def create_refresh_token(user_id: uuid.UUID) -> str:
    return _encode(user_id, "refresh", timedelta(days=get_settings().refresh_token_days))


def decode_token(token: str, expected_type: str) -> uuid.UUID | None:
    """Return the user id if the token is valid and of the expected type, else None."""
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None
