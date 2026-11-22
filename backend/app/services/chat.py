"""Chat orchestration: context building, memory, retrieval, streaming and post-turn tasks.

Three memory levels:
  1. Short-term: the most recent messages of this conversation, within a token budget.
  2. Long-term (opt-in): user-approved memories (preferences, allergies, …) stored in PostgreSQL.
  3. Summaries: older parts of long conversations are summarised and stored; the summary is
     sent instead of the full history. Summaries of the user's *other* conversations are
     retrieved by embedding similarity (only the user's own, only with memory enabled).

Every piece of context is labelled by origin (user-provided, user-approved memory, ML estimate,
generated summary, reference source) so the model never treats its own output as fact.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from collections.abc import Iterator
from datetime import timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import ChatMessage, ChatPreference, Conversation, ConversationSummary, Prediction, User, UserChatMemory
from app.security import utcnow
from app.services import embeddings, gemini, knowledge
from app.services.knowledge import LANGUAGE_NAMES
from app.services.users import age_from_dob

log = logging.getLogger("healthai.chat")

RECENT_TOKEN_BUDGET = 3500
MIN_RECENT_MESSAGES = 6
SUMMARISE_AFTER = 10  # unsummarised messages outside the recent window
MEMORY_CATEGORIES = ("language", "diet", "allergy", "meal_preference", "health_context", "response_style", "other")

# Deterministic emergency pre-check (multilingual keywords). The model is also instructed to
# handle emergencies; this guarantees the banner even if the model misses it.
EMERGENCY = re.compile(
    r"(chest pain|can'?t breathe|cannot breathe|difficulty breathing|unconscious|fainted|stroke|seizure|heavy bleeding|"
    r"bleeding heavily|heart attack|severe allergic|anaphylaxis|choking|poison|overdose|"
    r"सीने में दर्द|छाती में दर्द|सांस नहीं|बेहोश|ఛాతీ నొప్పి|ఊపిరి ఆడటం లేదు|స్పృహ|மார்பு வலி|மூச்சு விட முடியவில்லை|"
    r"বুকে ব্যথা|শ্বাস নিতে পারছি না|छातीत दुखत|छाती में|سینے میں درد|سانس نہیں|ಎದೆ ನೋವು|ഉസിരു|നെഞ്ചുവേദന|ଛାତି ଯନ୍ତ୍ରଣା|છાતીમાં દુખાવો)",
    re.I,
)
SELF_HARM = re.compile(
    r"(suicid|kill myself|end my life|want to die|self[- ]harm|hurt myself|आत्महत्या|मरना चाहता|मरना चाहती|ఆత్మహత్య|"
    r"தற்கொலை|আত্মহত্যা|خودکشی|ಆತ್ಮಹತ್ಯೆ|ആത്മഹത്യ|ଆତ୍ମହତ୍ୟା|આત્મહત્યા)",
    re.I,
)


def est_tokens(text: str) -> int:
    return max(1, len(text) // 3)  # conservative for Indic scripts


def prefs(db: Session, user: User) -> ChatPreference:
    p = db.get(ChatPreference, user.id)
    if p is None:
        # Concurrency-safe: two simultaneous requests must not both try to create the row.
        db.execute(pg_insert(ChatPreference).values(user_id=user.id).on_conflict_do_nothing(index_elements=["user_id"]))
        db.commit()
        p = db.get(ChatPreference, user.id)
    return p


def active_memories(db: Session, user_id: uuid.UUID) -> list[UserChatMemory]:
    now = utcnow()
    rows = db.scalars(select(UserChatMemory).where(UserChatMemory.user_id == user_id, UserChatMemory.status == "active").order_by(UserChatMemory.created_at)).all()
    return [m for m in rows if m.expires_at is None or m.expires_at > now]


def reply_language_for(user: User, conv: Conversation, override: str | None) -> str:
    if override in LANGUAGE_NAMES:
        return override
    if conv.reply_language in LANGUAGE_NAMES:
        return conv.reply_language
    lp = user.language_preference
    return lp.chatbot_language if lp and lp.chatbot_language in LANGUAGE_NAMES else "en"


def safety_flags(text: str) -> dict:
    return {"emergency": bool(EMERGENCY.search(text)), "self_harm": bool(SELF_HARM.search(text))}


def _system_prompt(lang: str, style: str) -> str:
    length = {"brief": "Keep answers under about 80 words.", "detailed": "You may give detailed answers (up to about 350 words) when helpful.", "balanced": "Keep answers concise: usually under about 180 words."}[style]
    return f"""You are HealthAssist AI, a health-information assistant for people in India. You are not a doctor.

LANGUAGE: Reply in {LANGUAGE_NAMES[lang]} ({lang}), whatever language the user writes in, unless the user explicitly asks you to switch. Use simple everyday words; when a medical term may be unfamiliar, add the English term in parentheses, e.g. (dengue). Never use square brackets except for source citations like [1]. Keep drug names, test names and numbers accurate.

SAFETY RULES (always follow):
- Do not diagnose. Explain possibilities in general terms and say what kind of professional to see and how urgently.
- If anything suggests an emergency (chest pain, trouble breathing, stroke signs, severe bleeding, unconsciousness, seizures, severe allergic reaction, poisoning), start your reply by telling the user to call 112 or go to the nearest emergency department now.
- If the user mentions suicide or self-harm, respond with care, encourage them to reach out now, and give India's Tele-MANAS helpline 14416 (or 1-800-891-4416) and 112 for immediate danger.
- Do not give doses for prescription medicines or tell anyone to start, stop or change a prescribed medicine. For over-the-counter medicines, refer to the label or a pharmacist.
- For children, pregnancy, and the elderly, advise extra caution and earlier medical review.
- If you are unsure, say so. Never invent facts, statistics, sources or study results.

USING CONTEXT: You may receive labelled context blocks.
- SOURCES are passages from MedlinePlus (U.S. National Library of Medicine). Base factual statements on them when relevant and cite them inline as [1], [2] using their numbers. Only cite a number if that passage supports the statement. If the sources don't cover the question, answer from general medical knowledge without citations and say it is general information.
- USER PROFILE and REMEMBERED FACTS were provided or approved by the user; use them to personalise, but do not repeat them back unnecessarily.
- ML ESTIMATES are outputs of statistical models in this app. They are not diagnoses and may be wrong; never present them as confirmed conditions.
- SUMMARIES were generated automatically from earlier messages and may be imperfect.
- Your own earlier replies in the conversation are not verified facts.

STYLE: Warm, clear, practical. {length} Use short paragraphs or bullet points. End with a brief reminder to consult a doctor when the topic is medical."""


def _profile_block(db: Session, user: User) -> str | None:
    hp = user.health_profile
    bits = []
    age = age_from_dob(user.date_of_birth)
    if age:
        bits.append(f"age {age}")
    if user.gender in ("female", "male"):
        bits.append(user.gender)
    if hp:
        if hp.bmi:
            bits.append(f"BMI {hp.bmi}")
        if hp.activity_level:
            bits.append(f"activity: {hp.activity_level}")
        if hp.dietary_preference:
            bits.append(f"diet: {hp.dietary_preference}")
        if hp.food_allergies:
            bits.append("food allergies: " + ", ".join(hp.food_allergies))
        if hp.health_conditions:
            bits.append("conditions the user chose to share: " + ", ".join(hp.health_conditions))
    preds = db.scalars(select(Prediction).where(Prediction.user_id == user.id).order_by(Prediction.created_at.desc()).limit(3)).all()
    lines = []
    if bits:
        lines.append("USER PROFILE (provided by the user): " + "; ".join(bits))
    if preds:
        lines.append("ML ESTIMATES (from this app's statistical models, not diagnoses):")
        for p in preds:
            what = p.label if p.prediction_type == "symptoms" else f"{p.label} (score {p.score:.2f})"
            lines.append(f"- {p.created_at.date()} {p.prediction_type}: {what}")
    return "\n".join(lines) or None


def _latest_summary(db: Session, conv_id: uuid.UUID) -> ConversationSummary | None:
    return db.scalar(select(ConversationSummary).where(ConversationSummary.conversation_id == conv_id).order_by(ConversationSummary.created_at.desc()).limit(1))


def _recent_messages(db: Session, conv_id: uuid.UUID) -> tuple[list[ChatMessage], int]:
    """Most recent messages that fit the token budget (always at least MIN_RECENT_MESSAGES)."""
    rows = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conv_id, ChatMessage.status == "complete").order_by(ChatMessage.created_at.desc())).all()
    picked, used = [], 0
    for m in rows:
        t = est_tokens(m.content)
        if len(picked) >= MIN_RECENT_MESSAGES and used + t > RECENT_TOKEN_BUDGET:
            break
        picked.append(m)
        used += t
    return list(reversed(picked)), len(rows)


def _related_conversations(db: Session, user_id: uuid.UUID, conv_id: uuid.UUID, q: np.ndarray, k: int = 2) -> list[str]:
    rows = db.execute(select(Conversation.id, Conversation.title, Conversation.embedding).where(Conversation.user_id == user_id, Conversation.id != conv_id, Conversation.embedding.is_not(None))).all()
    scored = []
    for cid, title, emb in rows:
        v = np.asarray(emb, dtype=np.float32)
        s = float(v @ q / (np.linalg.norm(v) + 1e-9))
        if s >= 0.55:
            scored.append((s, cid, title))
    out = []
    for _s, cid, title in sorted(scored, reverse=True)[:k]:
        summ = _latest_summary(db, cid)
        if summ:
            out.append(f"- \"{title}\": {summ.summary}")
    return out


def build_request(db: Session, user: User, conv: Conversation, user_text: str, lang: str) -> tuple[str, list[dict], list[dict], dict]:
    """Returns (system_prompt, contents, sources, context_info)."""
    p = prefs(db, user)
    recent, total = _recent_messages(db, conv.id)

    # Retrieval query: include the previous user turn so short follow-ups ("since yesterday")
    # still retrieve the right topic.
    prev_user = [m.content for m in recent if m.role == "user"][-2:]
    rq = " ".join(prev_user[-1:] + [user_text]) if len(user_text) < 60 else user_text
    sources, q_vec = [], None
    try:
        q_vec = embeddings.embed_queries([rq])[0]
        if knowledge.kb_available():
            sources = _search_with(q_vec)
    except Exception as e:  # retrieval must never block answering; the answer then has no citations
        log.warning("retrieval skipped: %s", e)

    blocks = []
    if p.use_profile:
        pb = _profile_block(db, user)
        if pb:
            blocks.append(pb)
    if p.memory_enabled:
        mems = active_memories(db, user.id)
        if mems:
            blocks.append("REMEMBERED FACTS (approved by the user):\n" + "\n".join(f"- [{m.category}] {m.content}" for m in mems))
        if q_vec is not None:
            rel = _related_conversations(db, user.id, conv.id, q_vec)
            if rel:
                blocks.append("SUMMARIES OF THE USER'S EARLIER CONVERSATIONS (generated, may be imperfect):\n" + "\n".join(rel))
    imgs = _image_analyses(db, conv.id)
    if imgs:
        blocks.append("IMAGE ANALYSES IN THIS CONVERSATION (from this app's skin-lesion image model; estimates, NOT diagnoses; the model only knows 7 lesion types):\n" + "\n".join(imgs))
    summ = _latest_summary(db, conv.id)
    if summ and total > len(recent):
        blocks.append(f"SUMMARY OF EARLIER PART OF THIS CONVERSATION (generated, may be imperfect):\n{summ.summary}")
    if sources:
        blocks.append("SOURCES (MedlinePlus, U.S. National Library of Medicine):\n" + "\n\n".join(f"[{i + 1}] {s['title']} — {s['url']}\n{s['text']}" for i, s in enumerate(sources)))

    contents = []
    if blocks:
        contents.append({"role": "user", "parts": [{"text": "CONTEXT (not written by the user in this chat):\n\n" + "\n\n".join(blocks)}]})
        contents.append({"role": "model", "parts": [{"text": "Understood. I'll use this context carefully and follow the rules."}]})
    for m in recent:
        contents.append({"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]})
    contents.append({"role": "user", "parts": [{"text": user_text}]})
    info = {"recent_messages": len(recent), "total_messages": total, "used_summary": bool(summ and total > len(recent)), "memory_items": p.memory_enabled, "sources": len(sources)}
    return _system_prompt(lang, p.response_style), contents, sources, info


def _image_analyses(db: Session, conv_id: uuid.UUID) -> list[str]:
    from app.models import MedicalImageAnalysis
    from app.services import skin

    c = skin.card()
    names = c["class_names"] if c else {}
    rows = db.scalars(select(MedicalImageAnalysis).where(MedicalImageAnalysis.conversation_id == conv_id).order_by(MedicalImageAnalysis.created_at)).all()
    out = []
    for r in rows:
        if r.status == "ok":
            top3 = sorted(r.probabilities.items(), key=lambda kv: -kv[1])[:3]
            out.append(f"- {r.created_at:%Y-%m-%d %H:%M}: most likely category {names.get(r.predicted_class, r.predicted_class)} (calibrated probability {r.probability:.2f}); next: " + ", ".join(f"{names.get(k, k)} {v:.2f}" for k, v in top3[1:]))
        else:
            out.append(f"- {r.created_at:%Y-%m-%d %H:%M}: image not analysed ({r.status})")
    return out


def image_reply(db: Session, user: User, conv: Conversation, question: str | None, analysis: dict, lang: str) -> tuple[str, str]:
    """Generate the assistant's explanation of an image analysis. Returns (text, model)."""
    s = get_settings()
    from app.services import skin

    c = skin.card() or {}
    names = c.get("class_names", {})
    if analysis["status"] == "ok":
        probs = sorted(analysis["probabilities"].items(), key=lambda kv: -kv[1])
        facts = (
            f"The skin-lesion image model (trained on dermatoscopic images of 7 pigmented lesion types) gave these calibrated probabilities: "
            + "; ".join(f"{names.get(k, k)} {v:.0%}" for k, v in probs[:4])
            + f". Prompt dermatologist review advised by app rules: {analysis['safety']['prompt_review']}."
        )
        task = ("Explain this result to the user in plain language: what the most likely category generally is, how uncertain the model is, "
                "what the model cannot tell (it is not a diagnosis; only a doctor, often with a biopsy, can diagnose skin cancer; it only knows 7 lesion types and was trained on dermatoscope images, not phone photos), "
                "and what to do next (see a dermatologist, especially if the spot is new, changing, bleeding, itchy or irregular; urgently if the model suggests melanoma or carcinoma). "
                "Do not repeat every number; the app shows them in a table. Do not cite sources.")
    elif analysis["status"] == "rejected_not_skin":
        facts = f"The image was not analysed because it does not appear to show a close-up of a skin spot ({analysis['gate'].get('description', '')})."
        task = "Tell the user briefly that the image tool only analyses close-up photos of a single skin spot or mole, and invite them to upload one or describe their concern."
    else:
        facts = "The image was not analysed because it looks too different from the images the model was trained on."
        task = "Tell the user briefly that the photo could not be analysed reliably (it may be blurry, too far away, or not a skin lesion), suggest a clear, well-lit close-up of one spot, and recommend a doctor for any concern."
    prompt = f"IMAGE ANALYSIS RESULT (machine-learning estimate, not a diagnosis): {facts}\n\nUSER'S QUESTION: {question or '(none)'}\n\nTASK: {task}"
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    system = _system_prompt(lang, prefs(db, user).response_style)
    last: Exception | None = None
    # Explaining an already-computed result needs no large model: try the fast model first, with
    # short timeouts so an overloaded model fails over quickly instead of hanging.
    models = gemini.prefer_available([s.gemini_fast_model, *s.gemini_chat_fallback_models, s.gemini_chat_model])
    for model in models:
        try:
            return gemini.generate(model, contents, system, max_tokens=900, thinking="minimal", timeout=30).text.strip(), model
        except (gemini.GeminiRateLimited, gemini.GeminiUnavailable) as e:
            last = e
    raise last or gemini.GeminiUnavailable("no model")


def _search_with(q: np.ndarray, k: int = 4) -> list[dict]:
    chunks, emb, _ = knowledge._kb()
    scores = emb @ q
    out, seen = [], set()
    for i in np.argsort(-scores)[: k * 6]:
        c = chunks[int(i)]
        if scores[i] < knowledge.MIN_SCORE or c["url"] in seen:
            continue
        seen.add(c["url"])
        out.append({**c, "score": round(float(scores[i]), 3)})
        if len(out) == k:
            break
    return out


def extract_citations(text: str, sources: list[dict]) -> list[dict]:
    used = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", text) if 1 <= int(n) <= len(sources)})
    return [{"n": n, "title": sources[n - 1]["title"], "url": sources[n - 1]["url"], "source": "MedlinePlus"} for n in used]


def strip_invalid_citations(text: str, n_sources: int) -> str:
    return re.sub(r"\[(\d{1,2})\]", lambda m: m.group(0) if 1 <= int(m.group(1)) <= n_sources else "", text)


# ------------------------------------------------------------------ post-turn background work
def schedule_post_turn(user_id: uuid.UUID, conv_id: uuid.UUID, user_msg_id: uuid.UUID) -> None:
    threading.Thread(target=_post_turn_safe, args=(user_id, conv_id, user_msg_id), daemon=True).start()


def _post_turn_safe(user_id, conv_id, user_msg_id) -> None:
    try:
        post_turn(user_id, conv_id, user_msg_id)
    except Exception:  # never crash the server for background work
        log.exception("post-turn task failed")


def post_turn(user_id: uuid.UUID, conv_id: uuid.UUID, user_msg_id: uuid.UUID) -> None:
    s = get_settings()
    with SessionLocal() as db:
        conv = db.get(Conversation, conv_id)
        user_msg = db.get(ChatMessage, user_msg_id)
        if conv is None or user_msg is None:
            return
        p = db.get(ChatPreference, user_id)
        recent, total = _recent_messages(db, conv_id)
        summ = _latest_summary(db, conv_id)
        covered = summ.messages_covered if summ else 0
        outside = total - len(recent)
        need_title = not conv.title_is_custom and not conv.title
        need_summary = outside - covered >= SUMMARISE_AFTER
        need_memory = bool(p and p.memory_enabled)
        if not (need_title or need_summary or need_memory):
            return

        tasks, payload = [], {}
        if need_title:
            lang_name = LANGUAGE_NAMES.get(user_msg.reply_language or "en", "English")
            tasks.append(f'"title": a short neutral title (max 6 words) for this conversation, written in {lang_name}')
        if need_summary:
            older = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conv_id, ChatMessage.status == "complete").order_by(ChatMessage.created_at).limit(outside)).all()
            payload["previous_summary"] = summ.summary if summ else ""
            payload["older_messages"] = [{"role": m.role, "text": m.content[:1500]} for m in older]
            tasks.append('"summary": an updated factual summary (max 120 words, English) of previous_summary + older_messages: symptoms and their timing, advice given, decisions, open questions. Mark which facts came from the user and which were suggestions from the assistant.')
        if need_memory:
            payload["latest_user_message"] = user_msg.content
            tasks.append(
                '"memories": a list of durable facts the USER stated about themselves in latest_user_message that would help in future conversations: '
                f'objects {{"category": one of {list(MEMORY_CATEGORIES)}, "content": short English sentence}}. '
                "Include only stable preferences or facts (language, diet, allergies, meal preferences, long-term conditions, preferred answer style). "
                "Exclude temporary symptoms, questions, anything the assistant said, and anything not about the user. Return [] if none."
            )
        payload["conversation_start"] = [{"role": m.role, "text": m.content[:600]} for m in recent[:4]] if need_title else []
        prompt = "Return a JSON object with these keys:\n" + "\n".join(f"- {t}" for t in tasks) + "\n\nDATA:\n" + json.dumps(payload, ensure_ascii=False)
        try:
            res = gemini.generate(s.gemini_fast_model, [{"role": "user", "parts": [{"text": prompt}]}], json_mode=True, temperature=0.2, max_tokens=1200, thinking="minimal")
            out = json.loads(res.text)
        except (gemini.GeminiError, ValueError) as e:
            log.warning("post-turn LLM call failed: %s", e)
            return

        if need_title and isinstance(out.get("title"), str) and out["title"].strip():
            conv.title = out["title"].strip()[:200]
        if need_summary and isinstance(out.get("summary"), str) and out["summary"].strip():
            db.add(ConversationSummary(conversation_id=conv_id, user_id=user_id, summary=out["summary"].strip(), messages_covered=outside, covers_until=recent[0].created_at if recent else utcnow(), model=s.gemini_fast_model))
        if need_memory and isinstance(out.get("memories"), list):
            existing = {m.content.lower() for m in db.scalars(select(UserChatMemory).where(UserChatMemory.user_id == user_id)).all()}
            for item in out["memories"][:5]:
                if not isinstance(item, dict):
                    continue
                cat, content = item.get("category"), str(item.get("content", "")).strip()[:500]
                if cat not in MEMORY_CATEGORIES or not content or content.lower() in existing:
                    continue
                sensitive = cat == "health_context"
                db.add(UserChatMemory(
                    user_id=user_id, category=cat, content=content,
                    # Health details are never stored as active without the user's explicit confirmation.
                    status="pending" if sensitive else "active", source="extracted", source_message_id=user_msg_id,
                    expires_at=utcnow() + timedelta(days=s.health_memory_retention_days) if sensitive else None,
                ))
        db.commit()

        # Keep a conversation embedding for cross-conversation retrieval (memory users only).
        if need_memory:
            latest = _latest_summary(db, conv_id)
            basis = f"{conv.title}\n{latest.summary if latest else user_msg.content}"
            try:
                conv.embedding = embeddings.embed_passages([basis])[0].tolist()
                db.commit()
            except Exception as e:
                log.warning("conversation embedding skipped: %s", e)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def run_turn(db: Session, user: User, conv: Conversation, text: str, message_type: str, reply_override: str | None) -> Iterator[str]:
    """Saves the user message, streams the assistant reply as SSE, saves it, schedules post-turn work."""
    s = get_settings()
    detected, method = knowledge.detect_language(text)
    lang = reply_language_for(user, conv, reply_override)
    flags = safety_flags(text)
    user_msg = ChatMessage(conversation_id=conv.id, user_id=user.id, role="user", message_type=message_type, content=text, detected_language=detected, reply_language=lang, safety=flags)
    db.add(user_msg)
    conv.message_count += 1
    conv.last_message_at = utcnow()
    db.commit()
    yield sse("meta", {"conversation_id": str(conv.id), "user_message_id": str(user_msg.id), "detected_language": detected, "detection_method": method, "reply_language": lang, "safety": flags})

    try:
        system, contents, sources, info = build_request(db, user, conv, text, lang)
        parts: list[str] = []
        final: gemini.GenResult | None = None
        used_model = s.gemini_chat_model
        models = gemini.prefer_available([s.gemini_chat_model, *s.gemini_chat_fallback_models])
        for i, model in enumerate(models):
            used_model = model
            try:
                # The main model thinks briefly; fallbacks answer directly so the first words come sooner.
                for chunk in gemini.stream(model, contents, system, thinking="low" if model == s.gemini_chat_model else "minimal"):
                    if isinstance(chunk, gemini.GenResult):
                        final = chunk
                    else:
                        parts.append(chunk)
                        yield sse("delta", {"text": chunk})
                break
            except (gemini.GeminiRateLimited, gemini.GeminiUnavailable) as e:
                # Fall back only if nothing has been streamed yet and another model remains.
                if parts or i == len(models) - 1:
                    raise
                log.warning("chat model %s failed (%s); falling back", model, e.code)
        answer = strip_invalid_citations((final.text if final else "".join(parts)).strip(), len(sources))
        if not answer:
            raise gemini.GeminiUnavailable("empty answer")
    except Exception as e:  # never let the stream die silently: always tell the client
        if not isinstance(e, gemini.GeminiError):
            log.exception("chat turn failed")
        db.rollback()
        code = e.code if isinstance(e, gemini.GeminiError) else "llm_unavailable"
        failed = ChatMessage(conversation_id=conv.id, user_id=user.id, role="assistant", content="", status="failed", model=s.gemini_chat_model, safety={"error": code})
        db.add(failed)
        db.commit()
        yield sse("error", {"code": code, "retry_after": getattr(e, "retry_after", None)})
        return

    citations = extract_citations(answer, sources)
    msg = ChatMessage(
        conversation_id=conv.id, user_id=user.id, role="assistant", content=answer, reply_language=lang,
        citations=citations, safety=flags, model=used_model,
        usage={**(final.usage if final else {}), "context": info, "retrieved": [{"title": x["title"], "url": x["url"], "score": x["score"]} for x in sources]},
    )
    db.add(msg)
    conv.message_count += 1
    conv.last_message_at = utcnow()
    db.commit()
    yield sse("done", {"assistant_message": message_out(msg), "context": info})
    schedule_post_turn(user.id, conv.id, user_msg.id)


def message_out(m: ChatMessage) -> dict:
    return {
        "id": str(m.id), "role": m.role, "message_type": m.message_type, "content": m.content,
        "detected_language": m.detected_language, "reply_language": m.reply_language,
        "citations": m.citations, "safety": m.safety, "status": m.status, "created_at": m.created_at.isoformat() if m.created_at else utcnow().isoformat(),
        "attachment_id": (m.usage or {}).get("attachment_id"), "image_analysis": (m.usage or {}).get("image_analysis"),
    }
