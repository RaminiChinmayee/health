"""Google OAuth flow. Google's token endpoint and ID-token signature check are stubbed; everything
else (state cookie, PKCE, nonce, account resolution/linking, session issuance) runs for real."""
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import OAuthAccount, User
from app.routers import auth as auth_router
from tests.conftest import CSRF, STRONG, auth, register, verified_login


@pytest.fixture
def google(monkeypatch):
    claims = {}

    def fake_exchange(code, verifier):
        assert code == "good-code" and len(verifier) > 40
        return {"id_token": "signed.jwt"}

    def fake_verify(token):
        return dict(claims)

    monkeypatch.setattr(auth_router, "_exchange_code", fake_exchange)
    monkeypatch.setattr(auth_router, "_verify_google_id_token", fake_verify)
    return claims


def _start(client):
    r = client.get("/api/auth/google", follow_redirects=False)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["scope"] == ["openid email profile"]
    return q["state"][0], q["nonce"][0]


def _finish(client, google, state, nonce, **claims):
    google.clear()
    google.update({"sub": "g-123", "email": "asha@example.com", "email_verified": True, "name": "Asha G", "nonce": nonce, **claims})
    return client.get(f"/api/auth/google/callback?code=good-code&state={state}", follow_redirects=False)


def test_first_google_login_creates_user_and_session(client, google):
    state, nonce = _start(client)
    r = _finish(client, google, state, nonce)
    assert r.status_code == 302 and r.headers["location"].endswith("/auth/callback")
    tok = client.post("/api/auth/refresh", headers=CSRF).json()["access_token"]
    me = client.get("/api/profile", headers=auth(tok)).json()
    assert me["auth_methods"] == ["google"] and me["email_verified"] and not me["has_password"]
    assert me["needs_onboarding"] is True  # must accept terms + give DOB


def test_returning_google_user_recognized(client, google):
    s, n = _start(client)
    _finish(client, google, s, n)
    s, n = _start(client)
    _finish(client, google, s, n, email="changed@example.com")  # same sub
    with SessionLocal() as db:
        assert db.query(User).count() == 1 and db.query(OAuthAccount).count() == 1


def test_state_mismatch_rejected(client, google):
    _, nonce = _start(client)
    r = _finish(client, google, "forged-state", nonce)
    assert "error=oauth_state_invalid" in r.headers["location"]


def test_nonce_mismatch_rejected(client, google):
    state, _ = _start(client)
    r = _finish(client, google, state, "wrong-nonce")
    assert "error=oauth_nonce_invalid" in r.headers["location"]


def test_unverified_google_email_not_linked(client, google):
    state, nonce = _start(client)
    r = _finish(client, google, state, nonce, email_verified=False)
    assert "error=google_email_unverified" in r.headers["location"]


def test_links_to_verified_local_account(client, mailbox, google):
    verified_login(client, mailbox)
    state, nonce = _start(client)
    _finish(client, google, state, nonce)
    with SessionLocal() as db:
        u = db.scalar(select(User))
        assert {a.provider for a in u.oauth_accounts} == {"google"} and u.password_hash
    assert any("linked" in m["text"] for m in mailbox.messages)  # security alert sent


def test_unverified_local_account_cannot_be_used_for_takeover(client, mailbox, google):
    # Attacker pre-registers the victim's email but can't verify it.
    register(client, email="asha@example.com")
    state, nonce = _start(client)
    _finish(client, google, state, nonce)  # real owner signs in with Google
    r = client.post("/api/auth/login", json={"email": "asha@example.com", "password": STRONG})
    assert r.status_code == 401  # attacker's password no longer works
    with SessionLocal() as db:
        assert db.scalar(select(User)).password_hash is None


def test_google_disabled_returns_503(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "google_client_id", "")
    assert client.get("/api/auth/google", follow_redirects=False).status_code == 503
