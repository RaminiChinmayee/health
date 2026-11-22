"""Build the chatbot's medical knowledge base from MedlinePlus health topics.

Source: MedlinePlus Health Topics XML (U.S. National Library of Medicine), English topics only.
Topic summaries written by NLM are in the public domain; the app attributes and links each one.
https://medlineplus.gov/xml.html

Output: backend/app/data/kb/{chunks.json, embeddings.npy}
Embeddings: local multilingual-e5-small ("passage: " prefix, 384 dims, normalised). Queries are
embedded at runtime with the "query: " prefix; the model is multilingual, so questions in Indian
languages retrieve English passages. (A cloud embedding API was tried first but its free-tier daily
quota is far too small for this corpus and for per-message retrieval.)

Usage: python build_knowledge.py
"""
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import requests

from common import RAW, sha256

OUT = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "kb"
XML = RAW / "medlineplus_topics.xml"
MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-2")
DIM = 768
CHUNK_CHARS = 1400
OVERLAP = 200


def env_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        env = Path(__file__).resolve().parent.parent / "backend" / ".env"
        for line in env.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        sys.exit("GEMINI_API_KEY not set")
    return key


def clean(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<li>", "\n- ", s)
    s = re.sub(r"</(p|ul|ol|h\d)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def chunks_of(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK_CHARS)
        if end < len(text):  # break at a sentence end if possible
            cut = text.rfind(". ", start + CHUNK_CHARS // 2, end)
            end = cut + 1 if cut > 0 else end
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - OVERLAP, start + 1)
    return out


def parse() -> list[dict]:
    root = ET.parse(XML).getroot()
    rows = []
    for t in root.findall("health-topic"):
        if t.get("language") != "English":
            continue
        title, url = t.get("title"), t.get("url")
        also = [a.text for a in t.findall("also-called") if a.text]
        summary = clean(t.findtext("full-summary") or "")
        if not summary:
            continue
        groups = [g.text for g in t.findall("group") if g.text]
        for i, c in enumerate(chunks_of(summary)):
            header = title + (f" (also called: {', '.join(also)})" if also else "")
            rows.append({"id": f"{t.get('id')}-{i}", "title": title, "url": url, "also_called": also, "groups": groups, "text": c, "embed_text": f"{header}\n{c}"})
    return rows


def embed(texts: list[str], key: str, batch: int = 20) -> np.ndarray:
    """Embed in small batches, honouring the server's retry delay; progress is checkpointed so an
    interrupted run resumes where it stopped."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents"
    ckpt = OUT / "embeddings.partial.npy"
    OUT.mkdir(parents=True, exist_ok=True)
    vecs = list(np.load(ckpt)) if ckpt.exists() else []
    if vecs:
        print(f"  resuming at {len(vecs)}", flush=True)
    while len(vecs) < len(texts):
        chunk = texts[len(vecs) : len(vecs) + batch]
        body = {"requests": [{"model": f"models/{MODEL}", "content": {"parts": [{"text": t}]}, "taskType": "RETRIEVAL_DOCUMENT", "outputDimensionality": DIM} for t in chunk]}
        r = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=120)
        if r.status_code == 429 or r.status_code >= 500:
            wait, quotas = 65, []
            try:
                for d in r.json().get("error", {}).get("details", []):
                    quotas += [v.get("quotaId") for v in d.get("violations", [])]
                    if "retryDelay" in d:
                        # Per-minute limits sometimes report a misleading long delay; cap it.
                        wait = min(65, int(re.match(r"(\d+)", d["retryDelay"]).group(1)) + 2)
            except ValueError:
                pass
            print(f"  {r.status_code} at {len(vecs)} {quotas}; waiting {wait}s", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        vecs += [e["values"] for e in r.json()["embeddings"]]
        np.save(ckpt, np.asarray(vecs, dtype=np.float32))
        print(f"  embedded {len(vecs)}/{len(texts)}", flush=True)
        time.sleep(15)  # stay under the free tier's per-minute limit (~80 passages/min)
    ckpt.unlink(missing_ok=True)
    m = np.asarray(vecs, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from app.services import embeddings

    rows = parse()
    print(f"{len(rows)} chunks from {len({r['url'] for r in rows})} English topics", flush=True)
    t0 = time.time()
    emb = embeddings.embed_passages([r["embed_text"] for r in rows])
    print(f"embedded in {time.time() - t0:.0f}s", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "embeddings.partial.npy").unlink(missing_ok=True)
    np.save(OUT / "embeddings.npy", emb.astype(np.float16))
    meta = {
        "source": {
            "name": "MedlinePlus Health Topics (U.S. National Library of Medicine)",
            "url": "https://medlineplus.gov/xml.html",
            "license": "NLM-authored summaries are public domain; attribute MedlinePlus and link to the topic page.",
            "file": XML.name,
            "file_sha256": sha256(XML),
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "embedding_model": embeddings.model_name(),
            "dimensions": int(emb.shape[1]),
        },
        "chunks": [{k: r[k] for k in ("id", "title", "url", "also_called", "groups", "text")} for r in rows],
    }
    (OUT / "chunks.json").write_text(json.dumps(meta, ensure_ascii=False))
    print("saved", OUT)
