"""Minimal Google Gemini REST client (generateContent, streaming, embeddings, transcription, TTS).

Errors are never hidden: callers receive GeminiNotConfigured / GeminiRateLimited /
GeminiUnavailable / GeminiBlocked and must show the user an honest message.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import time
import wave
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
import requests

from app.config import get_settings

log = logging.getLogger("healthai.gemini")
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(RuntimeError):
    code = "llm_unavailable"


class GeminiNotConfigured(GeminiError):
    code = "llm_not_configured"


class GeminiRateLimited(GeminiError):
    code = "llm_rate_limited"

    def __init__(self, msg: str, retry_after: int | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


class GeminiUnavailable(GeminiError):
    code = "llm_unavailable"


class GeminiBlocked(GeminiError):
    code = "llm_blocked"


@dataclass
class GenResult:
    text: str
    usage: dict = field(default_factory=dict)
    finish_reason: str | None = None


def _key() -> str:
    k = get_settings().gemini_api_key
    if not k:
        raise GeminiNotConfigured("GEMINI_API_KEY is not set")
    return k


def _retry_after(body: dict) -> int | None:
    for d in body.get("error", {}).get("details", []):
        if "retryDelay" in d:
            m = re.match(r"(\d+)", d["retryDelay"])
            if m:
                return int(m.group(1))
    return None


def _raise_for(r: requests.Response) -> None:
    if r.ok:
        return
    try:
        body = r.json()
    except ValueError:
        body = {}
    msg = body.get("error", {}).get("message", r.text[:200])
    if r.status_code == 429:
        raise GeminiRateLimited(msg, _retry_after(body))
    if r.status_code in (400, 403) and "API key" in msg:
        raise GeminiNotConfigured(msg)
    log.warning("Gemini HTTP %s: %s", r.status_code, msg[:300])
    raise GeminiUnavailable(msg)


_session = requests.Session()  # keep-alive: reuses the TLS connection between calls
_session.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=16))
_cooldown: dict[str, float] = {}  # model → monotonic time until which it is skipped


def cooling(model: str) -> bool:
    """True while a model recently answered "rate limited" / "overloaded" (skip it if possible)."""
    return _cooldown.get(model, 0.0) > time.monotonic()


def prefer_available(models: list[str]) -> list[str]:
    """Same models, de-duplicated, with any that are cooling down moved to the end."""
    models = list(dict.fromkeys(models))
    return [m for m in models if not cooling(m)] + [m for m in models if cooling(m)]


def _post(model: str, method: str, body: dict, timeout: int = 90, stream: bool = False) -> requests.Response:
    url = f"{BASE}/{model}:{method}" + ("?alt=sse" if stream else "")
    try:
        # (connect, read) timeouts: a hung connection fails over within 10 s.
        r = _session.post(url, json=body, headers={"x-goog-api-key": _key()}, timeout=(10, timeout), stream=stream)
    except requests.RequestException as e:
        _cooldown[model] = time.monotonic() + 30
        raise GeminiUnavailable(str(e)) from e
    try:
        _raise_for(r)
    except GeminiRateLimited as e:
        wait = getattr(e, "retry_after", None) or 60
        _cooldown[model] = time.monotonic() + min(max(float(wait), 15), 600)
        raise
    except GeminiUnavailable:
        _cooldown[model] = time.monotonic() + 30
        raise
    return r


def _text_of(candidate: dict) -> str:
    return "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", []) if not p.get("thought"))


def _check_blocked(data: dict) -> None:
    if data.get("promptFeedback", {}).get("blockReason"):
        raise GeminiBlocked(data["promptFeedback"]["blockReason"])


def generate(model: str, contents: list[dict], system: str | None = None, *, temperature: float = 0.4, max_tokens: int = 2048, json_mode: bool = False, thinking: str = "low", timeout: int = 90) -> GenResult:
    body: dict = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingLevel": thinking}},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    data = _post(model, "generateContent", body, timeout=timeout).json()
    _check_blocked(data)
    cands = data.get("candidates") or []
    if not cands:
        raise GeminiUnavailable("no candidates")
    return GenResult(text=_text_of(cands[0]), usage=data.get("usageMetadata", {}), finish_reason=cands[0].get("finishReason"))


def stream(model: str, contents: list[dict], system: str | None = None, *, temperature: float = 0.4, max_tokens: int = 2048, thinking: str = "low") -> Iterator[str | GenResult]:
    """Yields text chunks, then a final GenResult with the full text and usage."""
    body: dict = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingLevel": thinking}},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    r = _post(model, "streamGenerateContent", body, timeout=120, stream=True)
    full, usage, finish = [], {}, None
    with r:
        for data in _sse_events(r):
            _check_blocked(data)
            usage = data.get("usageMetadata", usage)
            for c in data.get("candidates", []):
                finish = c.get("finishReason", finish)
                t = _text_of(c)
                if t:
                    full.append(t)
                    yield t
    if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST") and not full:
        raise GeminiBlocked(finish)
    yield GenResult(text="".join(full), usage=usage, finish_reason=finish)


def _sse_events(r: requests.Response) -> Iterator[dict]:
    """Parse a Server-Sent Events byte stream. Events are split on blank lines at the *byte* level
    and decoded only when complete, so multi-byte UTF-8 characters (Indic scripts) and long events
    that span network chunks are never cut."""
    buf = b""
    for chunk in r.iter_content(chunk_size=None):
        buf += chunk.replace(b"\r\n", b"\n")
        while b"\n\n" in buf:
            block, buf = buf.split(b"\n\n", 1)
            data = b"\n".join(line[5:].lstrip() for line in block.split(b"\n") if line.startswith(b"data:"))
            if data:
                yield json.loads(data.decode("utf-8"))
    tail = b"\n".join(line[5:].lstrip() for line in buf.split(b"\n") if line.startswith(b"data:"))
    if tail.strip():
        yield json.loads(tail.decode("utf-8"))


def embed(texts: list[str], task: str = "RETRIEVAL_QUERY", dim: int = 768) -> np.ndarray:
    s = get_settings()
    model = s.gemini_embed_model
    body = {"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": t[:8000]}]}, "taskType": task, "outputDimensionality": dim} for t in texts]}
    data = _post(model, "batchEmbedContents", body, timeout=60).json()
    m = np.asarray([e["values"] for e in data["embeddings"]], dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


NO_SPEECH = "[NO_SPEECH]"
# The script each language must be written in. Without this, Urdu speech was often transcribed in
# Devanagari or romanised (found by ml/eval_speech_language.py).
SCRIPTS = {
    "en": "Latin script", "hi": "Devanagari script", "mr": "Devanagari script", "bn": "Bengali script",
    "te": "Telugu script", "ta": "Tamil script", "gu": "Gujarati script", "ur": "Urdu (Perso-Arabic, Nastaliq) script",
    "kn": "Kannada script", "or": "Odia script", "ml": "Malayalam script",
}


def transcribe(audio: bytes, mime: str, language_hint: str | None, language_names: dict[str, str]) -> dict:
    """Try each configured transcription model in order; move to the next on rate limit/outage."""
    last: GeminiError | None = None
    for model in prefer_available(list(get_settings().gemini_transcribe_models)):
        try:
            out = _transcribe_with(model, audio, mime, language_hint, language_names)
            return {**out, "model": model}
        except (GeminiRateLimited, GeminiUnavailable) as e:
            log.warning("transcription with %s failed (%s); trying next", model, e.code)
            last = e
    raise last or GeminiUnavailable("no transcription model configured")


def _transcribe_with(model: str, audio: bytes, mime: str, language_hint: str | None, language_names: dict[str, str]) -> dict:
    """Speech-to-text. Returns {"text", "language"}; empty text if no speech was found.
    The transcription model returns plain text (it does not support JSON mode); the language is
    detected afterwards from the transcript's script by the caller."""
    s = get_settings()
    if language_hint in language_names:
        hint = (
            f"The speaker most likely uses {language_names[language_hint]}; if so, write it in {SCRIPTS[language_hint]}. "
            "If they clearly speak a different language, write that language in its own standard script. "
        )
    else:
        hint = ""
    prompt = (
        f"Transcribe this audio exactly as spoken. Do not translate, transliterate or romanise. {hint}"
        "Keep English words that the speaker says in English as they are. "
        f"Output only the transcript, with no labels or commentary. If there is no intelligible speech, output exactly {NO_SPEECH}."
    )
    contents = [{"role": "user", "parts": [{"inlineData": {"mimeType": mime, "data": base64.b64encode(audio).decode()}}, {"text": prompt}]}]
    body = {"contents": contents, "generationConfig": {"temperature": 0.0}}
    data = _post(model, "generateContent", body, timeout=120).json()
    cands = data.get("candidates") or []
    text = (_text_of(cands[0]) if cands else "").strip()
    if not text or NO_SPEECH in text:
        return {"text": "", "language": None}
    return {"text": text, "language": None}


def tts(text: str, voice: str = "Kore") -> bytes:
    """Text-to-speech; returns a WAV file (PCM 16-bit mono 24 kHz)."""
    s = get_settings()
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
    }
    data = _post(s.gemini_tts_model, "generateContent", body, timeout=120).json()
    try:
        part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (KeyError, IndexError):
        raise GeminiUnavailable("no audio returned")
    pcm_or_wav = base64.b64decode(part["data"])
    if part.get("mimeType", "").startswith("audio/wav") or pcm_or_wav[:4] == b"RIFF":
        return pcm_or_wav
    rate = 24000
    m = re.search(r"rate=(\d+)", part.get("mimeType", ""))
    if m:
        rate = int(m.group(1))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm_or_wav)
    return buf.getvalue()
