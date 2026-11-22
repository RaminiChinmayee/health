import io
import json

from PIL import Image
from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from tests.conftest import CSRF, STRONG, auth, verified_login


def test_update_profile_and_health_profile_persist(client, mailbox):
    t = verified_login(client, mailbox)
    r = client.put("/api/profile", headers=auth(t), json={"full_name": "Asha  K  Rao", "phone": "+91 98765 43210"})
    assert r.json()["full_name"] == "Asha K Rao"
    assert client.put("/api/profile", headers=auth(t), json={"phone": "abc"}).status_code == 422

    hp = {
        "height_cm": 160, "weight_kg": 64, "activity_level": "moderate", "dietary_preference": "vegetarian",
        "food_allergies": ["Peanuts", "peanuts", " shellfish "], "health_conditions": ["Asthma"],
        "preferred_units": "metric",
    }
    r = client.put("/api/profile/health", headers=auth(t), json=hp).json()
    assert r["bmi"] == 25.0 and r["bmi_category"] == "overweight"
    assert r["food_allergies"] == ["Peanuts", "shellfish"]
    # persisted
    assert client.get("/api/profile/health", headers=auth(t)).json()["health_conditions"] == ["Asthma"]


def test_language_preference_persists_across_logins(client, mailbox):
    t = verified_login(client, mailbox)
    assert client.put("/api/profile/language", headers=auth(t), json={"ui_language": "hi"}).json()["chatbot_language"] == "hi"
    assert client.put("/api/profile/language", headers=auth(t), json={"ui_language": "xx"}).status_code == 422
    client.post("/api/auth/logout", headers=CSRF)
    t2 = client.post("/api/auth/login", json={"email": "asha@example.com", "password": STRONG}).json()
    assert t2["user"]["ui_language"] == "hi"


def test_change_password_requires_current_and_signs_out_other_devices(client, mailbox):
    t1 = verified_login(client, mailbox)
    from fastapi.testclient import TestClient
    from app.main import app

    other = TestClient(app)
    t2 = other.post("/api/auth/login", json={"email": "asha@example.com", "password": STRONG}).json()["access_token"]
    new = "Another-Strong-Pass-9"
    assert client.post("/api/profile/password", headers=auth(t1), json={"current_password": "nope", "new_password": new, "confirm_password": new}).status_code == 403
    r = client.post("/api/profile/password", headers=auth(t1), json={"current_password": STRONG, "new_password": new, "confirm_password": new})
    assert r.status_code == 200
    assert client.get("/api/profile", headers=auth(t1)).status_code == 200  # current device kept
    assert other.get("/api/profile", headers=auth(t2)).status_code == 401  # other device revoked


def test_change_email_requires_verification_of_new_address(client, mailbox):
    t = verified_login(client, mailbox)
    r = client.post("/api/profile/email", headers=auth(t), json={"new_email": "new@example.com", "current_password": STRONG})
    assert r.json()["email_delivery"] == "sent"
    assert client.get("/api/profile", headers=auth(t)).json()["email"] == "asha@example.com"  # unchanged yet
    token = mailbox.last_link("new@example.com", "/verify-email")
    assert client.post("/api/auth/verify-email", json={"token": token}).json()["code"] == "email_changed"
    assert client.get("/api/profile", headers=auth(t)).json()["email"] == "new@example.com"
    assert any(m["to"] == ["asha@example.com"] and "changed" in m["text"] for m in mailbox.messages)


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


def test_avatar_upload_validation_and_privacy(client, mailbox):
    t = verified_login(client, mailbox)
    bad = client.put("/api/profile/avatar", headers=auth(t), files={"file": ("x.png", b"<?php evil ?>", "image/png")})
    assert bad.status_code == 415
    ok = client.put("/api/profile/avatar", headers=auth(t), files={"file": ("me.png", _png(), "image/png")})
    assert ok.json()["has_avatar"]
    img = client.get("/api/profile/avatar", headers=auth(t))
    assert img.headers["content-type"] == "image/webp"
    assert max(Image.open(io.BytesIO(img.content)).size) <= 512
    assert client.get("/api/profile/avatar").status_code == 401


def test_users_are_isolated(client, mailbox):
    ta = verified_login(client, mailbox, email="a@example.com")
    from fastapi.testclient import TestClient
    from app.main import app

    cb = TestClient(app)
    tb = verified_login(cb, mailbox, email="b@example.com")
    client.put("/api/profile/health", headers=auth(ta), json={"health_conditions": ["Diabetes"]})
    assert cb.get("/api/profile/health", headers=auth(tb)).json()["health_conditions"] == []
    a_session = client.get("/api/profile/sessions", headers=auth(ta)).json()[0]["family_id"]
    assert cb.delete(f"/api/profile/sessions/{a_session}", headers=auth(tb)).status_code == 404
    assert client.get("/api/profile", headers=auth(ta)).status_code == 200


def test_export_and_delete_account(client, mailbox):
    t = verified_login(client, mailbox)
    client.put("/api/profile/health", headers=auth(t), json={"height_cm": 170, "weight_kg": 70})
    client.put("/api/profile/avatar", headers=auth(t), files={"file": ("me.png", _png(), "image/png")})
    data = json.loads(client.get("/api/profile/export", headers=auth(t)).content)
    assert data["account"]["email"] == "asha@example.com" and data["health_profile"]["bmi"] == 24.2

    assert client.request("DELETE", "/api/profile", headers=auth(t), json={"current_password": "wrong"}).status_code == 403
    assert client.request("DELETE", "/api/profile", headers=auth(t), json={"current_password": STRONG}).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(User)) is None
    assert client.get("/api/profile", headers=auth(t)).status_code == 401
