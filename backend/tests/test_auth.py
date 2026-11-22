from datetime import timedelta

from sqlalchemy import select, update

from app.db import SessionLocal
from app.models import AccountSecurityEvent, PasswordResetToken, User, UserSession
from tests.conftest import CSRF, STRONG, auth, register, verified_login


# ------------------------------------------------------------------ registration
def test_register_validation_errors(client):
    r = register(client, email="not-an-email")
    assert r.status_code == 422 and "email" in r.json()["detail"]["fields"]

    r = register(client, password="short")
    assert r.status_code == 422

    r = client.post("/api/auth/register", json={
        "full_name": "A B", "email": "a@example.com", "password": STRONG, "confirm_password": STRONG + "x",
        "date_of_birth": "1990-01-01", "accept_terms": True,
    })
    assert r.json()["detail"]["fields"]["_form"] == "passwords_do_not_match"

    r = register(client, accept_terms=False)
    assert r.json()["detail"]["fields"]["accept_terms"] == "terms_required"

    r = register(client, date_of_birth="2999-01-01")
    assert r.json()["detail"]["fields"]["date_of_birth"] == "dob_in_future"


def test_weak_password_rejected_with_codes(client):
    r = register(client, password="password1234")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "weak_password"
    r = register(client, password="Asharao1995!")  # meets classes but guessable from name
    assert r.status_code == 422


def test_register_hashes_password_and_prevents_duplicates(client, mailbox):
    assert register(client).status_code == 201
    with SessionLocal() as db:
        u = db.scalar(select(User))
        assert u.password_hash.startswith("$argon2id$") and STRONG not in u.password_hash
        assert u.language_preference.ui_language == "te"
        assert u.email_verified_at is None
    r = register(client, email="ASHA@Example.com")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "email_already_registered"


def test_registration_sends_verification_email_via_smtp(client, mailbox):
    r = register(client)
    assert r.json()["email_delivery"] == "sent"
    assert mailbox.messages[0]["to"] == ["asha@example.com"]
    assert "Verify" in mailbox.messages[0]["subject"]


# ------------------------------------------------------------------ verification & login
def test_login_requires_verified_email(client, mailbox):
    register(client)
    r = client.post("/api/auth/login", json={"email": "asha@example.com", "password": STRONG})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "email_not_verified"

    token = mailbox.last_link("asha@example.com", "/verify-email")
    assert client.post("/api/auth/verify-email", json={"token": token}).json()["code"] == "email_verified"
    # Single use
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400

    r = client.post("/api/auth/login", json={"email": "asha@example.com", "password": STRONG})
    assert r.status_code == 200
    me = client.get("/api/profile", headers=auth(r.json()["access_token"])).json()
    assert me["email"] == "asha@example.com" and me["email_verified"] and me["age"] >= 30


def test_wrong_password_and_unknown_email_look_identical(client, mailbox):
    verified_login(client, mailbox)
    a = client.post("/api/auth/login", json={"email": "asha@example.com", "password": "Wrong-pass-999!"})
    b = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong-pass-999!"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_login_rate_limited(client, mailbox):
    verified_login(client, mailbox)
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "asha@example.com", "password": "Wrong-pass-999!"})
    r = client.post("/api/auth/login", json={"email": "asha@example.com", "password": STRONG})
    assert r.status_code == 429


def test_protected_routes_require_token(client):
    assert client.get("/api/profile").status_code == 401
    assert client.get("/api/profile", headers=auth("garbage")).json()["detail"]["code"] == "invalid_token"


# ------------------------------------------------------------------ sessions
def test_refresh_rotation_and_reuse_detection(client, mailbox):
    verified_login(client, mailbox, remember=True)
    old_cookie = client.cookies.get("healthai_refresh")
    assert old_cookie

    assert client.post("/api/auth/refresh").status_code == 403  # CSRF header required
    r = client.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 200
    new_cookie = client.cookies.get("healthai_refresh")
    assert new_cookie != old_cookie
    access = r.json()["access_token"]
    assert client.get("/api/profile", headers=auth(access)).status_code == 200

    # Within the grace window a just-rotated token still works (aborted response / two tabs).
    client.cookies.clear()
    client.cookies.set("healthai_refresh", old_cookie, path="/api/auth")
    r = client.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 200
    new_cookie = r.cookies.get("healthai_refresh")
    access = r.json()["access_token"]

    # After the window, replaying the old token is treated as theft → entire family revoked.
    with SessionLocal() as db:
        db.execute(update(UserSession).where(UserSession.revoked_reason == "rotated").values(revoked_at=UserSession.revoked_at - timedelta(seconds=60)))
        db.commit()
    client.cookies.clear()
    client.cookies.set("healthai_refresh", old_cookie, path="/api/auth")
    assert client.post("/api/auth/refresh", headers=CSRF).status_code == 401
    assert client.get("/api/profile", headers=auth(access)).json()["detail"]["code"] == "session_revoked"
    client.cookies.clear()
    client.cookies.set("healthai_refresh", new_cookie, path="/api/auth")
    assert client.post("/api/auth/refresh", headers=CSRF).status_code == 401
    with SessionLocal() as db:
        assert db.scalar(select(AccountSecurityEvent).where(AccountSecurityEvent.event_type == "refresh_token_reuse"))


def test_logout_revokes_access_immediately(client, mailbox):
    access = verified_login(client, mailbox)
    assert client.post("/api/auth/logout", headers=CSRF).status_code == 200
    assert client.get("/api/profile", headers=auth(access)).status_code == 401
    assert client.post("/api/auth/refresh", headers=CSRF).status_code == 401


# ------------------------------------------------------------------ password reset
def test_forgot_password_does_not_reveal_accounts(client, mailbox):
    verified_login(client, mailbox)
    mailbox.messages.clear()
    a = client.post("/api/auth/forgot-password", json={"email": "asha@example.com"})
    b = client.post("/api/auth/forgot-password", json={"email": "ghost@example.com"})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert [m["to"] for m in mailbox.messages] == [["asha@example.com"]]


def test_password_reset_flow(client, mailbox):
    access = verified_login(client, mailbox)
    client.post("/api/auth/forgot-password", json={"email": "asha@example.com"})
    token = mailbox.last_link("asha@example.com", "/reset-password")

    with SessionLocal() as db:
        row = db.scalar(select(PasswordResetToken))
        assert token not in row.token_hash and len(row.token_hash) == 64  # only a hash stored

    new = "Brand-New-Secret-77"
    r = client.post("/api/auth/reset-password", json={"token": token, "password": new, "confirm_password": new})
    assert r.json()["code"] == "password_reset"
    # token single-use
    assert client.post("/api/auth/reset-password", json={"token": token, "password": new, "confirm_password": new}).status_code == 400
    # existing sessions invalidated
    assert client.get("/api/profile", headers=auth(access)).status_code == 401
    assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": STRONG}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": new}).status_code == 200


def test_reset_token_expires_and_only_newest_valid(client, mailbox):
    verified_login(client, mailbox)
    client.post("/api/auth/forgot-password", json={"email": "asha@example.com"})
    first = mailbox.last_link("asha@example.com", "/reset-password")
    client.post("/api/auth/forgot-password", json={"email": "asha@example.com"})
    second = mailbox.last_link("asha@example.com", "/reset-password")
    new = "Brand-New-Secret-77"
    assert client.post("/api/auth/reset-password", json={"token": first, "password": new, "confirm_password": new}).status_code == 400
    with SessionLocal() as db:
        db.execute(update(PasswordResetToken).values(expires_at=PasswordResetToken.created_at - timedelta(minutes=1)))
        db.commit()
    assert client.post("/api/auth/reset-password", json={"token": second, "password": new, "confirm_password": new}).status_code == 400


def test_forgot_password_rate_limited(client, mailbox):
    verified_login(client, mailbox)
    for _ in range(3):
        assert client.post("/api/auth/forgot-password", json={"email": "asha@example.com"}).status_code == 200
    assert client.post("/api/auth/forgot-password", json={"email": "asha@example.com"}).status_code == 429
