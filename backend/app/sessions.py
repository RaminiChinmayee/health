"""Refresh-token sessions with rotation and reuse detection.

* Each login starts a session *family*. Each refresh issues a new token in that family and
  revokes the old one.
* Presenting a token that was already rotated means it leaked: the whole family is revoked.
* Access tokens carry the family id; requests are rejected once the family is revoked, so
  logout and password changes take effect immediately.
"""
import uuid
from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import client_ip, log_event
from app.config import get_settings
from app.models import User, UserSession
from app.security import create_access_token, hash_token, new_token, utcnow

REFRESH_COOKIE = "healthai_refresh"
REFRESH_COOKIE_PATH = "/api/auth"
ROTATION_GRACE_SECONDS = 30


class RefreshError(Exception):
    pass


def _expiry(remember: bool):
    s = get_settings()
    if remember:
        return utcnow() + timedelta(days=s.refresh_token_days_remember)
    return utcnow() + timedelta(hours=s.refresh_token_hours_session)


def _set_cookie(response: Response, token: str, remember: bool) -> None:
    s = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        # Without "remember me" the cookie dies with the browser session.
        max_age=s.refresh_token_days_remember * 86400 if remember else None,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def start_session(
    db: Session, request: Request, response: Response, user: User, remember: bool
) -> str:
    """Create a session family, set the refresh cookie, return an access token."""
    token = new_token()
    sess = UserSession(
        user_id=user.id,
        family_id=uuid.uuid4(),
        refresh_token_hash=hash_token(token),
        remember=remember,
        expires_at=_expiry(remember),
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    db.add(sess)
    db.flush()
    _set_cookie(response, token, remember)
    return create_access_token(user.id, sess.family_id)


def rotate_session(
    db: Session, request: Request, response: Response, token: str
) -> tuple[User, str]:
    sess = db.scalar(
        select(UserSession).where(UserSession.refresh_token_hash == hash_token(token)).with_for_update()
    )
    if sess is None:
        raise RefreshError("unknown")
    now = utcnow()
    # Grace window: a token rotated seconds ago may legitimately come back (a page reload
    # aborted the response that carried the new cookie, or two tabs refreshed at once).
    # Within the window we issue another successor instead of treating it as theft.
    in_grace = (
        sess.revoked_reason == "rotated"
        and sess.revoked_at is not None
        and (now - sess.revoked_at).total_seconds() <= ROTATION_GRACE_SECONDS
    )
    if sess.revoked_at is not None and not in_grace:
        if sess.revoked_reason == "rotated":
            # A rotated token came back: assume theft and kill the family.
            revoke_family(db, sess.family_id, "reuse_detected")
            log_event(db, request, "refresh_token_reuse", user_id=sess.user_id)
            db.commit()
        raise RefreshError("revoked")
    if sess.expires_at <= now:
        raise RefreshError("expired")

    new = new_token()
    successor = UserSession(
        user_id=sess.user_id,
        family_id=sess.family_id,
        refresh_token_hash=hash_token(new),
        remember=sess.remember,
        # Sliding expiry for remembered sessions; fixed lifetime otherwise.
        expires_at=_expiry(True) if sess.remember else sess.expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
        last_used_at=now,
    )
    db.add(successor)
    db.flush()
    if not in_grace:
        sess.revoked_at = now
        sess.revoked_reason = "rotated"
        sess.replaced_by_id = successor.id
    user = db.get(User, sess.user_id)
    _set_cookie(response, new, sess.remember)
    return user, create_access_token(user.id, sess.family_id)


def revoke_family(db: Session, family_id: uuid.UUID, reason: str) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.family_id == family_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoked_reason=reason)
    )


def revoke_all_for_user(
    db: Session, user_id: uuid.UUID, reason: str, except_family: uuid.UUID | None = None
) -> None:
    q = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_family is not None:
        q = q.where(UserSession.family_id != except_family)
    db.execute(q.values(revoked_at=utcnow(), revoked_reason=reason))


def family_is_active(db: Session, family_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(UserSession.id).where(
                UserSession.family_id == family_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > utcnow(),
            ).limit(1)
        )
        is not None
    )
