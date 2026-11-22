"""Profile & account management: /api/profile/*  (all endpoints require authentication and
operate only on the authenticated user — no user id is ever taken from the request)."""
import io
import json
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import emailer
from app.audit import enforce_limit, log_event
from app.config import get_settings
from app.db import get_db
from app.deps import AuthContext, get_auth, get_current_user
from app.models import (
    AccountSecurityEvent,
    EmailVerificationToken,
    User,
    UserSession,
)
from app.schemas import (
    ChangeEmailIn,
    ChangePasswordIn,
    DeleteAccountIn,
    HealthProfileIn,
    HealthProfileOut,
    LanguageIn,
    MessageOut,
    NotificationPrefsIn,
    ProfileUpdateIn,
    SessionOut,
    UserOut,
)
from app.security import (
    hash_password,
    hash_subject,
    hash_token,
    new_token,
    password_problems,
    utcnow,
    verify_password,
)
from app.services.users import age_from_dob, bmi_category, ensure_user_rows, get_user_by_email, normalize_email, user_out
from app.sessions import clear_refresh_cookie, revoke_all_for_user, revoke_family

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _err(status: int, code: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, **extra})


def _require_reauth(user: User, current_password: str | None) -> None:
    """Sensitive actions on password accounts require the current password."""
    if user.password_hash and not verify_password(current_password or "", user.password_hash):
        raise _err(403, "current_password_incorrect")


# ------------------------------------------------------------------ basic profile
@router.get("", response_model=UserOut)
def get_profile(user: User = Depends(get_current_user)):
    return user_out(user)


@router.put("", response_model=UserOut)
def update_profile(body: ProfileUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if data.pop("accept_terms", None):
        user.terms_accepted_at = user.terms_accepted_at or utcnow()
    if "full_name" in data and data["full_name"]:
        data["full_name"] = " ".join(data["full_name"].split())
    for k, v in data.items():
        if k == "full_name" and not v:
            continue
        setattr(user, k, v)
    db.commit()
    return user_out(user)


# ------------------------------------------------------------------ health profile
def _health_out(user: User) -> HealthProfileOut:
    hp = user.health_profile
    return HealthProfileOut(
        height_cm=hp.height_cm,
        weight_kg=hp.weight_kg,
        activity_level=hp.activity_level,
        dietary_preference=hp.dietary_preference,
        food_allergies=hp.food_allergies or [],
        health_conditions=hp.health_conditions or [],
        emergency_contact_name=hp.emergency_contact_name,
        emergency_contact_phone=hp.emergency_contact_phone,
        preferred_units=hp.preferred_units,
        age=age_from_dob(user.date_of_birth),
        bmi=hp.bmi,
        bmi_category=bmi_category(hp.bmi),
        updated_at=hp.updated_at,
    )


@router.get("/health", response_model=HealthProfileOut)
def get_health(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.health_profile is None:
        ensure_user_rows(db, user)
        db.commit()
    return _health_out(user)


@router.put("/health", response_model=HealthProfileOut)
def put_health(body: HealthProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_user_rows(db, user)
    for k, v in body.model_dump().items():
        setattr(user.health_profile, k, v)
    db.commit()
    db.refresh(user.health_profile)
    return _health_out(user)


# ------------------------------------------------------------------ language & notifications
@router.put("/language", response_model=UserOut)
def put_language(body: LanguageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_user_rows(db, user)
    user.language_preference.ui_language = body.ui_language
    user.language_preference.chatbot_language = body.chatbot_language or body.ui_language
    db.commit()
    return user_out(user)


@router.get("/notifications", response_model=NotificationPrefsIn)
def get_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_user_rows(db, user)
    db.commit()
    n = user.notification_preference
    return NotificationPrefsIn(
        email_security_alerts=n.email_security_alerts,
        email_health_reminders=n.email_health_reminders,
        email_product_updates=n.email_product_updates,
    )


@router.put("/notifications", response_model=NotificationPrefsIn)
def put_notifications(body: NotificationPrefsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_user_rows(db, user)
    for k, v in body.model_dump().items():
        setattr(user.notification_preference, k, v)
    db.commit()
    return body


# ------------------------------------------------------------------ password & email
@router.post("/password", response_model=MessageOut)
def change_password(
    body: ChangePasswordIn,
    request: Request,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    user = ctx.user
    enforce_limit(db, "password_change_failed", 5, 15, subject_hash=hash_subject(user.email))
    if user.password_hash and not verify_password(body.current_password or "", user.password_hash):
        log_event(db, request, "password_change_failed", user_id=user.id, subject_hash=hash_subject(user.email))
        db.commit()
        raise _err(403, "current_password_incorrect")
    problems = password_problems(body.new_password, [user.email, user.full_name])
    if problems:
        raise _err(422, "weak_password", problems=problems)
    first_password = user.password_hash is None
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()
    # Sign out every other device; keep the current session.
    revoke_all_for_user(db, user.id, "password_changed", except_family=ctx.session_family)
    log_event(db, request, "password_set" if first_password else "password_changed", user_id=user.id)
    db.commit()
    emailer.send_security_alert(user.email, user.full_name, "Your password was changed.")
    return MessageOut(code="password_changed")


@router.post("/email", response_model=MessageOut)
def change_email(body: ChangeEmailIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_reauth(user, body.current_password)
    enforce_limit(db, "email_change_requested", 5, 60, subject_hash=hash_subject(user.email))
    new_email = normalize_email(body.new_email)
    if new_email == user.email:
        raise _err(400, "email_unchanged")
    if get_user_by_email(db, new_email):
        raise _err(409, "email_already_registered")
    s = get_settings()
    token = new_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(token),
            purpose="change_email",
            new_email=new_email,
            expires_at=utcnow() + timedelta(hours=s.email_verification_hours),
        )
    )
    log_event(db, request, "email_change_requested", user_id=user.id, subject_hash=hash_subject(user.email))
    db.commit()
    url = f"{s.frontend_url}/verify-email?token={token}"
    sent = emailer.send_email_change_email(new_email, user.full_name, url, s.email_verification_hours)
    delivery = "sent" if sent else ("not_configured" if not emailer.smtp_configured() else "failed")
    return MessageOut(code="email_change_pending", email_delivery=delivery)


# ------------------------------------------------------------------ avatar
def _avatar_abs(rel: str) -> Path:
    root = get_settings().storage_dir.resolve()
    p = (root / rel).resolve()
    if root not in p.parents:
        raise _err(400, "invalid_path")
    return p


@router.put("/avatar", response_model=UserOut)
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_settings()
    data = await file.read(s.max_avatar_bytes + 1)
    if len(data) > s.max_avatar_bytes:
        raise _err(413, "file_too_large", max_bytes=s.max_avatar_bytes)
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in {"JPEG", "PNG", "WEBP"}:
            raise _err(415, "unsupported_image_type")
        img.verify()
        img = Image.open(io.BytesIO(data))  # verify() invalidates the image
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise _err(415, "unsupported_image_type")
    # Re-encode: strips EXIF/GPS metadata and any embedded payload.
    img.thumbnail((512, 512))
    rel = f"avatars/{user.id}/{uuid.uuid4().hex}.webp"
    dest = _avatar_abs(rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "WEBP", quality=85)
    old = user.avatar_path
    user.avatar_path = rel
    db.commit()
    if old:
        _avatar_abs(old).unlink(missing_ok=True)
    return user_out(user)


@router.get("/avatar")
def get_avatar(user: User = Depends(get_current_user)):
    if not user.avatar_path:
        raise _err(404, "no_avatar")
    path = _avatar_abs(user.avatar_path)
    if not path.exists():
        raise _err(404, "no_avatar")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=300"})


@router.delete("/avatar", response_model=UserOut)
def delete_avatar(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.avatar_path:
        _avatar_abs(user.avatar_path).unlink(missing_ok=True)
        user.avatar_path = None
        db.commit()
    return user_out(user)


# ------------------------------------------------------------------ sessions & security log
@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == ctx.user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > utcnow())
        .order_by(UserSession.created_at.desc())
    ).all()
    return [
        SessionOut(
            family_id=r.family_id,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            user_agent=r.user_agent,
            ip_address=str(r.ip_address) if r.ip_address else None,
            current=r.family_id == ctx.session_family,
        )
        for r in rows
    ]


@router.delete("/sessions/{family_id}", response_model=MessageOut)
def revoke_session(family_id: uuid.UUID, request: Request, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    owned = db.scalar(select(UserSession.id).where(UserSession.family_id == family_id, UserSession.user_id == ctx.user.id).limit(1))
    if not owned:
        raise _err(404, "not_found")
    revoke_family(db, family_id, "revoked_by_user")
    log_event(db, request, "session_revoked", user_id=ctx.user.id)
    db.commit()
    return MessageOut(code="session_revoked")


@router.get("/security-events")
def security_events(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(AccountSecurityEvent)
        .where(AccountSecurityEvent.user_id == user.id)
        .order_by(AccountSecurityEvent.created_at.desc())
        .limit(50)
    ).all()
    return [
        {"event_type": r.event_type, "created_at": r.created_at, "ip_address": str(r.ip_address) if r.ip_address else None, "user_agent": r.user_agent}
        for r in rows
    ]


# ------------------------------------------------------------------ export & delete
@router.get("/export")
def export_data(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Download everything stored about the user as JSON. Later phases register more
    sections through app.services.export."""
    from app.services.export import collect_user_export

    payload = collect_user_export(db, user)
    log_event(db, request, "data_exported", user_id=user.id)
    db.commit()
    body = json.dumps(payload, default=str, indent=2, ensure_ascii=False)
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="healthassist-my-data.json"'},
    )


@router.delete("", response_model=MessageOut)
def delete_account(body: DeleteAccountIn, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.password_hash:
        _require_reauth(user, body.current_password)
    elif normalize_email(body.confirm_email or "") != user.email:
        raise _err(403, "confirmation_email_mismatch")

    from app.services.export import delete_user_files

    email, name = user.email, user.full_name
    delete_user_files(user)
    # FK cascades remove sessions, tokens, profiles, history and memory rows.
    # Security events are deleted too (they reference the user with ON DELETE CASCADE).
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    clear_refresh_cookie(response)
    emailer.send_security_alert(email, name, "Your HealthAssist AI account and its data were deleted.")
    return MessageOut(code="account_deleted")
