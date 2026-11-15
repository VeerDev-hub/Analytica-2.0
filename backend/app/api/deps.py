from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import Unauthorized
from app.core.security import decode_token
from app.models import User

DB = Annotated[Session, Depends(get_session)]


def get_current_user(request: Request, db: DB) -> User:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("Not signed in")
    user_id = decode_token(token, "access")
    if user_id is None:
        raise Unauthorized("Session expired", code="TOKEN_INVALID")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Not signed in")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
