"""Shared training / evaluation protocol for the tabular prediction models.

Protocol (binary models):
  1. Remove exact duplicate rows (prevents train/test leakage).
  2. Split into development (75%) and held-out test (25%), stratified by label — or grouped
     by subject when several rows belong to one person (Parkinson's).
  3. Choose among candidate model families with repeated cross-validation on the development
     set only (ROC-AUC). The test set is not touched during selection.
  4. Calibrate probabilities of the chosen model (Platt / sigmoid, 5-fold) on the dev set.
  5. Evaluate once on the held-out test set, with bootstrap 95% confidence intervals.
  6. Save the exact evaluated model, plus a model card with data provenance and metrics.

Nothing here invents numbers: every metric in a card is computed by this code from data.
"""
from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    GridSearchCV,
    GroupKFold,
    GroupShuffleSplit,
    RepeatedStratifiedKFold,
    StratifiedGroupKFold,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
ARTIFACTS = ROOT / "artifacts"
SEED = 42


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ feature specs
@dataclass
class Feature:
    """Describes one model input. Shared with the backend (validation) and frontend (forms)."""

    name: str
    kind: str  # "number" | "choice" | "boolean"
    required: bool = True
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = None
    options: list[Any] | None = None  # for "choice": allowed encoded values
    # Optional auto-fill source from the user's health profile ("age", "bmi", "sex").
    profile_source: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


# ------------------------------------------------------------------ candidates
def binary_candidates(balanced: bool = False) -> dict[str, tuple[Pipeline, dict]]:
    cw = "balanced" if balanced else None
    return {
        "logistic_regression": (
            Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=5000, class_weight=cw))]),
            {"clf__C": [0.01, 0.1, 1.0, 10.0]},
        ),
        "random_forest": (
            Pipeline([("impute", SimpleImputer(strategy="median")), ("clf", RandomForestClassifier(n_estimators=400, random_state=SEED, n_jobs=-1, class_weight=cw))]),
            {"clf__max_depth": [3, 5, None], "clf__min_samples_leaf": [1, 5]},
        ),
        "gradient_boosting": (
            # Handles missing values natively.
            Pipeline([("clf", HistGradientBoostingClassifier(random_state=SEED, class_weight=cw))]),
            {"clf__learning_rate": [0.03, 0.1], "clf__max_depth": [2, 3], "clf__max_iter": [100, 300]},
        ),
    }


# ------------------------------------------------------------------ metrics
def binary_metrics(y_true: np.ndarray, proba: np.ndarray, threshold: float = 0.5) -> dict:
    pred = (proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "n": int(len(y_true)),
        "positives": int(y_true.sum()),
        "accuracy": accuracy_score(y_true, pred),
        "precision": precision_score(y_true, pred, zero_division=0),
        "recall_sensitivity": recall_score(y_true, pred, zero_division=0),
        "specificity": tn / (tn + fp) if (tn + fp) else None,
        "f1": f1_score(y_true, pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, proba) if len(np.unique(y_true)) == 2 else None,
        "pr_auc": average_precision_score(y_true, proba) if len(np.unique(y_true)) == 2 else None,
        "brier": brier_score_loss(y_true, proba),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "threshold": threshold,
    }


def bootstrap_ci(y_true: np.ndarray, proba: np.ndarray, n: int = 1000, threshold: float = 0.5) -> dict:
    rng = np.random.default_rng(SEED)
    stats: dict[str, list[float]] = {"accuracy": [], "roc_auc": [], "recall_sensitivity": [], "specificity": []}
    idx = np.arange(len(y_true))
    for _ in range(n):
        s = rng.choice(idx, size=len(idx), replace=True)
        yt, pp = y_true[s], proba[s]
        if len(np.unique(yt)) < 2:
            continue
        m = binary_metrics(yt, pp, threshold)
        for k in stats:
            if m[k] is not None:
                stats[k].append(m[k])
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in stats.items() if v}


def calibration_table(y_true: np.ndarray, proba: np.ndarray, bins: int = 5) -> list[dict]:
    frac_pos, mean_pred = calibration_curve(y_true, proba, n_bins=bins, strategy="quantile")
    return [{"mean_predicted": float(p), "observed_rate": float(o)} for p, o in zip(mean_pred, frac_pos)]


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if np.isnan(obj) else round(float(obj), 4)
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


# ------------------------------------------------------------------ training
@dataclass
class BinaryTask:
    key: str  # e.g. "heart"
    version: str
    title: str
    X: pd.DataFrame
    y: pd.Series
    features: list[Feature]
    dataset: dict  # provenance: name, source url, citation, license, files+sha256, population
    limitations: list[str]
    positive_label: str
    groups: pd.Series | None = None  # subject ids when rows aren't independent
    external: dict[str, tuple[pd.DataFrame, pd.Series]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # Class-balanced training. With calibrate=False the output then reflects *equal* class
    # priors (a similarity score), not the dataset's prevalence.
    balanced: bool = False
    calibrate: bool = True
    display: str = "probability"  # "probability" | "similarity"


def train_binary(task: BinaryTask) -> dict:
    X, y, groups = task.X.copy(), task.y.astype(int).copy(), task.groups
    cols = [f.name for f in task.features]
    X = X[cols]

    # 1. de-duplicate (feature values + label); with groups, only within identical subject rows
    before = len(X)
    key = pd.concat([X, y.rename("__y")], axis=1)
    if groups is not None:
        key["__g"] = groups.values
    keep = ~key.duplicated()
    X, y = X[keep.values], y[keep.values]
    if groups is not None:
        groups = groups[keep.values]
    dupes = before - len(X)

    # 2. split
    if groups is None:
        X_dev, X_test, y_dev, y_test = train_test_split(X, y, test_size=0.25, stratify=y, random_state=SEED)
        cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=SEED)
        g_dev = None
        split_desc = "stratified random 75/25 split"
    else:
        gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED)
        dev_idx, test_idx = next(gss.split(X, y, groups))
        X_dev, X_test, y_dev, y_test = X.iloc[dev_idx], X.iloc[test_idx], y.iloc[dev_idx], y.iloc[test_idx]
        g_dev = groups.iloc[dev_idx]
        cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
        split_desc = (
            f"subject-level split: {groups.iloc[dev_idx].nunique()} subjects for development, "
            f"{groups.iloc[test_idx].nunique()} different subjects for testing"
        )

    # 3. model selection on dev only
    selection = {}
    best_name, best_score, best_est = None, -1.0, None
    for name, (pipe, grid) in binary_candidates(task.balanced).items():
        gs = GridSearchCV(pipe, grid, scoring="roc_auc", cv=cv, n_jobs=-1)
        gs.fit(X_dev, y_dev, groups=g_dev)
        selection[name] = {"cv_roc_auc": gs.best_score_, "best_params": gs.best_params_}
        if gs.best_score_ > best_score:
            best_name, best_score, best_est = name, gs.best_score_, gs.best_estimator_

    # 4. calibrate
    if task.calibrate:
        cal_cv = list(cv.split(X_dev, y_dev, g_dev))[:5] if groups is not None else 5
        model = CalibratedClassifierCV(clone(best_est), method="sigmoid", cv=cal_cv)
    else:
        model = clone(best_est)
    model.fit(X_dev, y_dev)

    # 5. evaluate on held-out test
    p_test = model.predict_proba(X_test)[:, 1]
    test = binary_metrics(y_test.values, p_test)
    test["ci95"] = bootstrap_ci(y_test.values, p_test)
    test["calibration"] = calibration_table(y_test.values, p_test)

    # grouped/whole-data CV estimate (more stable than one small test split)
    cv_scores = []
    full_cv = (
        GroupKFold(n_splits=5).split(X, y, groups)
        if groups is not None
        else RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=SEED).split(X, y)
    )
    for tr, te in full_cv:
        m = (CalibratedClassifierCV(clone(best_est), method="sigmoid", cv=3) if task.calibrate else clone(best_est)).fit(X.iloc[tr], y.iloc[tr])
        pp = m.predict_proba(X.iloc[te])[:, 1]
        if len(np.unique(y.iloc[te])) == 2:
            cv_scores.append(binary_metrics(y.iloc[te].values, pp))
    cv_summary = {
        k: {"mean": float(np.mean([s[k] for s in cv_scores])), "std": float(np.std([s[k] for s in cv_scores]))}
        for k in ("accuracy", "roc_auc", "recall_sensitivity", "specificity", "f1")
    }

    external = {}
    for name, (Xe, ye) in task.external.items():
        pe = model.predict_proba(Xe[cols])[:, 1]
        external[name] = binary_metrics(ye.astype(int).values, pe)

    imp = permutation_importance(model, X_test, y_test, scoring="roc_auc", n_repeats=20, random_state=SEED)
    importance = sorted(
        [{"feature": c, "importance": float(m), "std": float(s)} for c, m, s in zip(cols, imp.importances_mean, imp.importances_std)],
        key=lambda d: -d["importance"],
    )

    # Reference values for "what-if" contributions at inference time.
    reference = {}
    for f in task.features:
        col = X_dev[f.name].dropna()
        reference[f.name] = float(col.median()) if f.kind == "number" else float(col.mode().iloc[0])

    card = _clean(
        {
            "key": task.key,
            "version": task.version,
            "title": task.title,
            "task": "binary_classification",
            "positive_label": task.positive_label,
            "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "algorithm": best_name,
            "calibration": "Platt scaling (sigmoid), 5-fold, fit on development data" if task.calibrate else "None — class-balanced model; outputs assume equal numbers of positive and negative cases",
            "display": task.display,
            "features": [f.to_dict() for f in task.features],
            "reference_values": reference,
            "dataset": {**task.dataset, "rows_after_dedup": len(X), "duplicates_removed": dupes},
            "evaluation": {
                "protocol": split_desc,
                "dev_rows": len(X_dev),
                "test_rows": len(X_test),
                "model_selection_cv": selection,
                "test": test,
                "cross_validation_all_data": cv_summary,
                "external_validation": external,
                "permutation_importance_test": importance,
            },
            "limitations": task.limitations,
            "notes": task.notes,
            "environment": {"python": platform.python_version(), "sklearn": sklearn.__version__},
        }
    )
    out = ARTIFACTS / task.key / task.version
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out / "model.joblib", compress=3)
    (out / "card.json").write_text(json.dumps(card, indent=2, ensure_ascii=False))
    (out / "report.md").write_text(render_binary_report(card))
    return card


def fmt(v, pct=True):
    if v is None:
        return "n/a"
    return f"{v * 100:.1f}%" if pct else f"{v:.3f}"


def render_binary_report(c: dict) -> str:
    e = c["evaluation"]
    t = e["test"]
    ci = t.get("ci95", {})
    cm = t["confusion_matrix"]
    lines = [
        f"# {c['title']} — model report (v{c['version']})",
        "",
        f"*Generated {c['trained_at']} by `ml/train_{c['key']}.py`. All numbers are computed from data by the training script.*",
        "",
        "## Data",
        f"- **Dataset:** {c['dataset']['name']} — {c['dataset']['source']}",
        f"- **Population:** {c['dataset'].get('population', 'n/a')}",
        f"- **Licence:** {c['dataset'].get('license', 'see source')}",
        f"- Rows after removing {c['dataset']['duplicates_removed']} exact duplicates: {c['dataset']['rows_after_dedup']}",
        "",
        "## Method",
        f"- Evaluation protocol: {e['protocol']} ({e['dev_rows']} development / {e['test_rows']} test rows).",
        f"- Model chosen by cross-validated ROC-AUC on development data only: **{c['algorithm']}**.",
        f"- Probabilities: {c['calibration']}.",
        "",
        "| Candidate | CV ROC-AUC (dev) | Best params |",
        "|---|---|---|",
        *[f"| {k} | {fmt(v['cv_roc_auc'], False)} | `{v['best_params']}` |" for k, v in e["model_selection_cv"].items()],
        "",
        "## Held-out test results",
        "| Metric | Value | 95% bootstrap CI |",
        "|---|---|---|",
        *[
            f"| {label} | {fmt(t[k], k != 'brier')} | {('%s – %s' % (fmt(ci[k][0]), fmt(ci[k][1]))) if k in ci else ''} |"
            for label, k in [
                ("Accuracy", "accuracy"),
                ("Sensitivity (recall)", "recall_sensitivity"),
                ("Specificity", "specificity"),
                ("Precision", "precision"),
                ("F1", "f1"),
                ("ROC-AUC", "roc_auc"),
                ("PR-AUC", "pr_auc"),
                ("Brier score (lower is better)", "brier"),
            ]
        ],
        "",
        f"Confusion matrix at threshold {t['threshold']}: TN={cm['tn']}, FP={cm['fp']}, FN={cm['fn']}, TP={cm['tp']}.",
        "",
        "### Calibration (test set, quantile bins)",
        "| Mean predicted probability | Observed rate |",
        "|---|---|",
        *[f"| {fmt(b['mean_predicted'])} | {fmt(b['observed_rate'])} |" for b in t["calibration"]],
        "",
        "## Cross-validation on all data (stability check)",
        "| Metric | Mean ± SD |",
        "|---|---|",
        *[f"| {k} | {fmt(v['mean'])} ± {fmt(v['std'])} |" for k, v in e["cross_validation_all_data"].items()],
    ]
    if e["external_validation"]:
        lines += ["", "## External validation (different hospital / population)", "| Dataset | n | Accuracy | Sensitivity | Specificity | ROC-AUC |", "|---|---|---|---|---|---|"]
        for name, m in e["external_validation"].items():
            lines.append(f"| {name} | {m['n']} | {fmt(m['accuracy'])} | {fmt(m['recall_sensitivity'])} | {fmt(m['specificity'])} | {fmt(m['roc_auc'])} |")
    lines += [
        "",
        "## Most influential inputs (permutation importance on test set, drop in ROC-AUC)",
        *[f"- {d['feature']}: {d['importance']:.3f} ± {d['std']:.3f}" for d in e["permutation_importance_test"][:8]],
        "",
        "## Limitations",
        *[f"- {x}" for x in c["limitations"]],
    ]
    if c.get("notes"):
        lines += ["", "## Notes", *[f"- {x}" for x in c["notes"]]]
    return "\n".join(lines) + "\n"
