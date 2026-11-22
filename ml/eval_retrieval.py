"""Evaluate knowledge retrieval (MedlinePlus) for multilingual questions and tune the relevance
threshold.

Test questions are SYNTHETIC: for a random sample of MedlinePlus topics, Gemini writes one short
lay question per language about that topic (en, hi, te, ta, bn, ur); a set of clearly off-topic
(non-health) questions is generated the same way. Each question's "correct" topic is the topic it
was generated from. Topics are split in half: the threshold is chosen on the first half and all
metrics are reported on the second half.

Metrics: hit@1, hit@4 (correct topic among the 4 passages the chatbot receives), MRR, and the
false-retrieval rate for off-topic questions at the chosen threshold.
Usage: python eval_retrieval.py [n_topics]
"""
import json
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.config import get_settings  # noqa: E402
from app.services import embeddings, gemini, knowledge  # noqa: E402

LANGS = {"en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "bn": "Bengali", "ur": "Urdu"}
OUT = Path(__file__).resolve().parent / "eval"
CACHE = OUT / "retrieval_questions.json"


def gen(prompt: str, max_tokens: int = 800) -> dict:
    for _ in range(15):
        try:
            r = gemini.generate(get_settings().gemini_fast_model, [{"role": "user", "parts": [{"text": prompt}]}], json_mode=True, temperature=0.7, max_tokens=max_tokens, thinking="minimal")
            return json.loads(r.text)
        except gemini.GeminiRateLimited as e:
            time.sleep(min(65, (e.retry_after or 30) + 2))
        except (gemini.GeminiUnavailable, ValueError):
            time.sleep(20)
    raise RuntimeError("generation failed")


def build_questions(n_topics: int) -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    partial = OUT / "retrieval_questions.partial.json"
    chunks, _, _ = knowledge._kb()
    topics = sorted({(c["title"], c["url"]) for c in chunks})
    random.Random(42).shuffle(topics)
    qs = json.loads(partial.read_text()) if partial.exists() else []
    done = {q["url"] for q in qs}
    for i, (title, url) in enumerate(topics[:n_topics]):
        if url in done:
            continue
        out = gen(
            f'Write one short question (max 20 words) that an ordinary person in India might ask a health chatbot, where the answer would be found in a health article titled "{title}". '
            f"Do not copy the title word for word. Give the question in each language, in its native script: {json.dumps(LANGS)}. Return JSON object mapping language code to question."
        )
        for lang in LANGS:
            if isinstance(out.get(lang), str):
                qs.append({"topic": title, "url": url, "lang": lang, "q": out[lang], "split": "tune" if i % 2 == 0 else "test"})
        OUT.mkdir(exist_ok=True)
        partial.write_text(json.dumps(qs, ensure_ascii=False))
        print(f"  generated {i + 1}/{n_topics}", flush=True)
    off = gen(f"Write 12 short everyday questions that have nothing to do with health or medicine (e.g. sports, cooking techniques, geography, technology), each in every language: {json.dumps(LANGS)}. Return JSON: {{\"questions\": [{{lang_code: question, ...}}, ...]}}", max_tokens=4000)
    offq = [{"lang": lang, "q": q[lang], "split": "tune" if j % 2 == 0 else "test"} for j, q in enumerate(off.get("questions", [])) for lang in LANGS if isinstance(q.get(lang), str)]
    data = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "generator": get_settings().gemini_fast_model, "questions": qs, "off_topic": offq}
    OUT.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    partial.unlink(missing_ok=True)
    return data


def rank(qv: np.ndarray, emb: np.ndarray, chunks: list[dict]) -> tuple[list[str], list[float]]:
    scores = emb @ qv
    urls, best = [], []
    for i in np.argsort(-scores):
        u = chunks[int(i)]["url"]
        if u not in urls:
            urls.append(u)
            best.append(float(scores[i]))
        if len(urls) == 20:
            break
    return urls, best


def main(n_topics: int):
    chunks, emb, src = knowledge._kb()
    data = build_questions(n_topics)
    qs, off = data["questions"], data["off_topic"]
    qv = embeddings.embed_queries([q["q"] for q in qs])
    ov = embeddings.embed_queries([q["q"] for q in off])
    for q, v in zip(qs, qv):
        q["urls"], q["scores"] = rank(v, emb, chunks)
    for q, v in zip(off, ov):
        q["top_score"] = rank(v, emb, chunks)[1][0]

    # Choose the threshold on the tune split: maximise (relevant kept) − (off-topic kept).
    tune_rel = [q["scores"][0] for q in qs if q["split"] == "tune" and q["url"] in q["urls"][:4]]
    tune_off = [q["top_score"] for q in off if q["split"] == "tune"]
    cands = np.arange(0.70, 0.95, 0.005)
    best_t = max(cands, key=lambda t: np.mean([s >= t for s in tune_rel]) - np.mean([s >= t for s in tune_off]))

    def metrics(sub):
        r = {}
        for lang in LANGS:
            L = [q for q in sub if q["lang"] == lang]
            if not L:
                continue
            ranks = [q["urls"].index(q["url"]) + 1 if q["url"] in q["urls"] else 999 for q in L]
            r[lang] = {"n": len(L), "hit@1": float(np.mean([k == 1 for k in ranks])), "hit@4": float(np.mean([k <= 4 for k in ranks])), "mrr": float(np.mean([1 / k if k < 999 else 0 for k in ranks])),
                       "kept_at_threshold": float(np.mean([q["scores"][0] >= best_t for q in L]))}
        return r

    test = [q for q in qs if q["split"] == "test"]
    test_off = [q for q in off if q["split"] == "test"]
    res = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "embedding_model": src["embedding_model"],
        "kb_chunks": len(chunks),
        "questions": {"source": f"synthetic, generated by {data['generator']}", "topics": n_topics, "test_questions": len(test), "off_topic_test": len(test_off)},
        "threshold": round(float(best_t), 3),
        "test_metrics": metrics(test),
        "off_topic_false_retrieval_rate": float(np.mean([q["top_score"] >= best_t for q in test_off])) if test_off else None,
    }
    (OUT / "retrieval.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    lines = [
        "# Knowledge retrieval evaluation (MedlinePlus)",
        "",
        f"*Generated {res['generated_at']} by `ml/eval_retrieval.py`. Embeddings: {res['embedding_model']}; {res['kb_chunks']} passages.*",
        "",
        f"Test questions are **synthetic** ({res['questions']['source']}): one lay question per language for each of {n_topics} randomly sampled topics. "
        "The relevance threshold was chosen on half of the topics; results below are on the other half.",
        "",
        f"**Relevance threshold:** {res['threshold']} (passages scoring below it are not given to the chatbot).",
        "",
        "| Language | Questions | Correct topic ranked 1st | Correct topic in top 4 | MRR | Passed threshold |",
        "|---|---|---|---|---|---|",
        *[f"| {LANGS[k]} | {v['n']} | {v['hit@1']*100:.0f}% | {v['hit@4']*100:.0f}% | {v['mrr']:.2f} | {v['kept_at_threshold']*100:.0f}% |" for k, v in res["test_metrics"].items()],
        "",
        f"Off-topic (non-health) questions that still retrieved a passage above the threshold: {res['off_topic_false_retrieval_rate']*100:.0f}% of {len(test_off)}." if test_off else "",
        "",
        "Caveat: synthetic questions are cleaner than real user questions, and a topic counted as 'wrong' may still be relevant (MedlinePlus topics overlap).",
    ]
    (OUT / "retrieval.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
