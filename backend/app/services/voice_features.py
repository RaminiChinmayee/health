"""Measure the Parkinson's model's 15 voice features from a sustained-vowel recording with Praat
(via parselmouth) — the same "Voice report" measures used by the training dataset (Sakar et al.).

Quality gates refuse recordings that are too short, not a steady vowel, or whose measures fall
outside the range seen in the training data, rather than producing an unreliable result.
"""
from __future__ import annotations

import io
import re
import wave

import numpy as np
import parselmouth
from parselmouth.praat import call

PITCH_FLOOR, PITCH_CEILING = 75, 600

# Voice-report label → (feature name, scale). Percent values are converted to fractions.
REPORT = {
    "Jitter (local)": ("jitter_local", 0.01),
    "Jitter (local, absolute)": ("jitter_local_abs", 1.0),
    "Jitter (rap)": ("jitter_rap", 0.01),
    "Jitter (ppq5)": ("jitter_ppq5", 0.01),
    "Jitter (ddp)": ("jitter_ddp", 0.01),
    "Shimmer (local)": ("shimmer_local", 0.01),
    "Shimmer (local, dB)": ("shimmer_local_db", 1.0),
    "Shimmer (apq3)": ("shimmer_apq3", 0.01),
    "Shimmer (apq5)": ("shimmer_apq5", 0.01),
    "Shimmer (apq11)": ("shimmer_apq11", 0.01),
    "Shimmer (dda)": ("shimmer_dda", 0.01),
    "Mean noise-to-harmonics ratio": ("nhr", 1.0),
    "Mean harmonics-to-noise ratio": ("hnr", 1.0),
    "Mean period": ("period_mean", 1.0),
    "Standard deviation of period": ("period_sd", 1.0),
}


class RecordingRejected(ValueError):
    def __init__(self, code: str, **details):
        super().__init__(code)
        self.code = code
        self.details = details


def _read_wav(data: bytes) -> tuple[np.ndarray, int]:
    try:
        with wave.open(io.BytesIO(data)) as w:
            rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError):
        raise RecordingRejected("unsupported_audio_type")
    if width != 2:
        raise RecordingRejected("unsupported_audio_type")
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, rate


def _num(s: str) -> float:
    s = s.strip().split()[0].rstrip("%")
    return float(s)


def measure(data: bytes) -> dict:
    x, rate = _read_wav(data)
    dur = len(x) / rate
    if dur < 2.0:
        raise RecordingRejected("recording_too_short", min_seconds=2)
    if dur > 15.0:
        raise RecordingRejected("recording_too_long", max_seconds=15)
    if np.max(np.abs(x)) < 0.02:
        raise RecordingRejected("recording_too_quiet")
    # Trim 0.5 s at each end (onset/offset are not steady phonation).
    trim = int(0.5 * rate)
    snd = parselmouth.Sound(x[trim:-trim] if len(x) > 3 * trim else x, sampling_frequency=rate)
    pitch = snd.to_pitch_cc(pitch_floor=PITCH_FLOOR, pitch_ceiling=PITCH_CEILING)
    pp = call([snd, pitch], "To PointProcess (cc)")
    report = call([snd, pitch, pp], "Voice report", 0, 0, PITCH_FLOOR, PITCH_CEILING, 1.3, 1.6, 0.03, 0.45)

    fields: dict[str, float] = {}
    for line in report.splitlines():
        if ":" not in line:
            continue
        label, value = (p.strip() for p in line.split(":", 1))
        if label in REPORT:
            name, scale = REPORT[label]
            try:
                fields[name] = _num(value) * scale
            except ValueError:
                pass  # "--undefined--"
    unvoiced = re.search(r"Fraction of locally unvoiced frames: ([\d.]+)%?", report)
    unvoiced_frac = float(unvoiced.group(1)) / (100 if "%" in unvoiced.group(0) else 1) if unvoiced else 1.0
    pulses = re.search(r"Number of pulses: (\d+)", report)
    n_pulses = int(pulses.group(1)) if pulses else 0
    if n_pulses < 100 or unvoiced_frac > 0.4 or len(fields) < len(REPORT):
        raise RecordingRejected("not_a_sustained_vowel", unvoiced_fraction=round(unvoiced_frac, 3), pulses=n_pulses)
    return {"features": fields, "quality": {"duration_seconds": round(dur, 2), "unvoiced_fraction": round(unvoiced_frac, 3), "pulses": n_pulses, "sample_rate": rate}}


def check_range(features: dict, card_features: list[dict]) -> list[str]:
    """Names of features outside the range seen in training (the model would be extrapolating)."""
    out = []
    for f in card_features:
        v = features.get(f["name"])
        if v is None or ("min" in f and v < f["min"]) or ("max" in f and v > f["max"]):
            out.append(f["name"])
    return out
