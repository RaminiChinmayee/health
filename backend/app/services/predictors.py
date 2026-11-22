"""Model registry and inference for the prediction modules.

Explanations are "what-if" contributions: how much the estimate changes when one input is
replaced by a typical value from the training data (median / most common). They are simple,
model-agnostic and honest about what they mean; they are not SHAP values.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.config import get_settings

BINARY_TYPES = ("diabetes", "diabetes_symptoms", "heart", "kidney", "lung", "parkinsons")
ALL_TYPES = ("symptoms", *BINARY_TYPES)


class ModelUnavailable(RuntimeError):
    pass


class InputError(ValueError):
    def __init__(self, fields: dict[str, str]):
        super().__init__("invalid inputs")
        self.fields = fields


@dataclass
class LoadedModel:
    key: str
    version: str
    model: Any
    card: dict


def _latest_version(d: Path) -> str:
    versions = [p.name for p in d.iterdir() if (p / "card.json").exists() and (p / "model.joblib").exists()]
    if not versions:
        raise ModelUnavailable(d.name)
    return max(versions, key=lambda v: tuple(int(x) for x in v.split(".")))


@lru_cache(maxsize=16)
def load_model(key: str) -> LoadedModel:
    d = get_settings().model_dir / key
    if not d.exists():
        raise ModelUnavailable(key)
    v = _latest_version(d)
    card = json.loads((d / v / "card.json").read_text())
    if card.get("deployable") is False:
        raise ModelUnavailable(key)
    return LoadedModel(key=key, version=v, model=joblib.load(d / v / "model.joblib"), card=card)


def public_card(card: dict) -> dict:
    """The parts of a model card shown to users (data provenance, metrics, limitations)."""
    ev = card.get("evaluation", {})
    out = {
        "key": card["key"],
        "version": card["version"],
        "title": card["title"],
        "algorithm": card.get("algorithm"),
        "trained_at": card.get("trained_at"),
        "dataset": {k: card["dataset"].get(k) for k in ("name", "source", "citation", "license", "population", "rows_after_dedup", "duplicates_removed", "unique_patterns")},
        "limitations": card.get("limitations", []),
        "protocol": ev.get("protocol"),
        "display": card.get("display", "probability"),
        "notes": card.get("notes", []),
    }
    if card.get("task") == "binary_classification":
        t = ev["test"]
        out["metrics"] = {
            "test": {k: t.get(k) for k in ("n", "accuracy", "recall_sensitivity", "specificity", "precision", "roc_auc", "brier")},
            "ci95": t.get("ci95", {}),
            "cv": ev.get("cross_validation_all_data"),
            "external": ev.get("external_validation"),
        }
        out["features"] = card["features"]
        out["positive_label"] = card.get("positive_label")
    else:
        out["metrics"] = {"selected": ev.get("selected")}
    return out


# ------------------------------------------------------------------ binary models
def _validate_binary(card: dict, raw: dict[str, Any]) -> tuple[dict[str, float | None], list[str]]:
    errors: dict[str, str] = {}
    clean: dict[str, float | None] = {}
    missing_optional: list[str] = []
    for f in card["features"]:
        name = f["name"]
        v = raw.get(name)
        if v is None or v == "":
            if f.get("required", True):
                errors[name] = "required"
            else:
                clean[name] = None
                missing_optional.append(name)
            continue
        try:
            num = float(v)
        except (TypeError, ValueError):
            errors[name] = "value_error"
            continue
        if not math.isfinite(num):
            errors[name] = "value_error"
        elif f["kind"] in ("choice", "boolean") and num not in [float(o) for o in f["options"]]:
            errors[name] = "literal_error"
        elif f["kind"] == "number" and (("min" in f and num < f["min"]) or ("max" in f and num > f["max"])):
            errors[name] = "out_of_range"
        else:
            clean[name] = num
    unknown = set(raw) - {f["name"] for f in card["features"]}
    for u in unknown:
        errors[u] = "unknown_field"
    if errors:
        raise InputError(errors)
    return clean, missing_optional


def risk_band(p: float, display: str = "probability") -> str:
    if display == "similarity":
        # Balanced, uncalibrated model: a similarity judgement, never a risk level.
        return "resembles_healthy" if p < 0.35 else "inconclusive" if p < 0.65 else "resembles_condition"
    return "lower" if p < 0.2 else "moderate" if p < 0.5 else "higher"


def predict_binary(key: str, raw: dict[str, Any]) -> dict:
    m = load_model(key)
    card = m.card
    values, missing = _validate_binary(card, raw)
    cols = [f["name"] for f in card["features"]]
    row = pd.DataFrame([[values[c] if values[c] is not None else np.nan for c in cols]], columns=cols)
    p = float(m.model.predict_proba(row)[0, 1])

    # What-if contributions against typical (reference) values, for inputs the user provided.
    ref = card["reference_values"]
    contribs = []
    variants = []
    names = []
    for c in cols:
        if values[c] is None or values[c] == ref[c]:
            continue
        alt = row.copy()
        alt[c] = ref[c]
        variants.append(alt)
        names.append(c)
    if variants:
        alt_p = m.model.predict_proba(pd.concat(variants, ignore_index=True))[:, 1]
        for c, ap in zip(names, alt_p):
            contribs.append({"feature": c, "value": values[c], "typical_value": ref[c], "effect": round(p - float(ap), 4)})
    contribs.sort(key=lambda d: -abs(d["effect"]))

    display = card.get("display", "probability")
    band = risk_band(p, display)
    warnings = []
    if missing:
        warnings.append({"code": "missing_optional_inputs", "fields": missing})
    if band in ("higher", "resembles_condition", "inconclusive") or (display == "probability" and p >= 0.5):
        warnings.append({"code": "consult_doctor"})
    if display == "similarity":
        warnings.append({"code": "not_a_risk_estimate"})
    return {
        "model_key": key,
        "model_version": m.version,
        "display": display,
        "probability": round(p, 4),
        "risk_band": band,
        "contributions": contribs[:6],
        "inputs": values,
        "safety": {"warnings": warnings, "disclaimer": "not_a_diagnosis"},
    }


# ------------------------------------------------------------------ symptom checker
def _rank_proba(model, X: np.ndarray, ranking: dict | None) -> np.ndarray:
    """Same ranking as ml/train_symptoms.py:rank_proba (see the model card's "ranking")."""
    if not ranking:
        return model.predict_proba(X)
    lp = model.feature_log_prob_
    ln = np.log1p(-np.exp(lp))
    n = X.sum(1, keepdims=True)
    w = np.clip((n - 1) / ranking["absent_ramp"], 0, 1)
    s = X @ np.minimum(lp, np.log(ranking.get("pos_cap", 1.0))).T + w * ((1 - X) @ ln.T)
    s = s + np.log(np.where(np.isin(model.classes_, ranking["common_in_india"]), ranking["common_weight"], 1.0))
    s = s - s.max(1, keepdims=True)
    e = np.exp(s)
    return e / e.sum(1, keepdims=True)


def predict_symptoms(selected: list[str]) -> dict:
    m = load_model("symptoms")
    card = m.card
    bundle = m.model
    model, vocab = bundle["model"], bundle["symptoms"]
    index = {s: i for i, s in enumerate(vocab)}
    sel = sorted(set(selected))
    bad = [s for s in sel if s not in index]
    if bad:
        raise InputError({"symptoms": "unknown_symptom"})
    if not sel:
        raise InputError({"symptoms": "required"})
    x = np.zeros((1, len(vocab)), dtype=np.int8)
    for s in sel:
        x[0, index[s]] = 1
    ranking = card.get("ranking")
    proba = _rank_proba(model, x, ranking)[0]
    # Exact ties (e.g. one symptom alone) are ordered by the model's raw probability, only as a
    # stable tie-break. Show the top 5, extended to up to 10 when more conditions fit as well.
    raw = (x @ model.feature_log_prob_.T)[0] if ranking else proba
    ranked = np.lexsort((-raw, -np.round(proba, 6)))
    order = [i for j, i in enumerate(ranked[:10]) if j < 5 or proba[i] >= 0.5 * proba[ranked[0]]]
    n_tied = int(np.sum(np.isclose(proba, proba[ranked[0]], rtol=0.02)))
    classes = model.classes_
    matches = [{"disease": str(classes[i]), "score": round(float(proba[i]), 4)} for i in order]
    top = matches[0]["disease"]
    top_i = list(classes).index(top)

    # Contribution of each reported symptom to the top match (drop when removed).
    contribs = []
    if len(sel) > 1:
        variants = np.repeat(x, len(sel), axis=0)
        for r, s in enumerate(sel):
            variants[r, index[s]] = 0
        alt = _rank_proba(model, variants, ranking)[:, top_i]
        contribs = sorted(
            [{"feature": s, "effect": round(float(proba[top_i] - a), 4)} for s, a in zip(sel, alt)],
            key=lambda d: -d["effect"],
        )[:6]

    red_flags = sorted(set(sel) & set(card["red_flag_symptoms"]))
    urgent = [mm["disease"] for mm in matches[:3] if mm["disease"] in card["urgent_diseases"] and mm["score"] >= 0.1]
    warnings = []
    if red_flags:
        warnings.append({"code": "red_flag_symptoms", "symptoms": red_flags})
    if urgent:
        warnings.append({"code": "urgent_condition_possible", "diseases": urgent})
    if len(sel) < 3:
        warnings.append({"code": "few_symptoms"})
    if n_tied >= 3:
        warnings.append({"code": "equal_matches", "count": n_tied})
    typical = card["typical_symptoms"].get(top, [])
    return {
        "model_key": "symptoms",
        "model_version": m.version,
        "matches": matches,
        "top": top,
        "score": matches[0]["score"],
        "contributions": contribs,
        "inputs": {"symptoms": sel},
        "typical_not_reported": [s for s in typical if s not in sel][:8],
        "safety": {"warnings": warnings, "disclaimer": "not_a_diagnosis", "emergency": bool(red_flags or urgent)},
    }


def symptom_vocabulary() -> dict:
    card = load_model("symptoms").card
    return {"symptoms": card["symptoms"], "diseases": card["diseases"], "red_flag_symptoms": card["red_flag_symptoms"]}
