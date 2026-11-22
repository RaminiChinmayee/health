"""Chatbot tests. Gemini is stubbed (deterministic); everything else — persistence, memory,
summaries, isolation, SSE, validation — runs for real against PostgreSQL."""
import io
import json
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import ChatMessage, ConversationSummary, UserChatMemory
from app.services import chat as chat_svc
from app.services import embeddings, gemini, knowledge
from tests.conftest import auth, verified_login

SOURCES = [{"id": "1-0", "title": "Dengue", "url": "https://medlineplus.gov/dengue.html", "text": "Dengue is spread by mosquitoes...", "score": 0.8}]


@pytest.fixture
def llm(monkeypatch):
    """Stub Gemini. Records the contents/system of each chat call; post-turn work runs inline."""
    calls = {"stream": [], "generate": [], "reply": "Rest and drink fluids [1]. See a doctor if it gets worse [7].", "post": {}}
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")

    def fake_stream(model, contents, system=None, **kw):
        calls["stream"].append({"contents": contents, "system": system})
        if isinstance(calls["reply"], Exception):
            raise calls["reply"]
        for part in (calls["reply"][:10], calls["reply"][10:]):
            yield part
        yield gemini.GenResult(text=calls["reply"], usage={"totalTokenCount": 42})

    def fake_generate(model, contents, system=None, **kw):
        calls["generate"].append(contents[0]["parts"][0]["text"])
        return gemini.GenResult(text=json.dumps(calls["post"]))

    monkeypatch.setattr(gemini, "stream", fake_stream)
    monkeypatch.setattr(gemini, "generate", fake_generate)
    unit = lambda texts: np.ones((len(texts), 384), dtype=np.float32) / np.sqrt(384)  # noqa: E731
    monkeypatch.setattr(embeddings, "embed_queries", unit)
    monkeypatch.setattr(embeddings, "embed_passages", unit)
    monkeypatch.setattr(knowledge, "kb_available", lambda: True)
    monkeypatch.setattr(chat_svc, "_search_with", lambda q, k=4: SOURCES)
    monkeypatch.setattr(chat_svc, "schedule_post_turn", lambda u, c, m: chat_svc.post_turn(u, c, m))
    return calls


def send(client, token, content, **kw):
    r = client.post("/api/chat/message", headers=auth(token), json={"content": content, **kw})
    assert r.status_code == 200, r.text
    events = {}
    for block in r.text.strip().split("\n\n"):
        ev, data = block.split("\n", 1)
        events.setdefault(ev.removeprefix("event: "), []).append(json.loads(data.removeprefix("data: ")))
    return events


# ------------------------------------------------------------------ language detection
@pytest.mark.parametrize("text,lang", [
    ("I have a headache and fever", "en"), ("मुझे सिरदर्द और बुखार है", "hi"), ("मला डोकेदुखी आणि ताप आहे", "mr"),
    ("నాకు తలనొప్పి మరియు జ్వరం ఉంది", "te"), ("எனக்கு தலைவலி மற்றும் காய்ச்சல் உள்ளது", "ta"), ("আমার মাথাব্যথা এবং জ্বর", "bn"),
    ("મને માથાનો દુખાવો અને તાવ છે", "gu"), ("مجھے سر درد اور بخار ہے", "ur"), ("ನನಗೆ ತಲೆನೋವು ಮತ್ತು ಜ್ವರ ಇದೆ", "kn"),
    ("ମୋର ମୁଣ୍ଡବିନ୍ଧା ଏବଂ ଜ୍ୱର ଅଛି", "or"), ("എനിക്ക് തലവേദനയും പനിയും ഉണ്ട്", "ml"), ("mujhe kal se bukhar hai aur sir dard", "hi"),
])
def test_language_detection(text, lang):
    assert knowledge.detect_language(text)[0] == lang


# ------------------------------------------------------------------ messaging
def test_chat_streams_saves_and_cites(client, mailbox, llm):
    t = verified_login(client, mailbox)
    ev = send(client, t, "I have a fever since yesterday", reply_language="te")
    meta, done = ev["meta"][0], ev["done"][0]
    assert meta["detected_language"] == "en" and meta["reply_language"] == "te"
    assert "".join(d["text"] for d in ev["delta"]) == llm["reply"]
    msg = done["assistant_message"]
    # [1] maps to a real retrieved source; the invalid [7] is removed.
    assert msg["citations"] == [{"n": 1, "title": "Dengue", "url": "https://medlineplus.gov/dengue.html", "source": "MedlinePlus"}]
    assert "[7]" not in msg["content"]
    assert "Telugu" in llm["stream"][0]["system"] and "MedlinePlus" in llm["stream"][0]["contents"][0]["parts"][0]["text"]
    conv = client.get(f"/api/chat/conversations/{meta['conversation_id']}", headers=auth(t)).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]


def test_short_term_memory_follow_up(client, mailbox, llm):
    t = verified_login(client, mailbox)
    cid = send(client, t, "I have a headache and fever.")["meta"][0]["conversation_id"]
    send(client, t, "Since yesterday.", conversation_id=cid)
    second = llm["stream"][1]["contents"]
    texts = [p["parts"][0]["text"] for p in second]
    # The earlier user turn and assistant reply are included, so "since yesterday" has context.
    assert "I have a headache and fever." in texts and texts[-1] == "Since yesterday."


def test_title_generated_and_conversation_management(client, mailbox, llm):
    t = verified_login(client, mailbox)
    llm["post"] = {"title": "Fever and headache"}
    cid = send(client, t, "fever and headache")["meta"][0]["conversation_id"]
    lst = client.get("/api/history/chats", headers=auth(t)).json()
    assert lst["items"][0]["title"] == "Fever and headache"
    assert client.get("/api/history/chats?q=headache", headers=auth(t)).json()["total"] == 1
    assert client.get("/api/history/chats?q=diabetes", headers=auth(t)).json()["total"] == 0
    client.patch(f"/api/chat/conversations/{cid}", headers=auth(t), json={"title": "My fever"})
    assert client.get("/api/history/chats", headers=auth(t)).json()["items"][0]["title"] == "My fever"
    assert client.delete(f"/api/chat/conversations/{cid}", headers=auth(t)).status_code == 204
    assert client.get("/api/history/chats", headers=auth(t)).json()["total"] == 0


def test_conversations_isolated_between_users(client, mailbox, llm):
    ta = verified_login(client, mailbox, email="a@example.com")
    cid = send(client, ta, "private question")["meta"][0]["conversation_id"]
    other = TestClient(app)
    tb = verified_login(other, mailbox, email="b@example.com")
    assert other.get(f"/api/chat/conversations/{cid}", headers=auth(tb)).status_code == 404
    assert other.patch(f"/api/chat/conversations/{cid}", headers=auth(tb), json={"title": "x"}).status_code == 404
    assert other.delete(f"/api/chat/conversations/{cid}", headers=auth(tb)).status_code == 404
    assert other.delete(f"/api/history/{cid}", headers=auth(tb)).status_code == 404
    assert other.post("/api/chat/message", headers=auth(tb), json={"content": "hi", "conversation_id": cid}).status_code == 404
    assert other.get("/api/history/chats?q=private", headers=auth(tb)).json()["total"] == 0


def test_safety_flags(client, mailbox, llm):
    t = verified_login(client, mailbox)
    assert send(client, t, "I have severe chest pain")["meta"][0]["safety"]["emergency"] is True
    assert send(client, t, "నాకు ఛాతీ నొప్పి ఉంది")["meta"][0]["safety"]["emergency"] is True
    assert send(client, t, "I want to end my life")["meta"][0]["safety"]["self_harm"] is True
    sys = llm["stream"][0]["system"]
    assert "112" in sys and "14416" in sys and "Do not diagnose" in sys


def test_llm_failures_are_reported_not_faked(client, mailbox, llm):
    t = verified_login(client, mailbox)
    llm["reply"] = gemini.GeminiRateLimited("quota", retry_after=30)
    ev = send(client, t, "hello")
    assert ev["error"][0] == {"code": "llm_rate_limited", "retry_after": 30} and "done" not in ev
    with SessionLocal() as db:
        assert db.scalar(select(ChatMessage).where(ChatMessage.role == "assistant")).status == "failed"


def test_not_configured(client, mailbox, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    t = verified_login(client, mailbox)
    r = client.post("/api/chat/message", headers=auth(t), json={"content": "hi"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "llm_not_configured"


# ------------------------------------------------------------------ long-term memory
def test_memory_off_by_default_and_requires_consent(client, mailbox, llm):
    t = verified_login(client, mailbox)
    llm["post"] = {"memories": [{"category": "diet", "content": "User is vegetarian"}]}
    send(client, t, "I'm vegetarian, suggest a breakfast")
    assert client.get("/api/chat/memory", headers=auth(t)).json()["items"] == []  # nothing stored without consent
    assert not any("memories" in g for g in llm["generate"])


def test_memory_extraction_pending_health_items_and_management(client, mailbox, llm):
    t = verified_login(client, mailbox)
    st = client.put("/api/chat/memory", headers=auth(t), json={"memory_enabled": True}).json()
    assert st["settings"]["memory_enabled"] and st["settings"]["consent_at"]
    llm["post"] = {"memories": [{"category": "diet", "content": "User is vegetarian"}, {"category": "health_context", "content": "User has asthma"}, {"category": "nonsense", "content": "x"}]}
    send(client, t, "I'm vegetarian and I have asthma")
    items = {m["content"]: m for m in client.get("/api/chat/memory", headers=auth(t)).json()["items"]}
    assert set(items) == {"User is vegetarian", "User has asthma"}
    assert items["User is vegetarian"]["status"] == "active"
    assert items["User has asthma"]["status"] == "pending" and items["User has asthma"]["expires_at"]

    # Pending health details are NOT given to the model until confirmed.
    llm["post"] = {}
    send(client, t, "what should I eat?")
    ctx = llm["stream"][-1]["contents"][0]["parts"][0]["text"]
    assert "User is vegetarian" in ctx and "asthma" not in ctx
    client.patch(f"/api/chat/memory/items/{items['User has asthma']['id']}", headers=auth(t), json={"status": "active"})
    send(client, t, "and for dinner?")
    assert "User has asthma" in llm["stream"][-1]["contents"][0]["parts"][0]["text"]

    # Edit, add, delete, clear.
    client.patch(f"/api/chat/memory/items/{items['User is vegetarian']['id']}", headers=auth(t), json={"content": "User is vegan"})
    client.post("/api/chat/memory/items", headers=auth(t), json={"category": "response_style", "content": "Prefers short answers"})
    assert len(client.get("/api/chat/memory", headers=auth(t)).json()["items"]) == 3
    assert client.delete(f"/api/chat/memory/items/{items['User has asthma']['id']}", headers=auth(t)).status_code == 204
    assert client.delete("/api/chat/memory", headers=auth(t)).status_code == 204
    assert client.get("/api/chat/memory", headers=auth(t)).json()["items"] == []


def test_memory_isolated(client, mailbox, llm):
    ta = verified_login(client, mailbox, email="a@example.com")
    item = client.post("/api/chat/memory/items", headers=auth(ta), json={"category": "allergy", "content": "Allergic to peanuts"}).json()
    other = TestClient(app)
    tb = verified_login(other, mailbox, email="b@example.com")
    assert other.get("/api/chat/memory", headers=auth(tb)).json()["items"] == []
    assert other.patch(f"/api/chat/memory/items/{item['id']}", headers=auth(tb), json={"status": "disabled"}).status_code == 404
    assert other.delete(f"/api/chat/memory/items/{item['id']}", headers=auth(tb)).status_code == 404
    other.put("/api/chat/memory", headers=auth(tb), json={"memory_enabled": True})
    send(other, tb, "hello")
    assert "peanuts" not in json.dumps(llm["stream"][-1]["contents"])


def test_long_conversation_is_summarised_and_context_is_bounded(client, mailbox, llm, monkeypatch):
    monkeypatch.setattr(chat_svc, "RECENT_TOKEN_BUDGET", 200)
    t = verified_login(client, mailbox)
    llm["reply"] = "x" * 300  # long replies so the token budget is exceeded quickly
    llm["post"] = {"summary": "User reported fever for 2 days; assistant suggested fluids."}
    cid = None
    for i in range(12):
        ev = send(client, t, f"message number {i} " + "y" * 200, conversation_id=cid)
        cid = ev["meta"][0]["conversation_id"]
    with SessionLocal() as db:
        assert db.scalar(select(ConversationSummary)) is not None
    last = llm["stream"][-1]["contents"]
    ctx = last[0]["parts"][0]["text"]
    assert "SUMMARY OF EARLIER PART OF THIS CONVERSATION" in ctx
    assert len(last) < 2 + 23  # far fewer than the 23 prior messages are resent
    assert client.get(f"/api/chat/summaries?conversation_id={cid}", headers=auth(t)).json()[0]["generated"] is True


# ------------------------------------------------------------------ voice
def _wav(seconds=1.0, rate=16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.sin(np.linspace(0, 440 * 2 * np.pi * seconds, int(rate * seconds))) * 8000).astype(np.int16).tobytes())
    return buf.getvalue()


def test_speech_to_text_validation_and_history(client, mailbox, llm, monkeypatch):
    t = verified_login(client, mailbox)
    monkeypatch.setattr(gemini, "transcribe", lambda data, mime, hint, names: {"text": "నాకు జ్వరం ఉంది", "language": "te"})
    r = client.post("/api/chat/speech-to-text", headers=auth(t), files={"file": ("a.wav", _wav(), "audio/wav")}, data={"language": "te"})
    assert r.status_code == 200 and r.json()["language"] == "te" and r.json()["duration_seconds"] == pytest.approx(1.0)
    assert client.post("/api/chat/speech-to-text", headers=auth(t), files={"file": ("a.webm", b"\x1aE\xdf\xa3" + b"0" * 2000, "audio/webm")}).status_code == 415
    assert client.post("/api/chat/speech-to-text", headers=auth(t), files={"file": ("a.wav", _wav(130), "audio/wav")}).status_code == 413
    monkeypatch.setattr(gemini, "transcribe", lambda *a: {"text": "", "language": None})
    r = client.post("/api/chat/speech-to-text", headers=auth(t), files={"file": ("a.wav", _wav(), "audio/wav")})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_speech_detected"
    data = json.loads(client.get("/api/profile/export", headers=auth(t)).content)
    assert [v["status"] for v in data["voice_transcriptions"]] == ["ok", "empty"]


def test_voice_one_shot_and_tts(client, mailbox, llm, monkeypatch):
    t = verified_login(client, mailbox)
    monkeypatch.setattr(gemini, "transcribe", lambda *a: {"text": "I have a cough", "language": "en"})
    r = client.post("/api/chat/voice", headers=auth(t), files={"file": ("a.wav", _wav(), "audio/wav")})
    assert r.status_code == 200 and r.json()["transcription"]["text"] == "I have a cough"
    conv = client.get(f"/api/chat/conversations/{r.json()['conversation_id']}", headers=auth(t)).json()
    assert conv["messages"][0]["message_type"] == "voice"
    monkeypatch.setattr(gemini, "tts", lambda text, voice="Kore": _wav(0.5))
    a = client.post("/api/chat/text-to-speech", headers=auth(t), json={"text": "నమస్కారం"})
    assert a.status_code == 200 and a.headers["content-type"] == "audio/wav" and a.content[:4] == b"RIFF"


def test_export_and_account_deletion_cover_chats(client, mailbox, llm):
    t = verified_login(client, mailbox)
    client.put("/api/chat/memory", headers=auth(t), json={"memory_enabled": True})
    client.post("/api/chat/memory/items", headers=auth(t), json={"category": "diet", "content": "Vegetarian"})
    send(client, t, "hello there")
    data = json.loads(client.get("/api/profile/export", headers=auth(t)).content)
    assert len(data["chat_messages"]) == 2 and data["chat_memories"][0]["content"] == "Vegetarian"
    client.request("DELETE", "/api/profile", headers=auth(t), json={"current_password": "Correct-Horse-42-battery"})
    with SessionLocal() as db:
        assert db.scalar(select(ChatMessage)) is None and db.scalar(select(UserChatMemory)) is None


def test_sse_parser_handles_split_multibyte_chunks():
    """Regression: events split mid-character/mid-line across network chunks must parse."""
    payload = json.dumps({"candidates": [{"content": {"parts": [{"text": "డెంగ్యూ జ్వరం"}]}}]}, ensure_ascii=False)
    raw = f"data: {payload}\r\n\r\ndata: {payload}\n\n".encode()

    class FakeResp:
        def iter_content(self, chunk_size=None):
            for i in range(0, len(raw), 7):  # 7-byte chunks split Telugu characters
                yield raw[i : i + 7]

    events = list(gemini._sse_events(FakeResp()))
    assert len(events) == 2 and events[0]["candidates"][0]["content"]["parts"][0]["text"] == "డెంగ్యూ జ్వరం"


def test_rate_limited_model_is_skipped_for_a_while(monkeypatch):
    from app.services import gemini as g

    class R:
        ok, status_code, text = False, 429, ""

        def json(self):
            return {"error": {"message": "quota"}}

    monkeypatch.setattr(g, "_key", lambda: "k")
    monkeypatch.setattr(g._session, "post", lambda *a, **k: R())
    g._cooldown.clear()
    with pytest.raises(g.GeminiRateLimited):
        g.generate("model-a", [{"role": "user", "parts": [{"text": "hi"}]}])
    assert g.cooling("model-a")
    assert g.prefer_available(["model-a", "model-b", "model-a"]) == ["model-b", "model-a"]
    g._cooldown.clear()
