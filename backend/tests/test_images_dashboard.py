"""Image upload/analysis endpoints and dashboard. The trained skin model is stubbed so tests are
deterministic; validation, storage, privacy, history, deletion and isolation run for real."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings
from app.main import app
from app.services import chat as chat_svc
from app.services import gemini, skin
from tests.conftest import auth, verified_login

CARD = {"version": "1.0.0", "classes": ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"], "concern_classes": ["akiec", "bcc", "mel"],
        "class_names": {"mel": "Melanoma", "nv": "Melanocytic naevus (mole)", "bcc": "Basal cell carcinoma", "akiec": "AK", "bkl": "BKL", "df": "DF", "vasc": "Vascular"}}


def jpeg(w=400, h=300, color=(180, 120, 100)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (w, h), color)
    img.save(buf, "JPEG", exif=Image.Exif())
    return buf.getvalue()


@pytest.fixture
def stub(monkeypatch):
    state = {"status": "ok", "reply_calls": 0}
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test")
    monkeypatch.setattr(skin, "available", lambda: True)
    monkeypatch.setattr(skin, "card", lambda: CARD)

    def fake_analyse(img, webp):
        base = {"model_key": "skin", "model_version": "1.0.0", "gate": {"checked": True, "skin_lesion_closeup": state["status"] != "rejected_not_skin"}}
        if state["status"] != "ok":
            return {**base, "status": state["status"]}
        probs = {"mel": 0.55, "nv": 0.30, "bkl": 0.05, "bcc": 0.04, "akiec": 0.03, "df": 0.02, "vasc": 0.01}
        return {**base, "status": "ok", "probabilities": probs, "predicted_class": "mel", "probability": 0.55, "ood_distance": 0.1, "safety": {"see_dermatologist": True, "prompt_review": True, "not_a_diagnosis": True}}

    def fake_reply(db, user, conv, question, analysis, lang):
        state["reply_calls"] += 1
        return f"Explanation in {lang}: please see a dermatologist.", "stub-model"

    monkeypatch.setattr(skin, "analyse", fake_analyse)
    monkeypatch.setattr(chat_svc, "image_reply", fake_reply)
    monkeypatch.setattr(chat_svc, "schedule_post_turn", lambda *a: None)
    return state


def upload(client, t, data=None, **form):
    return client.post("/api/chat/image", headers=auth(t), files={"file": ("spot.jpg", data or jpeg(), "image/jpeg")}, data={"consent": "true", **form})


def test_image_upload_analysis_and_private_serving(client, mailbox, stub):
    t = verified_login(client, mailbox)
    r = upload(client, t, question="Is this mole dangerous?", reply_language="te")
    assert r.status_code == 200, r.text
    body = r.json()
    a = body["analysis"]
    assert a["status"] == "ok" and a["predicted_class"] == "mel" and a["safety"]["prompt_review"] is True
    assert body["assistant_message"]["content"].startswith("Explanation in te")
    assert body["assistant_message"]["image_analysis"]["id"] == a["id"]
    # Stored image is re-encoded (metadata stripped) and served to the owner only.
    img = client.get(f"/api/chat/attachments/{a['attachment_id']}", headers=auth(t))
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp"
    assert "exif" not in Image.open(io.BytesIO(img.content)).info
    assert client.get(f"/api/chat/attachments/{a['attachment_id']}").status_code == 401
    other = TestClient(app)
    tb = verified_login(other, mailbox, email="b@example.com")
    assert other.get(f"/api/chat/attachments/{a['attachment_id']}", headers=auth(tb)).status_code == 404
    assert other.get("/api/history/images", headers=auth(tb)).json()["total"] == 0
    assert other.delete(f"/api/history/{a['id']}", headers=auth(tb)).status_code == 404
    # Conversation shows the image message with its attachment and the analysis.
    conv = client.get(f"/api/chat/conversations/{body['conversation_id']}", headers=auth(t)).json()
    assert conv["messages"][0]["message_type"] == "image" and conv["messages"][0]["attachment_id"] == a["attachment_id"]


def test_validation_and_consent(client, mailbox, stub):
    t = verified_login(client, mailbox)
    no_consent = client.post("/api/chat/image", headers=auth(t), files={"file": ("a.jpg", jpeg(), "image/jpeg")})
    assert no_consent.json()["detail"]["code"] == "image_consent_required"
    assert upload(client, t, data=b"%PDF-1.4 not an image" * 50).status_code == 415
    assert upload(client, t, data=jpeg(60, 60)).json()["detail"]["code"] == "image_too_small"
    big = b"\xff\xd8" + b"0" * (9 * 1024 * 1024)
    assert upload(client, t, data=big).status_code == 413


def test_rejected_images_are_not_classified(client, mailbox, stub):
    t = verified_login(client, mailbox)
    stub["status"] = "rejected_not_skin"
    a = upload(client, t).json()["analysis"]
    assert a["status"] == "rejected_not_skin" and a["predicted_class"] is None and a["probabilities"] == {}


def test_model_unavailable_is_reported(client, mailbox, monkeypatch):
    monkeypatch.setattr(skin, "available", lambda: False)
    t = verified_login(client, mailbox)
    r = upload(client, t)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "image_model_unavailable"


def test_follow_up_questions_see_labelled_image_context(client, mailbox, stub, monkeypatch):
    t = verified_login(client, mailbox)
    cid = upload(client, t).json()["conversation_id"]
    seen = {}

    def fake_stream(model, contents, system=None, **kw):
        seen["ctx"] = json.dumps(contents)
        yield "ok"
        yield gemini.GenResult(text="ok")

    monkeypatch.setattr(gemini, "stream", fake_stream)
    monkeypatch.setattr(chat_svc, "_search_with", lambda q, k=4: [])
    r = client.post("/api/chat/message", headers=auth(t), json={"content": "What should I do next?", "conversation_id": cid})
    assert r.status_code == 200
    assert "IMAGE ANALYSES IN THIS CONVERSATION" in seen["ctx"] and "NOT diagnoses" in seen["ctx"] and "Melanoma" in seen["ctx"]


def test_image_history_delete_removes_file_and_export(client, mailbox, stub):
    t = verified_login(client, mailbox)
    a = upload(client, t).json()["analysis"]
    assert client.get("/api/history/images", headers=auth(t)).json()["total"] == 1
    data = json.loads(client.get("/api/profile/export", headers=auth(t)).content)
    assert data["image_analyses"][0]["predicted_class"] == "mel"
    assert client.delete(f"/api/history/{a['id']}", headers=auth(t)).status_code == 204
    assert client.get("/api/history/images", headers=auth(t)).json()["total"] == 0
    assert client.get(f"/api/chat/attachments/{a['attachment_id']}", headers=auth(t)).status_code == 404


def test_dashboard_summary(client, mailbox, stub):
    t = verified_login(client, mailbox)
    client.put("/api/profile/health", headers=auth(t), json={"height_cm": 160, "weight_kg": 60, "activity_level": "light", "dietary_preference": "vegetarian"})
    client.post("/api/predict/symptoms", headers=auth(t), json={"symptoms": ["cough", "high_fever"]})
    upload(client, t)
    d = client.get("/api/dashboard", headers=auth(t)).json()
    assert d["profile"]["completeness"] == 100 and d["profile"]["bmi"] == 23.4
    assert d["counts"]["predictions"] == 1 and d["counts"]["image_analyses"] == 1 and d["counts"]["conversations"] == 1
    assert {a["kind"] for a in d["activity"]} >= {"prediction", "image", "chat"}
    other = TestClient(app)
    tb = verified_login(other, mailbox, email="b@example.com")
    assert other.get("/api/dashboard", headers=auth(tb)).json()["counts"] == {"predictions": 0, "conversations": 0, "diet_plans": 0, "image_analyses": 0}
