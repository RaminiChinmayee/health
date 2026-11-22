"""Medical knowledge retrieval (MedlinePlus health topics) and input-language detection."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.services import embeddings

KB = Path(__file__).resolve().parent.parent / "data" / "kb"
MIN_SCORE = 0.80  # e5 cosine similarity below this is treated as "not relevant" (tuned in ml/eval_retrieval.py)

LANGUAGE_NAMES = {
    "en": "English", "hi": "Hindi", "bn": "Bengali", "mr": "Marathi", "te": "Telugu", "ta": "Tamil",
    "gu": "Gujarati", "ur": "Urdu", "kn": "Kannada", "or": "Odia", "ml": "Malayalam",
}

# Unicode blocks → language. Devanagari is shared by Hindi and Marathi.
_SCRIPTS = [
    (0x0980, 0x09FF, "bn"), (0x0A80, 0x0AFF, "gu"), (0x0B00, 0x0B7F, "or"), (0x0B80, 0x0BFF, "ta"),
    (0x0C00, 0x0C7F, "te"), (0x0C80, 0x0CFF, "kn"), (0x0D00, 0x0D7F, "ml"), (0x0900, 0x097F, "deva"),
    (0x0600, 0x06FF, "ur"), (0x0750, 0x077F, "ur"), (0xFB50, 0xFDFF, "ur"), (0xFE70, 0xFEFF, "ur"),
]
# Hindi vs Marathi (both Devanagari): count high-frequency function words that are distinctive to
# each language (chosen on the FLEURS *dev* split; evaluated on the test split). Words shared by
# both languages (या, ही, होता, अनेक …) are deliberately excluded.
_MR_WORDS = {"आणि", "आहे", "आहेत", "किंवा", "केले", "केली", "नाही", "काही", "मध्ये", "म्हणून", "हा", "हे", "आम्ही", "मला", "तुम्ही",
             "माझे", "माझ्या", "माझी", "आपण", "झाले", "झाला", "असे", "असते", "आहोत", "करा", "होईल", "त्यामुळे", "पण", "खूप", "दुखत", "ताप"}
_HI_WORDS = {"में", "के", "है", "हैं", "से", "और", "को", "का", "पर", "कि", "नहीं", "किया", "ने", "लिए", "था", "थे", "भी", "जाता", "करने",
             "इस", "मुझे", "मेरा", "मेरी", "क्या", "हूँ", "हूं", "रहा", "रही", "बहुत", "दर्द", "बुखार"}
_DEVA_WORD = re.compile(r"[\u0900-\u0963\u0966-\u097F]+")


# Marathi attaches case endings to words (genitive -च्या/-ची/-चा/-चे, -ांना, infinitive -ण्या…);
# Hindi uses separate postpositions instead.
_MR_SUFFIX = re.compile(r"(च्या|ाची|ाचा|ाचे|ांची|ांचा|ांचे|ांना|ण्या|ण्यात|ण्यास|मध्ये|ावर|ातील|ाने)$")


def _hindi_or_marathi(text: str) -> str:
    words = _DEVA_WORD.findall(text)
    mr = sum(w in _MR_WORDS for w in words) + sum(len(w) > 3 and bool(_MR_SUFFIX.search(w)) for w in words)
    hi = sum(w in _HI_WORDS for w in words)
    return "mr" if mr > hi else "hi"


# Common romanized-Hindi words (Hinglish); used only when the text is in Latin script.
_HINGLISH = re.compile(r"\b(mujhe|mera|meri|hai|hain|nahi|nahin|kya|kaise|kyun|bahut|dard|bukhar|sir|pet|aur|se|ko|ho|raha|rahi|tha|thi|kal|aaj)\b", re.I)


def detect_language(text: str) -> tuple[str, str]:
    """Return (language_code, method). Script-based, deterministic, no network call."""
    counts: dict[str, int] = {}
    latin = 0
    for ch in text:
        o = ord(ch)
        if ch.isascii() and ch.isalpha():
            latin += 1
            continue
        for lo, hi, code in _SCRIPTS:
            if lo <= o <= hi:
                counts[code] = counts.get(code, 0) + 1
                break
    if counts:
        code = max(counts, key=counts.get)
        if code == "deva":
            return _hindi_or_marathi(text), "script+lexicon"
        return code, "script"
    if latin and len(_HINGLISH.findall(text)) >= 2:
        return "hi", "romanized"
    return "en", "script"


@lru_cache
def _kb() -> tuple[list[dict], np.ndarray, dict]:
    meta = json.loads((KB / "chunks.json").read_text())
    emb = np.load(KB / "embeddings.npy").astype(np.float32)
    return meta["chunks"], emb, meta["source"]


def kb_available() -> bool:
    return (KB / "chunks.json").exists() and (KB / "embeddings.npy").exists()


def search(query: str, k: int = 4) -> list[dict]:
    """Top-k relevant MedlinePlus passages (one per topic) for a query in any language."""
    if not kb_available():
        return []
    chunks, emb, _ = _kb()
    q = embeddings.embed_queries([query])[0]
    scores = emb @ q
    order = np.argsort(-scores)
    out, seen = [], set()
    for i in order[: k * 6]:
        c = chunks[int(i)]
        if scores[i] < MIN_SCORE or c["url"] in seen:
            continue
        seen.add(c["url"])
        out.append({**c, "score": round(float(scores[i]), 3)})
        if len(out) == k:
            break
    return out


def kb_source() -> dict | None:
    return _kb()[2] if kb_available() else None
