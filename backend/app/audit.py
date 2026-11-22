"""Security event logging and DB-backed rate limiting (works across multiple workers)."""
import ipaddress
import uuid
from datetime import timedelta

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AccountSecurityEvent
from app.security import utcnow


def client_ip(request: Request) -> str | None:
    # Behind a reverse proxy, configure uvicorn --proxy-headers so request.client is correct.
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:  # unix sockets, test clients, etc.
        return None


def log_event(
    db: Session,
    request: Request | None,
    event_type: str,
    user_id: uuid.UUID | None = None,
    subject_hash: str | None = None,
    **details,
) -> None:
    db.add(
        AccountSecurityEvent(
            user_id=user_id,
            event_type=event_type,
            subject_hash=subject_hash,
            ip_address=client_ip(request) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            details=details,
        )
    )


def count_recent(
    db: Session,
    event_type: str,
    minutes: int,
    subject_hash: str | None = None,
    ip: str | None = None,
) -> int:
    q = select(func.count()).select_from(AccountSecurityEvent).where(
        AccountSecurityEvent.event_type == event_type,
        AccountSecurityEvent.created_at >= utcnow() - timedelta(minutes=minutes),
    )
    if subject_hash is not None:
        q = q.where(AccountSecurityEvent.subject_hash == subject_hash)
    if ip is not None:
        q = q.where(AccountSecurityEvent.ip_address == ip)
    return db.scalar(q) or 0


def enforce_limit(
    db: Session,
    event_type: str,
    max_count: int,
    minutes: int,
    subject_hash: str | None = None,
    ip: str | None = None,
) -> None:
    """Limit by subject (email hash) or by IP. Exactly one should be given; if the value is
    unknown (None) the check is skipped rather than turning into a global limit."""
    if subject_hash is None and ip is None:
        return
    if count_recent(db, event_type, minutes, subject_hash=subject_hash, ip=ip) >= max_count:
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "retry_after_minutes": minutes},
            headers={"Retry-After": str(minutes * 60)},
        )
