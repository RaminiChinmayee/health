"""Evaluate (1) input-language identification and (2) speech-to-text, per language.

Data: Google FLEURS test split (CC BY 4.0) — read speech with transcripts in all 11 app languages.
  * Language ID: every test transcript per language → app's detect_language() (offline).
  * Speech-to-text: the first N test recordings per language (streamed from the audio archive,
    so only a few MB are downloaded) → the app's Gemini transcription, with the language hint the
    app would send. Also re-run with white noise added at 10 dB SNR (a noisier condition).
    Metrics: WER and CER (jiwer) after light normalisation (lower-case, punctuation removed).

Small samples: N recordings per language gives indicative, not definitive, numbers; the report
states N. Usage: python eval_speech_language.py [N]
"""
import csv
import io
import json
import re
import sys
import tarfile
import time
import unicodedata
import wave
from datetime import UTC, datetime
from pathlib import Path

import jiwer
import numpy as np
import requests
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.services import gemini  # noqa: E402
from app.services.knowledge import LANGUAGE_NAMES, detect_language  # noqa: E402

FLEURS = {"en": "en_us", "hi": "hi_in", "bn": "bn_in", "mr": "mr_in", "te": "te_in", "ta": "ta_in", "gu": "gu_in", "ur": "ur_pk", "kn": "kn_in", "or": "or_in", "ml": "ml_in"}
BASE = "https://huggingface.co/datasets/google/fleurs/resolve/main/data"
OUT = Path(__file__).resolve().parent / "eval"
CACHE = Path(__file__).resolve().parent / "data" / "raw" / "fleurs"


def transcripts(cfg: str) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{cfg}_test.tsv"
    if not f.exists():
        r = requests.get(f"{BASE}/{cfg}/test.tsv", timeout=120)
        r.raise_for_status()
        f.write_bytes(r.content)
    rows = []
    for line in f.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) >= 4:
            rows.append({"id": p[0], "file": p[1], "raw": p[2], "norm": p[3]})
    return rows


def first_audio(cfg: str, wanted: set[str], n: int) -> dict[str, bytes]:
    """Stream the test audio archive and keep the first n files whose names are in `wanted`."""
    out: dict[str, bytes] = {}
    cdir = CACHE / cfg
    if cdir.exists():
        for p in sorted(cdir.glob("*.wav"))[:n]:
            out[p.name] = p.read_bytes()
        if len(out) >= n:
            return out
    cdir.mkdir(parents=True, exist_ok=True)
    with requests.get(f"{BASE}/{cfg}/audio/test.tar.gz", stream=True, timeout=120) as r:
        r.raise_for_status()
        r.raw.decode_content = True
        with tarfile.open(fileobj=r.raw, mode="r|gz") as tar:
            for m in tar:
                name = Path(m.name).name
                if m.isfile() and name in wanted and name not in out:
                    data = tar.extractfile(m).read()
                    out[name] = data
                    (cdir / name).write_bytes(data)
                    if len(out) >= n:
                        break
    return out


def to_pcm16(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """Read any WAV (FLEURS uses 32-bit float) as int16 samples, mono."""
    rate, x = wavfile.read(io.BytesIO(wav_bytes))
    if x.ndim > 1:
        x = x.mean(axis=1)
    if x.dtype.kind == "f":
        x = np.clip(x, -1, 1) * 32767
    return x.astype(np.int16), rate


def write_wav(x: np.ndarray, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(x.astype(np.int16).tobytes())
    return buf.getvalue()


def add_noise(x: np.ndarray, rate: int, snr_db: float, seed: int) -> bytes:
    xf = x.astype(np.float64)
    noise = np.random.default_rng(seed).standard_normal(len(xf)) * np.sqrt(np.mean(xf**2) / 10 ** (snr_db / 10))
    return write_wav(np.clip(xf + noise, -32768, 32767), rate)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s.lower())
    s = "".join(ch if not unicodedata.category(ch).startswith("P") else " " for ch in s)
    s = s.replace("।", " ").replace("॥", " ")
    return re.sub(r"\s+", " ", s).strip()


MODEL = None  # set in main()


class DailyQuotaExhausted(RuntimeError):
    pass


def transcribe_with_retry(data: bytes, lang: str) -> dict:
    for attempt in range(6):
        try:
            return gemini._transcribe_with(MODEL, data, "audio/wav", lang, LANGUAGE_NAMES)
        except gemini.GeminiRateLimited as e:
            if (e.retry_after or 0) > 300:  # a daily quota, not a per-minute one
                raise DailyQuotaExhausted(str(e))
            wait = min(65, (e.retry_after or 30) + 2)
            print(f"    rate limited, waiting {wait}s", flush=True)
            time.sleep(wait)
        except gemini.GeminiUnavailable as e:
            print(f"    unavailable ({e}); retrying", flush=True)
            time.sleep(10)
    raise RuntimeError("transcription failed repeatedly")


def main(n: int, model: str):
    global MODEL
    MODEL = model
    OUT.mkdir(exist_ok=True)
    lid, stt = {}, {}
    examples, all_pairs = [], []
    for lang, cfg in FLEURS.items():
        rows = transcripts(cfg)
        preds = [detect_language(r["raw"])[0] for r in rows]
        lid[lang] = {"n": len(rows), "accuracy": float(np.mean([p == lang for p in preds])), "confusions": {k: preds.count(k) for k in set(preds) if k != lang}}
        print(f"{lang}: LID {lid[lang]['accuracy']:.3f} on {len(rows)} sentences", flush=True)

        by_file = {r["file"]: r for r in rows}
        audio = first_audio(cfg, set(by_file), n)
        res = {"clean": {"refs": [], "hyps": []}, "noisy_10db": {"refs": [], "hyps": []}}
        for i, (fname, data) in enumerate(sorted(audio.items())):
            ref = norm(by_file[fname]["raw"])
            pcm, rate = to_pcm16(data)  # the app sends 16-bit PCM WAV
            for cond, payload in (("clean", write_wav(pcm, rate)), ("noisy_10db", add_noise(pcm, rate, 10, i))):
                out = transcribe_with_retry(payload, lang)
                res[cond]["refs"].append(ref)
                res[cond]["hyps"].append(norm(out["text"]))
                all_pairs.append({"lang": lang, "condition": cond, "file": fname, "reference": by_file[fname]["raw"], "hypothesis": out["text"]})
                if cond == "clean" and i < 2:
                    examples.append({"lang": lang, "reference": by_file[fname]["raw"], "hypothesis": out["text"], "detected": out["language"]})
        stt[lang] = {}
        for cond, d in res.items():
            refs, hyps = d["refs"], [h if h else "<empty>" for h in d["hyps"]]
            stt[lang][cond] = {"n": len(refs), "wer": float(jiwer.wer(refs, hyps)), "cer": float(jiwer.cer(refs, hyps))}
        print(f"   STT clean WER {stt[lang]['clean']['wer']:.3f} CER {stt[lang]['clean']['cer']:.3f} | noisy WER {stt[lang]['noisy_10db']['wer']:.3f} CER {stt[lang]['noisy_10db']['cer']:.3f} (n={n})", flush=True)

    result = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": {"name": "Google FLEURS (test split)", "url": "https://huggingface.co/datasets/google/fleurs", "license": "CC BY 4.0", "citation": "Conneau A, et al. FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech. IEEE SLT 2022."},
        "stt_model": MODEL,
        "recordings_per_language": n,
        "language_identification": lid,
        "speech_to_text": stt,
        "examples": examples,
        "all_transcripts": all_pairs,
    }
    (OUT / "speech_language.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    lines = [
        "# Speech-to-text and language identification evaluation",
        "",
        f"*Generated {result['generated_at']} by `ml/eval_speech_language.py`. Dataset: {result['dataset']['name']} ({result['dataset']['license']}).*",
        "",
        "## Input-language identification (app's offline detector)",
        "Every FLEURS test transcript per language, classified by `detect_language()`.",
        "",
        "| Language | Sentences | Accuracy | Most common confusions |",
        "|---|---|---|---|",
        *[f"| {LANGUAGE_NAMES[k]} | {v['n']} | {v['accuracy']*100:.1f}% | {', '.join(f'{c}: {m}' for c, m in sorted(v['confusions'].items(), key=lambda x: -x[1])[:3]) or '—'} |" for k, v in lid.items()],
        "",
        f"## Speech-to-text ({result['stt_model']})",
        f"First {n} FLEURS test recordings per language, transcribed with the app's language hint. Noisy = white noise added at 10 dB SNR. Lower is better. **Small samples: indicative only.**",
        "",
        "| Language | WER (clean) | CER (clean) | WER (noisy) | CER (noisy) |",
        "|---|---|---|---|---|",
        *[f"| {LANGUAGE_NAMES[k]} | {v['clean']['wer']*100:.1f}% | {v['clean']['cer']*100:.1f}% | {v['noisy_10db']['wer']*100:.1f}% | {v['noisy_10db']['cer']*100:.1f}% |" for k, v in stt.items()],
        "",
        "WER is harsh for agglutinative languages (Telugu, Tamil, Kannada, Malayalam) where one spelling or suffix difference makes a whole long word wrong; CER is more informative there.",
    ]
    (OUT / "speech_language.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10, sys.argv[2] if len(sys.argv) > 2 else "gemini-3.5-flash-lite")
