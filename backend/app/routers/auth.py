"""Authentication endpoints: /api/auth/*"""
import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import jwt
import requests
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import emailer
from app.audit import client_ip, enforce_limit, log_event
from app.config import get_settings
from app.db import get_db
from app.deps import AuthContext, get_auth
from app.models import (
    EmailVerificationToken,
    OAuthAccount,
    PasswordResetToken,
    User,
)
from app.schemas import (
    AccessTokenOut,
    EmailIn,
    LoginIn,
    MessageOut,
    RegisterIn,
    ResetPasswordIn,
    TokenIn,
)
from app.security import (
    hash_password,
    hash_subject,
    hash_token,
    new_token,
    password_needs_rehash,
    password_problems,
    utcnow,
    verify_password,
)
from app.services.users import ensure_user_rows, get_user_by_email, normalize_email, user_out
from app.sessions import (
    REFRESH_COOKIE,
    RefreshError,
    clear_refresh_cookie,
    revoke_all_for_user,
    revoke_family,
    rotate_session,
    start_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_RESET_MSG = "If an account exists for that email, a password reset link has been sent."
OAUTH_STATE_COOKIE = "healthai_oauth"


def _err(status: int, code: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, **extra})


def _require_csrf_header(x_healthai_csrf: str | None = Header(default=None)) -> None:
    """Cookie-authenticated endpoints require a custom header. Browsers can't add it cross-site
    without a CORS preflight, which our CORS policy rejects for foreign origins."""
    if x_healthai_csrf != "1":
        raise _err(403, "csrf_header_missing")


def _token_response(user: User, access: str) -> AccessTokenOut:
    return AccessTokenOut(
        access_token=access,
        expires_in=get_settings().access_token_minutes * 60,
        user=user_out(user),
    )


def _delivery(sent: bool) -> str:
    if sent:
        return "sent"
    return "not_configured" if not emailer.smtp_configured() else "failed"


def _issue_verification(db: Session, user: User) -> bool:
    s = get_settings()
    # Invalidate previous outstanding verification links.
    db.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.purpose == "verify",
            EmailVerificationToken.used_at.is_(None),
        )
        .values(used_at=utcnow())
    )
    token = new_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(token),
            purpose="verify",
            expires_at=utcnow() + timedelta(hours=s.email_verification_hours),
        )
    )
    db.commit()
    url = f"{s.frontend_url}/verify-email?token={token}"
    return emailer.send_verification_email(user.email, user.full_name, url, s.email_verification_hours)


# ======================================================================= config
@router.get("/config")
def auth_config():
    s = get_settings()
    return {"google_enabled": s.google_enabled, "email_delivery_configured": emailer.smtp_configured()}


# ======================================================================= register
@router.post("/register", status_code=201, response_model=MessageOut)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    enforce_limit(db, "register", get_settings().register_max_per_hour_per_ip, 60, ip=ip)

    email = normalize_email(body.email)
    problems = password_problems(body.password, [email, body.full_name, str(body.date_of_birth.year)])
    if problems:
        raise _err(422, "weak_password", problems=problems)
    if get_user_by_email(db, email):
        log_event(db, request, "register", subject_hash=hash_subject(email), outcome="duplicate")
        db.commit()
        raise _err(409, "email_already_registered")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        password_changed_at=utcnow(),
        full_name=body.full_name,
        phone=body.phone,
        date_of_birth=body.date_of_birth,
        gender=body.gender,
        terms_accepted_at=utcnow(),
    )
    ensure_user_rows(db, user, body.language)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:  # concurrent registration with same email
        db.rollback()
        raise _err(409, "email_already_registered")
    log_event(db, request, "register", user_id=user.id, subject_hash=hash_subject(email), outcome="created")
    db.commit()

    sent = _issue_verification(db, user)
    return MessageOut(code="registered", email_delivery=_delivery(sent))


@router.post("/resend-verification", response_model=MessageOut)
def resend_verification(body: EmailIn, request: Request, db: Session = Depends(get_db)):
    subject = hash_subject(body.email)
    enforce_limit(db, "resend_verification", get_settings().resend_verification_max_per_hour, 60, subject_hash=subject)
    enforce_limit(db, "resend_verification", get_settings().resend_verification_max_per_hour * 20, 60, ip=client_ip(request))
    log_event(db, request, "resend_verification", subject_hash=subject)
    db.commit()
    user = get_user_by_email(db, body.email)
    if user and not user.is_verified:
        _issue_verification(db, user)
    # Same response either way: don't reveal account state.
    return MessageOut(code="verification_resent_if_applicable")


@router.post("/verify-email", response_model=MessageOut)
def verify_email(body: TokenIn, request: Request, db: Session = Depends(get_db)):
    tok = db.scalar(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token_hash == hash_token(body.token))
        .with_for_update()
    )
    if tok is None or tok.used_at is not None or tok.expires_at <= utcnow():
        raise _err(400, "invalid_or_expired_token")
    user = db.get(User, tok.user_id)
    tok.used_at = utcnow()

    if tok.purpose == "change_email":
        new_email = normalize_email(tok.new_email or "")
        if get_user_by_email(db, new_email):
            db.commit()
            raise _err(409, "email_already_registered")
        old = user.email
        user.email = new_email
        user.email_verified_at = utcnow()
        log_event(db, request, "email_changed", user_id=user.id, old_email_hash=hash_subject(old))
        db.commit()
        emailer.send_security_alert(old, user.full_name, f"Your account email was changed to {new_email}.")
        return MessageOut(code="email_changed")

    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    log_event(db, request, "email_verified", user_id=user.id)
    db.commit()
    return MessageOut(code="email_verified")


# ======================================================================= login / session
@router.post("/login", response_model=AccessTokenOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    subject = hash_subject(body.email)
    ip = client_ip(request)
    enforce_limit(db, "login_failed", s.login_max_attempts, s.login_window_minutes, subject_hash=subject)
    enforce_limit(db, "login_failed", s.login_max_attempts * 5, s.login_window_minutes, ip=ip)

    user = get_user_by_email(db, body.email)
    if not verify_password(body.password, user.password_hash if user else None):
        log_event(db, request, "login_failed", user_id=user.id if user else None, subject_hash=subject)
        db.commit()
        raise _err(401, "invalid_credentials")
    if not user.is_verified:
        raise _err(403, "email_not_verified")
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    access = start_session(db, request, response, user, body.remember_me)
    log_event(db, request, "login", user_id=user.id, method="password")
    db.commit()
    return _token_response(user, access)


@router.post("/refresh", response_model=AccessTokenOut, dependencies=[Depends(_require_csrf_header)])
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise _err(401, "no_refresh_token")
    try:
        user, access = rotate_session(db, request, response, token)
    except RefreshError as e:
        db.rollback()
        err = JSONResponse(status_code=401, content={"detail": {"code": f"refresh_{e}"}})
        clear_refresh_cookie(err)
        return err
    db.commit()
    return _token_response(user, access)


@router.post("/logout", response_model=MessageOut, dependencies=[Depends(_require_csrf_header)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Revokes the session family identified by the refresh cookie. Works even if the access
    token already expired."""
    from app.models import UserSession

    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        sess = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == hash_token(token)))
        if sess:
            revoke_family(db, sess.family_id, "logout")
            log_event(db, request, "logout", user_id=sess.user_id)
            db.commit()
    clear_refresh_cookie(response)
    return MessageOut(code="logged_out")


@router.post("/logout-all", response_model=MessageOut)
def logout_all(request: Request, response: Response, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    revoke_all_for_user(db, ctx.user.id, "logout_all")
    log_event(db, request, "logout_all", user_id=ctx.user.id)
    db.commit()
    clear_refresh_cookie(response)
    return MessageOut(code="logged_out_everywhere")


# ======================================================================= password reset
@router.post("/forgot-password", response_model=MessageOut)
def forgot_password(body: EmailIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    subject = hash_subject(body.email)
    ip = client_ip(request)
    enforce_limit(db, "password_reset_requested", s.reset_max_requests, s.reset_window_minutes, subject_hash=subject)
    enforce_limit(db, "password_reset_requested", s.reset_max_requests * 10, s.reset_window_minutes, ip=ip)

    user = get_user_by_email(db, body.email)
    log_event(db, request, "password_reset_requested", user_id=user.id if user else None, subject_hash=subject)
    db.commit()

    if user:
        # Only the newest link is valid.
        db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=utcnow())
        )
        token = new_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=utcnow() + timedelta(minutes=s.password_reset_minutes),
                request_ip=ip,
            )
        )
        db.commit()
        url = f"{s.frontend_url}/reset-password?token={token}"
        emailer.send_password_reset_email(user.email, user.full_name, url, s.password_reset_minutes)
    # Identical response whether or not the account exists.
    return MessageOut(code="reset_requested", detail=GENERIC_RESET_MSG)


@router.post("/reset-password", response_model=MessageOut)
def reset_password(body: ResetPasswordIn, request: Request, db: Session = Depends(get_db)):
    enforce_limit(db, "password_reset_failed", 20, 60, ip=client_ip(request))
    tok = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_token(body.token))
        .with_for_update()
    )
    if tok is None or tok.used_at is not None or tok.expires_at <= utcnow():
        log_event(db, request, "password_reset_failed")
        db.commit()
        raise _err(400, "invalid_or_expired_token")
    user = db.get(User, tok.user_id)
    problems = password_problems(body.password, [user.email, user.full_name])
    if problems:
        raise _err(422, "weak_password", problems=problems)

    tok.used_at = utcnow()
    user.password_hash = hash_password(body.password)
    user.password_changed_at = utcnow()
    # Following a reset link proves control of the mailbox.
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    revoke_all_for_user(db, user.id, "password_reset")
    log_event(db, request, "password_reset_completed", user_id=user.id)
    db.commit()
    emailer.send_security_alert(user.email, user.full_name, "Your password was reset.")
    return MessageOut(code="password_reset")


# ======================================================================= Google OAuth
def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _login_redirect(error: str) -> RedirectResponse:
    resp = RedirectResponse(f"{get_settings().frontend_url}/login?error={error}", status_code=302)
    resp.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth/google")
    return resp


@router.get("/google")
def google_start(remember: bool = False):
    s = get_settings()
    if not s.google_enabled:
        raise _err(503, "google_oauth_not_configured")
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    params = {
        "client_id": s.google_client_id,
        "redirect_uri": s.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    # State, nonce and PKCE verifier travel in a signed, httpOnly, short-lived cookie.
    cookie = jwt.encode(
        {"state": state, "nonce": nonce, "v": verifier, "r": remember, "exp": utcnow() + timedelta(minutes=10)},
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    resp = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), status_code=302)
    resp.set_cookie(
        OAUTH_STATE_COOKIE, cookie, httponly=True, secure=s.cookie_secure, samesite="lax",
        path="/api/auth/google", max_age=600,
    )
    return resp


def _exchange_code(code: str, verifier: str) -> dict:
    s = get_settings()
    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "redirect_uri": s.google_redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _verify_google_id_token(token: str) -> dict:
    return google_id_token.verify_oauth2_token(
        token, google_requests.Request(), get_settings().google_client_id
    )


def resolve_google_user(db: Session, request: Request, claims: dict) -> User:
    """Find, link or create the local user for verified Google claims.

    Linking rules (prevent account takeover):
      * Google must assert email_verified.
      * Existing *verified* local account with the same email → link.
      * Existing *unverified* local account → its password was never proven to belong to the
        mailbox owner (could be an attacker pre-registering the address). Link, mark verified,
        remove that password and revoke its sessions. The real owner can set a new password.
    """
    sub = claims["sub"]
    acct = db.scalar(select(OAuthAccount).where(OAuthAccount.provider == "google", OAuthAccount.provider_subject == sub))
    if acct:
        acct.last_login_at = utcnow()
        return acct.user

    if not claims.get("email_verified"):
        raise _err(400, "google_email_unverified")
    email = normalize_email(claims["email"])
    user = get_user_by_email(db, email)
    if user is None:
        user = User(
            email=email,
            email_verified_at=utcnow(),
            full_name=(claims.get("name") or email.split("@")[0])[:200],
        )
        ensure_user_rows(db, user)
        db.add(user)
        db.flush()
        log_event(db, request, "register", user_id=user.id, method="google")
    else:
        if not user.is_verified:
            user.password_hash = None
            user.email_verified_at = utcnow()
            revoke_all_for_user(db, user.id, "unverified_account_claimed_via_google")
            log_event(db, request, "unverified_password_removed_on_google_link", user_id=user.id)
        log_event(db, request, "oauth_linked", user_id=user.id, provider="google")
        emailer.send_security_alert(user.email, user.full_name, "Google sign-in was linked to your account.")

    db.add(
        OAuthAccount(
            user_id=user.id,
            provider="google",
            provider_subject=sub,
            provider_email=email,
            provider_email_verified=True,
            last_login_at=utcnow(),
        )
    )
    return user


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    s = get_settings()
    if not s.google_enabled:
        return _login_redirect("google_not_configured")
    if error:
        return _login_redirect("google_cancelled")
    raw = request.cookies.get(OAUTH_STATE_COOKIE)
    try:
        saved = jwt.decode(raw or "", s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.InvalidTokenError:
        return _login_redirect("oauth_state_invalid")
    if not code or not state or not secrets.compare_digest(state, saved["state"]):
        return _login_redirect("oauth_state_invalid")

    try:
        tokens = _exchange_code(code, saved["v"])
        claims = _verify_google_id_token(tokens["id_token"])
    except (requests.RequestException, ValueError, KeyError):
        log_event(db, request, "oauth_failed", provider="google")
        db.commit()
        return _login_redirect("google_verification_failed")
    if not secrets.compare_digest(claims.get("nonce", ""), saved["nonce"]):
        return _login_redirect("oauth_nonce_invalid")

    try:
        user = resolve_google_user(db, request, claims)
    except HTTPException as e:
        db.rollback()
        return _login_redirect(e.detail["code"])

    resp = RedirectResponse(f"{s.frontend_url}/auth/callback", status_code=302)
    resp.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth/google")
    # Sets the refresh cookie; the SPA then calls /api/auth/refresh for an access token,
    # so no token ever appears in a URL.
    start_session(db, request, resp, user, remember=bool(saved.get("r")))
    log_event(db, request, "login", user_id=user.id, method="google")
    db.commit()
    return resp
