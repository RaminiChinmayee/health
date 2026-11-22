import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import decode_access_token
from app.sessions import family_is_active

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user: User
    session_family: uuid.UUID


def _unauthorized(code: str = "not_authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code},
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    if creds is None:
        raise _unauthorized()
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
        family = uuid.UUID(payload["sid"])
    except (jwt.ExpiredSignatureError,):
        raise _unauthorized("token_expired")
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise _unauthorized("invalid_token")
    if not family_is_active(db, family):
        raise _unauthorized("session_revoked")
    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("invalid_token")
    return AuthContext(user=user, session_family=family)


def get_current_user(ctx: AuthContext = Depends(get_auth)) -> User:
    return ctx.user
