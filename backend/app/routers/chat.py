"""Chatbot endpoints: /api/chat/*  and  /api/history/chats.  All scoped to the authenticated user."""
import hashlib
import io
import uuid
import wave
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import ChatAttachment, ChatMessage, ChatPreference, Conversation, ConversationSummary, User, UserChatMemory, VoiceTranscription
from app.security import utcnow
from app.services import chat as svc
from app.services import gemini
from app.services.knowledge import LANGUAGE_NAMES, detect_language

router = APIRouter(tags=["chat"])
Lang = Literal["en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "or", "ml"]


def _err(status: int, code: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, **extra})


def _llm_http(e: gemini.GeminiError) -> HTTPException:
    status = 429 if isinstance(e, gemini.GeminiRateLimited) else 503
    return _err(status, e.code, retry_after=getattr(e, "retry_after", None))


def _owned_conv(db: Session, user: User, cid: uuid.UUID) -> Conversation:
    c = db.scalar(select(Conversation).where(Conversation.id == cid, Conversation.user_id == user.id))
    if c is None:
        raise _err(404, "not_found")
    return c


def conv_out(c: Conversation, preview: str | None = None) -> dict:
    return {"id": str(c.id), "title": c.title, "reply_language": c.reply_language, "message_count": c.message_count, "created_at": c.created_at.isoformat(), "last_message_at": c.last_message_at.isoformat(), "preview": preview}


# ------------------------------------------------------------------ messages
class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    reply_language: Lang | None = None
    message_type: Literal["text", "voice"] = "text"


@router.post("/api/chat/message")
def send_message(body: MessageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not get_settings().gemini_api_key:
        raise _err(503, "llm_not_configured")
    if body.conversation_id:
        conv = _owned_conv(db, user, body.conversation_id)
    else:
        conv = Conversation(user_id=user.id, reply_language=body.reply_language)
        db.add(conv)
        db.commit()
    if body.reply_language and body.reply_language != conv.reply_language:
        conv.reply_language = body.reply_language  # switching language mid-conversation
        db.commit()
    return StreamingResponse(
        svc.run_turn(db, user, conv, body.content.strip(), body.message_type, body.reply_language),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------ conversations
@router.get("/api/history/chats")
def list_chats(q: str | None = Query(None, max_length=200), limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(Conversation).where(Conversation.user_id == user.id, Conversation.message_count > 0)
    if q:
        like = f"%{q.strip()}%"
        hits = select(ChatMessage.conversation_id).where(ChatMessage.user_id == user.id, ChatMessage.content.ilike(like))
        query = query.where(or_(Conversation.title.ilike(like), Conversation.id.in_(hits)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Conversation.last_message_at.desc()).limit(limit).offset(offset)).all()
    out = []
    for c in rows:
        first = db.scalar(select(ChatMessage.content).where(ChatMessage.conversation_id == c.id, ChatMessage.role == "user").order_by(ChatMessage.created_at).limit(1))
        out.append(conv_out(c, (first or "")[:120]))
    return {"total": total, "items": out}


@router.get("/api/chat/conversations/{cid}")
def get_conversation(cid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _owned_conv(db, user, cid)
    msgs = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == c.id).order_by(ChatMessage.created_at)).all()
    return {**conv_out(c), "messages": [svc.message_out(m) for m in msgs]}


class ConvPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    reply_language: Lang | None = None


@router.patch("/api/chat/conversations/{cid}")
def patch_conversation(cid: uuid.UUID, body: ConvPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _owned_conv(db, user, cid)
    if body.title:
        c.title, c.title_is_custom = body.title.strip(), True
    if body.reply_language:
        c.reply_language = body.reply_language
    db.commit()
    return conv_out(c)


def _delete_conv_files(db: Session, user: User, conv_ids: list[uuid.UUID]) -> None:
    root = get_settings().storage_dir.resolve()
    for a in db.scalars(select(ChatAttachment).where(ChatAttachment.user_id == user.id, ChatAttachment.conversation_id.in_(conv_ids))).all():
        p = (root / a.storage_path).resolve()
        if root in p.parents:
            p.unlink(missing_ok=True)


@router.delete("/api/chat/conversations/{cid}", status_code=204)
def delete_conversation(cid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _owned_conv(db, user, cid)
    _delete_conv_files(db, user, [c.id])
    db.delete(c)
    db.commit()


@router.delete("/api/chat/conversations", status_code=204)
def delete_all_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = list(db.scalars(select(Conversation.id).where(Conversation.user_id == user.id)).all())
    _delete_conv_files(db, user, ids)
    db.execute(delete(Conversation).where(Conversation.user_id == user.id))
    db.commit()


@router.get("/api/chat/summaries")
def list_summaries(conversation_id: uuid.UUID | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(ConversationSummary).where(ConversationSummary.user_id == user.id)
    if conversation_id:
        q = q.where(ConversationSummary.conversation_id == conversation_id)
    rows = db.scalars(q.order_by(ConversationSummary.created_at.desc()).limit(50)).all()
    return [{"id": str(r.id), "conversation_id": str(r.conversation_id), "summary": r.summary, "messages_covered": r.messages_covered, "created_at": r.created_at.isoformat(), "generated": True} for r in rows]


# ------------------------------------------------------------------ memory
def memory_out(m: UserChatMemory) -> dict:
    return {"id": str(m.id), "category": m.category, "content": m.content, "status": m.status, "source": m.source, "expires_at": m.expires_at.isoformat() if m.expires_at else None, "created_at": m.created_at.isoformat()}


def _memory_state(db: Session, user: User) -> dict:
    p = svc.prefs(db, user)
    db.commit()
    now = utcnow()
    items = db.scalars(select(UserChatMemory).where(UserChatMemory.user_id == user.id).order_by(UserChatMemory.created_at.desc())).all()
    return {
        "settings": {"memory_enabled": p.memory_enabled, "use_profile": p.use_profile, "response_style": p.response_style, "consent_at": p.memory_consent_at.isoformat() if p.memory_consent_at else None},
        "items": [memory_out(m) for m in items if m.expires_at is None or m.expires_at > now],
        "retention": {"health_context_days": get_settings().health_memory_retention_days},
    }


@router.get("/api/chat/memory")
def get_memory(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _memory_state(db, user)


class MemorySettingsIn(BaseModel):
    memory_enabled: bool | None = None
    use_profile: bool | None = None
    response_style: Literal["brief", "balanced", "detailed"] | None = None


@router.put("/api/chat/memory")
def put_memory(body: MemorySettingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = svc.prefs(db, user)
    if body.memory_enabled is not None:
        if body.memory_enabled and not p.memory_enabled:
            p.memory_consent_at = utcnow()
        p.memory_enabled = body.memory_enabled
    if body.use_profile is not None:
        p.use_profile = body.use_profile
    if body.response_style:
        p.response_style = body.response_style
    db.commit()
    return _memory_state(db, user)


class MemoryItemIn(BaseModel):
    category: Literal["language", "diet", "allergy", "meal_preference", "health_context", "response_style", "other"]
    content: str = Field(min_length=2, max_length=500)


@router.post("/api/chat/memory/items", status_code=201)
def add_memory(body: MemoryItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    days = get_settings().health_memory_retention_days
    m = UserChatMemory(user_id=user.id, category=body.category, content=body.content.strip(), status="active", source="user_added", expires_at=utcnow() + timedelta(days=days) if body.category == "health_context" else None)
    db.add(m)
    db.commit()
    return memory_out(m)


class MemoryPatch(BaseModel):
    content: str | None = Field(default=None, min_length=2, max_length=500)
    status: Literal["active", "disabled"] | None = None  # confirming a pending item = set active


def _owned_mem(db: Session, user: User, mid: uuid.UUID) -> UserChatMemory:
    m = db.scalar(select(UserChatMemory).where(UserChatMemory.id == mid, UserChatMemory.user_id == user.id))
    if m is None:
        raise _err(404, "not_found")
    return m


@router.patch("/api/chat/memory/items/{mid}")
def patch_memory(mid: uuid.UUID, body: MemoryPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = _owned_mem(db, user, mid)
    if body.content:
        m.content = body.content.strip()
    if body.status:
        if body.status == "active" and m.category == "health_context":
            m.expires_at = utcnow() + timedelta(days=get_settings().health_memory_retention_days)
        m.status = body.status
    db.commit()
    return memory_out(m)


@router.delete("/api/chat/memory/items/{mid}", status_code=204)
def delete_memory_item(mid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_owned_mem(db, user, mid))
    db.commit()


@router.delete("/api/chat/memory", status_code=204)
def clear_memory(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Clear all stored chatbot memory: remembered facts, summaries and conversation embeddings."""
    db.execute(delete(UserChatMemory).where(UserChatMemory.user_id == user.id))
    db.execute(delete(ConversationSummary).where(ConversationSummary.user_id == user.id))
    for c in db.scalars(select(Conversation).where(Conversation.user_id == user.id)).all():
        c.embedding = None
    db.commit()


# ------------------------------------------------------------------ voice
AUDIO_SIGNATURES = [(b"RIFF", "audio/wav"), (b"OggS", "audio/ogg"), (b"fLaC", "audio/flac"), (b"ID3", "audio/mp3"), (b"\xff\xfb", "audio/mp3"), (b"\xff\xf3", "audio/mp3")]


def _sniff_audio(data: bytes) -> str | None:
    for sig, mime in AUDIO_SIGNATURES:
        if data.startswith(sig):
            if mime == "audio/wav" and data[8:12] != b"WAVE":
                return None
            return mime
    return None


def _wav_seconds(data: bytes) -> float | None:
    try:
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError):
        return None


async def _read_audio(file: UploadFile) -> tuple[bytes, str, float | None]:
    s = get_settings()
    data = await file.read(s.max_audio_bytes + 1)
    if len(data) > s.max_audio_bytes:
        raise _err(413, "file_too_large", max_bytes=s.max_audio_bytes)
    if len(data) < 1000:
        raise _err(422, "audio_too_short")
    mime = _sniff_audio(data)
    if mime is None:
        raise _err(415, "unsupported_audio_type")
    secs = _wav_seconds(data) if mime == "audio/wav" else None
    if secs is not None and secs > s.max_audio_seconds:
        raise _err(413, "audio_too_long", max_seconds=s.max_audio_seconds)
    if secs is not None and secs < 0.3:
        raise _err(422, "audio_too_short")
    return data, mime, secs


def _store_audio(db: Session, user: User, conv_id: uuid.UUID | None, data: bytes, mime: str) -> ChatAttachment:
    rel = f"audio/{user.id}/{uuid.uuid4().hex}.{mime.split('/')[1]}"
    p = get_settings().storage_dir.resolve() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    a = ChatAttachment(user_id=user.id, conversation_id=conv_id, kind="audio", storage_path=rel, mime_type=mime, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    db.add(a)
    db.flush()
    return a


def _transcribe(db: Session, user: User, data: bytes, mime: str, secs: float | None, language: str | None, conv_id: uuid.UUID | None, keep_audio: bool) -> VoiceTranscription:
    s = get_settings()
    att = _store_audio(db, user, conv_id, data, mime) if keep_audio else None
    rec = VoiceTranscription(user_id=user.id, conversation_id=conv_id, attachment_id=att.id if att else None, model=s.gemini_transcribe_models[0], language_hint=language, duration_seconds=secs, status="failed")
    try:
        out = gemini.transcribe(data, mime, language, LANGUAGE_NAMES)
    except gemini.GeminiError as e:
        rec.error = e.code
        db.add(rec)
        db.commit()
        raise _llm_http(e)
    text = out["text"]
    rec.model = out.get("model", rec.model)
    lang = out["language"] if out["language"] in LANGUAGE_NAMES else (detect_language(text)[0] if text else None)
    rec.transcript, rec.detected_language, rec.status = text, lang, ("ok" if text else "empty")
    db.add(rec)
    db.commit()
    return rec


@router.post("/api/chat/speech-to-text")
async def speech_to_text(
    file: UploadFile = File(...),
    language: Lang | None = Form(None),
    conversation_id: uuid.UUID | None = Form(None),
    keep_audio: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if conversation_id:
        _owned_conv(db, user, conversation_id)
    data, mime, secs = await _read_audio(file)
    rec = _transcribe(db, user, data, mime, secs, language, conversation_id, keep_audio)
    if rec.status == "empty":
        raise _err(422, "no_speech_detected", transcription_id=str(rec.id))
    return {"transcription_id": str(rec.id), "text": rec.transcript, "language": rec.detected_language, "duration_seconds": secs}


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    voice: Literal["Kore", "Puck", "Charon", "Aoede", "Leda", "Orus"] = "Kore"


_tts_cache: dict[str, bytes] = {}


@router.post("/api/chat/text-to-speech")
def text_to_speech(body: TTSIn, _: User = Depends(get_current_user)):
    key = hashlib.sha256(f"{body.voice}|{body.text}".encode()).hexdigest()
    audio = _tts_cache.get(key)
    if audio is None:
        try:
            audio = gemini.tts(body.text, body.voice)
        except gemini.GeminiError as e:
            raise _llm_http(e)
        if len(_tts_cache) > 200:
            _tts_cache.clear()
        _tts_cache[key] = audio
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/api/chat/voice")
async def voice_message(
    file: UploadFile = File(...),
    conversation_id: uuid.UUID | None = Form(None),
    language: Lang | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One-shot voice turn: transcribe, then answer (non-streaming). The web app instead shows the
    transcript for editing first (speech-to-text + message)."""
    conv = _owned_conv(db, user, conversation_id) if conversation_id else None
    data, mime, secs = await _read_audio(file)
    rec = _transcribe(db, user, data, mime, secs, language, conv.id if conv else None, keep_audio=False)
    if rec.status == "empty":
        raise _err(422, "no_speech_detected")
    if conv is None:
        conv = Conversation(user_id=user.id, reply_language=language)
        db.add(conv)
        db.commit()
    events = list(svc.run_turn(db, user, conv, rec.transcript, "voice", language))
    done = next((e for e in events if e.startswith("event: done")), None)
    if done is None:
        err = next((e for e in events if e.startswith("event: error")), "")
        raise _err(503, "llm_unavailable", detail=err[:200])
    import json as _json

    payload = _json.loads(done.split("data: ", 1)[1])
    return {"conversation_id": str(conv.id), "transcription": {"id": str(rec.id), "text": rec.transcript, "language": rec.detected_language}, "assistant_message": payload["assistant_message"]}


# ------------------------------------------------------------------ images (skin-lesion analysis)
def analysis_out(a, names: dict | None = None) -> dict:
    return {
        "id": str(a.id), "status": a.status, "model_key": a.model_key, "model_version": a.model_version,
        "predicted_class": a.predicted_class, "probability": a.probability, "probabilities": a.probabilities,
        "gate": a.gate, "safety": a.safety, "question": a.question, "conversation_id": str(a.conversation_id) if a.conversation_id else None,
        "attachment_id": str(a.attachment_id) if a.attachment_id else None, "created_at": a.created_at.isoformat() if a.created_at else utcnow().isoformat(),
    }


@router.post("/api/chat/image")
async def chat_image(
    file: UploadFile = File(...),
    question: str | None = Form(None, max_length=2000),
    conversation_id: uuid.UUID | None = Form(None),
    reply_language: Lang | None = Form(None),
    consent: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a skin photo with an optional question. The image is validated, stored privately,
    screened (vision check + out-of-distribution check) and, if suitable, classified. The assistant
    then explains the result in the conversation."""
    from app.models import MedicalImageAnalysis
    from app.services import skin

    if not consent:
        raise _err(422, "image_consent_required")
    if not skin.available():
        raise _err(503, "image_model_unavailable")
    data = await file.read(skin.MAX_BYTES + 1)
    try:
        img, webp = skin.validate_and_normalise(data)
    except skin.ImageRejected as e:
        status = 413 if e.code == "file_too_large" else 415 if e.code == "unsupported_image_type" else 422
        raise _err(status, e.code, **e.details)

    conv = _owned_conv(db, user, conversation_id) if conversation_id else None
    if conv is None:
        conv = Conversation(user_id=user.id, reply_language=reply_language)
        db.add(conv)
        db.commit()
    lang = svc.reply_language_for(user, conv, reply_language)

    rel = f"uploads/{user.id}/{uuid.uuid4().hex}.webp"
    path = get_settings().storage_dir.resolve() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(webp)
    att = ChatAttachment(user_id=user.id, conversation_id=conv.id, kind="image", storage_path=rel, mime_type="image/webp", size_bytes=len(webp), sha256=hashlib.sha256(webp).hexdigest())
    db.add(att)
    db.flush()
    user_msg = ChatMessage(conversation_id=conv.id, user_id=user.id, role="user", message_type="image", content=(question or "").strip() or "[image]", reply_language=lang, usage={"attachment_id": str(att.id)})
    db.add(user_msg)
    db.flush()
    att.message_id = user_msg.id

    from fastapi.concurrency import run_in_threadpool

    try:
        result = await run_in_threadpool(skin.analyse, img, webp)
    except Exception:  # never invent a result
        import logging

        logging.getLogger("healthai.skin").exception("image analysis failed")
        result = {"status": "failed", "model_key": "skin", "model_version": (skin.card() or {}).get("version", "?"), "gate": {}}
    a = MedicalImageAnalysis(
        user_id=user.id, conversation_id=conv.id, attachment_id=att.id, model_key=result["model_key"], model_version=result["model_version"],
        status=result["status"], predicted_class=result.get("predicted_class"), probability=result.get("probability"),
        probabilities=result.get("probabilities", {}), ood_distance=result.get("ood_distance"), gate=result.get("gate", {}),
        question=question, safety=result.get("safety", {}),
    )
    db.add(a)
    conv.message_count += 1
    conv.last_message_at = utcnow()
    db.commit()

    reply_text, reply_model, status = None, None, "complete"
    if result["status"] != "failed":
        try:
            reply_text, reply_model = await run_in_threadpool(svc.image_reply, db, user, conv, question, result, lang)
        except gemini.GeminiError:
            reply_text = None  # the structured result card is still shown; no invented text
    if reply_text is None:
        status = "complete" if result["status"] != "failed" else "failed"
        reply_text = ""
    bot = ChatMessage(
        conversation_id=conv.id, user_id=user.id, role="assistant", message_type="text", content=reply_text, reply_language=lang,
        model=reply_model, status=status if reply_text or result["status"] == "ok" else status,
        safety={"image_concern": bool(result.get("safety", {}).get("prompt_review"))}, usage={"image_analysis": analysis_out(a)},
    )
    db.add(bot)
    conv.message_count += 1
    db.commit()
    svc.schedule_post_turn(user.id, conv.id, user_msg.id)
    return {"conversation_id": str(conv.id), "user_message": svc.message_out(user_msg), "assistant_message": svc.message_out(bot), "analysis": analysis_out(a)}


@router.get("/api/chat/attachments/{aid}")
def get_attachment(aid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Serve a private upload to its owner only (never via a public URL)."""
    from fastapi.responses import FileResponse

    a = db.scalar(select(ChatAttachment).where(ChatAttachment.id == aid, ChatAttachment.user_id == user.id))
    if a is None:
        raise _err(404, "not_found")
    root = get_settings().storage_dir.resolve()
    p = (root / a.storage_path).resolve()
    if root not in p.parents or not p.exists():
        raise _err(404, "not_found")
    return FileResponse(p, media_type=a.mime_type, headers={"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})


@router.get("/api/history/images")
def list_images(limit: int = Query(50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models import MedicalImageAnalysis

    rows = db.scalars(select(MedicalImageAnalysis).where(MedicalImageAnalysis.user_id == user.id).order_by(MedicalImageAnalysis.created_at.desc()).limit(limit)).all()
    return {"total": len(rows), "items": [analysis_out(r) for r in rows]}


@router.get("/api/chat/image-model")
def image_model_info(_: User = Depends(get_current_user)):
    from app.services import skin

    c = skin.card()
    if c is None:
        raise _err(503, "image_model_unavailable")
    t = c["evaluation"]["test"]
    return {
        "version": c["version"], "architecture": c["architecture"], "classes": c["classes"], "class_names": c["class_names"],
        "dataset": {k: c["dataset"][k] for k in ("name", "source", "citation", "license", "population")}, "limitations": c["limitations"],
        "metrics": {k: t[k] for k in ("n_test", "accuracy", "balanced_accuracy", "macro_f1", "macro_roc_auc_ovr")} | {"per_class": t["per_class"]},
        "protocol": c["evaluation"]["protocol"],
    }
