"""Skin-lesion image analysis: validation, safety gates, and classification.

Pipeline for an uploaded image:
  1. Decode & validate (format, size, dimensions), fix orientation, strip metadata.
  2. Gate A — vision-model check (Gemini): is this a close-up of a skin spot / lesion? If the
     model says no, the image is NOT classified. If the check is unavailable, gate B still applies.
  3. Gate B — out-of-distribution check: features far from every training image are rejected.
  4. Classification with the fine-tuned EfficientNet-B0 (temperature-calibrated, flip TTA).
Never fabricates a result: any failure is returned as an explicit status.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings
from app.services import gemini

log = logging.getLogger("healthai.skin")
MAX_BYTES = 8 * 1024 * 1024
MIN_SIDE = 100
_lock = threading.Lock()


class ImageRejected(ValueError):
    def __init__(self, code: str, **details):
        super().__init__(code)
        self.code = code
        self.details = details


class SkinModelUnavailable(RuntimeError):
    pass


def _dir() -> Path | None:
    d = get_settings().model_dir / "skin"
    if not d.exists():
        return None
    versions = sorted((p for p in d.iterdir() if (p / "model.pt").exists() and (p / "card.json").exists()), key=lambda p: tuple(int(x) for x in p.name.split(".")))
    return versions[-1] if versions else None


def available() -> bool:
    return _dir() is not None


@lru_cache
def load() -> tuple:
    import torch
    import torch.nn as nn
    from torchvision.models import efficientnet_b0

    d = _dir()
    if d is None:
        raise SkinModelUnavailable("skin model not trained")
    with _lock:
        card = json.loads((d / "card.json").read_text())
        m = efficientnet_b0(weights=None)
        m.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(1280, len(card["classes"])))
        m.load_state_dict(torch.load(d / "model.pt", map_location="cpu", weights_only=True))
        m.eval()
        bank = np.load(d / "feature_bank.npy").astype(np.float32)
        bank /= np.linalg.norm(bank, axis=1, keepdims=True)
    return m, card, bank


def card() -> dict | None:
    try:
        return load()[1]
    except SkinModelUnavailable:
        return None


def validate_and_normalise(data: bytes) -> tuple[Image.Image, bytes]:
    """Return (RGB image, re-encoded WEBP bytes without metadata)."""
    if len(data) > MAX_BYTES:
        raise ImageRejected("file_too_large", max_bytes=MAX_BYTES)
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in {"JPEG", "PNG", "WEBP"}:
            raise ImageRejected("unsupported_image_type")
        img.verify()
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageRejected("unsupported_image_type")
    if min(img.size) < MIN_SIDE:
        raise ImageRejected("image_too_small", min_side=MIN_SIDE)
    stored = img.copy()
    stored.thumbnail((1600, 1600))
    buf = io.BytesIO()
    stored.save(buf, "WEBP", quality=88)  # re-encoding drops EXIF/GPS and any embedded payload
    return img, buf.getvalue()


def vision_gate(webp: bytes) -> dict:
    """Ask a vision model whether the photo shows a skin spot/lesion close-up."""
    prompt = (
        "You screen images before a skin-lesion classifier. Look at the image and answer JSON: "
        '{"skin_lesion_closeup": true|false, "description": "<max 15 words, English, neutral>"}. '
        "skin_lesion_closeup is true only if the image mainly shows a close-up of human skin with a mole, spot, "
        "growth, or lesion (dermatoscopic or ordinary photo). It is false for faces/whole bodies, rashes covering large areas, "
        "objects, documents, screenshots, animals, food, or anything else."
    )
    contents = [{"role": "user", "parts": [{"inlineData": {"mimeType": "image/webp", "data": base64.b64encode(webp).decode()}}, {"text": prompt}]}]
    try:
        r = gemini.generate(get_settings().gemini_fast_model, contents, json_mode=True, temperature=0, max_tokens=200, thinking="minimal", timeout=20)
        out = json.loads(r.text)
        return {"checked": True, "skin_lesion_closeup": bool(out.get("skin_lesion_closeup")), "description": str(out.get("description", ""))[:200]}
    except (gemini.GeminiError, ValueError) as e:
        log.warning("vision gate unavailable: %s", e)
        return {"checked": False, "reason": getattr(e, "code", "invalid_response")}


def classify(img: Image.Image) -> dict:
    import torch

    model, c, bank = load()
    size, crop = c["input"]["resize"], c["input"]["size"]
    x = np.asarray(img.resize((size, size), Image.BICUBIC), dtype=np.float32) / 255.0
    off = (size - crop) // 2
    x = x[off : off + crop, off : off + crop]
    x = (x - np.array(c["input"]["mean"], dtype=np.float32)) / np.array(c["input"]["std"], dtype=np.float32)
    t = torch.from_numpy(x).permute(2, 0, 1)[None]
    with torch.no_grad():
        f = model.avgpool(model.features(t)).flatten(1)
        logits = model.classifier(f)
        logits = (logits + model.classifier(model.avgpool(model.features(torch.flip(t, dims=[3]))).flatten(1))) / 2
    feat = f.numpy()[0]
    feat /= np.linalg.norm(feat)
    dist = float(1 - np.sort(bank @ feat)[-5:].mean())
    z = logits.numpy()[0] / c["temperature"]
    p = np.exp(z - z.max())
    p /= p.sum()
    probs = {cls: round(float(v), 4) for cls, v in zip(c["classes"], p)}
    top = max(probs, key=probs.get)
    return {"probabilities": probs, "predicted_class": top, "probability": probs[top], "ood_distance": round(dist, 4), "ood_threshold": c["ood"]["threshold"]}


def analyse(img: Image.Image, webp: bytes) -> dict:
    """Run gates and classifier. Returns a dict with an explicit status."""
    if not available():
        raise SkinModelUnavailable("skin model not trained")
    _, c, _ = load()
    gate = vision_gate(webp) if get_settings().gemini_api_key else {"checked": False, "reason": "llm_not_configured"}
    base = {"model_key": "skin", "model_version": c["version"], "gate": gate}
    if gate.get("checked") and not gate.get("skin_lesion_closeup"):
        return {**base, "status": "rejected_not_skin"}
    res = classify(img)
    if res["ood_distance"] > res["ood_threshold"]:
        return {**base, "status": "rejected_out_of_distribution", "ood_distance": res["ood_distance"]}
    concern = res["predicted_class"] in c["concern_classes"] or sum(res["probabilities"][k] for k in c["concern_classes"]) >= 0.3
    return {**base, "status": "ok", **res, "safety": {"see_dermatologist": True, "prompt_review": concern, "not_a_diagnosis": True}}
