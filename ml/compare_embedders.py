"""Compare local embedding models for MedlinePlus retrieval on the saved synthetic questions.
Model choice uses the *tune* split only; the chosen model is then reported by eval_retrieval.py
on the held-out test split."""
import json
import sys
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.services import knowledge  # noqa: E402

MODELS = {
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
    "BAAI/bge-m3": ("", ""),
}

chunks, _, _ = knowledge._kb()
data = json.loads((Path(__file__).parent / "eval" / "retrieval_questions.json").read_text())
qs = [q for q in data["questions"] if q["split"] == "tune"]
texts = [f"{c['title']}" + (f" (also called: {', '.join(c['also_called'])})" if c["also_called"] else "") + f"\n{c['text']}" for c in chunks]
results = {}
for name, (qp, pp) in MODELS.items():
    t0 = time.time()
    m = SentenceTransformer(name, device="cpu")
    emb = m.encode([pp + t for t in texts], normalize_embeddings=True, batch_size=16, show_progress_bar=False)
    qv = m.encode([qp + q["q"] for q in qs], normalize_embeddings=True, batch_size=32)
    t1 = time.time()
    per = {}
    for q, v in zip(qs, qv):
        scores = emb @ v
        urls = []
        for i in np.argsort(-scores):
            if chunks[int(i)]["url"] not in urls:
                urls.append(chunks[int(i)]["url"])
            if len(urls) == 4:
                break
        per.setdefault(q["lang"], []).append(q["url"] in urls)
    tq = time.time()
    m.encode(["query: test"] * 20)
    results[name] = {"hit@4_by_lang": {k: round(float(np.mean(v)), 3) for k, v in per.items()}, "hit@4_mean": round(float(np.mean([x for v in per.values() for x in v])), 3), "kb_embed_seconds": round(t1 - t0), "query_ms": round((time.time() - tq) / 20 * 1000)}
    print(name, results[name], flush=True)
(Path(__file__).parent / "eval" / "embedder_comparison.json").write_text(json.dumps(results, indent=2))
