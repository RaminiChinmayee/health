"""Symptom checker — multi-class disease matching from reported symptoms.

Data: the widely used 41-disease / 132-symptom dataset (Kaggle "Disease Prediction Using
Machine Learning", here from a GitHub mirror). It is *synthetic*: each disease has a fixed
symptom set and rows are random subsets of it. The 4,920 rows contain only ~304 unique
symptom patterns, and the published "test" file's rows almost all appear in training, which
is why scores near 100% are commonly reported for it.

Protocol here:
  * merge train+test files and drop exact duplicates → unique patterns only;
  * repeated stratified 5-fold CV over unique patterns;
  * evaluate on the full held-out patterns AND on a *partial-symptom* simulation (users
    usually report only some symptoms): each test pattern keeps a random 50% of its symptoms;
  * optional training-time augmentation with random symptom subsets (inside training folds
    only, never touching the test fold).
Scores are reported as top-1 / top-3 accuracy and macro-F1. They measure agreement with this
dataset's disease–symptom table, NOT clinical diagnostic accuracy.
"""
import json
import re
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.naive_bayes import BernoulliNB

from common import ARTIFACTS, RAW, SEED, _clean, sha256

VERSION = "1.1.0"

# Source labels contain typos; display names fixed here (the model keeps stable keys).
DISEASES = {
    "(vertigo) Paroymsal  Positional Vertigo": ("bppv", "Benign paroxysmal positional vertigo"),
    "AIDS": ("aids", "HIV/AIDS"),
    "Acne": ("acne", "Acne"),
    "Alcoholic hepatitis": ("alcoholic_hepatitis", "Alcoholic hepatitis"),
    "Allergy": ("allergy", "Allergy"),
    "Arthritis": ("arthritis", "Arthritis"),
    "Bronchial Asthma": ("asthma", "Bronchial asthma"),
    "Cervical spondylosis": ("cervical_spondylosis", "Cervical spondylosis"),
    "Chicken pox": ("chicken_pox", "Chickenpox"),
    "Chronic cholestasis": ("chronic_cholestasis", "Chronic cholestasis"),
    "Common Cold": ("common_cold", "Common cold"),
    "Dengue": ("dengue", "Dengue"),
    "Diabetes ": ("diabetes", "Diabetes"),
    "Dimorphic hemmorhoids(piles)": ("hemorrhoids", "Haemorrhoids (piles)"),
    "Drug Reaction": ("drug_reaction", "Drug reaction"),
    "Fungal infection": ("fungal_infection", "Fungal infection"),
    "GERD": ("gerd", "Gastro-oesophageal reflux disease (GERD)"),
    "Gastroenteritis": ("gastroenteritis", "Gastroenteritis"),
    "Heart attack": ("heart_attack", "Heart attack"),
    "Hepatitis B": ("hepatitis_b", "Hepatitis B"),
    "Hepatitis C": ("hepatitis_c", "Hepatitis C"),
    "Hepatitis D": ("hepatitis_d", "Hepatitis D"),
    "Hepatitis E": ("hepatitis_e", "Hepatitis E"),
    "Hypertension ": ("hypertension", "Hypertension"),
    "Hyperthyroidism": ("hyperthyroidism", "Hyperthyroidism"),
    "Hypoglycemia": ("hypoglycemia", "Hypoglycaemia"),
    "Hypothyroidism": ("hypothyroidism", "Hypothyroidism"),
    "Impetigo": ("impetigo", "Impetigo"),
    "Jaundice": ("jaundice", "Jaundice"),
    "Malaria": ("malaria", "Malaria"),
    "Migraine": ("migraine", "Migraine"),
    "Osteoarthristis": ("osteoarthritis", "Osteoarthritis"),
    "Paralysis (brain hemorrhage)": ("brain_hemorrhage", "Paralysis (brain haemorrhage)"),
    "Peptic ulcer diseae": ("peptic_ulcer", "Peptic ulcer disease"),
    "Pneumonia": ("pneumonia", "Pneumonia"),
    "Psoriasis": ("psoriasis", "Psoriasis"),
    "Tuberculosis": ("tuberculosis", "Tuberculosis"),
    "Typhoid": ("typhoid", "Typhoid"),
    "Urinary tract infection": ("uti", "Urinary tract infection"),
    "Varicose veins": ("varicose_veins", "Varicose veins"),
    "hepatitis A": ("hepatitis_a", "Hepatitis A"),
}
# Conditions that need urgent care: flagged whenever they appear in the top results.
URGENT_DISEASES = {"heart_attack", "brain_hemorrhage", "dengue", "malaria", "pneumonia", "typhoid", "hypoglycemia", "alcoholic_hepatitis", "hepatitis_b", "hepatitis_c", "hepatitis_d", "hepatitis_e", "tuberculosis"}
# Symptoms that warrant urgent medical attention regardless of the model output.
RED_FLAG_SYMPTOMS = {
    "chest_pain", "breathlessness", "weakness_of_one_body_side", "altered_sensorium", "slurred_speech",
    "coma", "stomach_bleeding", "blood_in_sputum", "acute_liver_failure", "fast_heart_rate",
    "bloody_stool", "loss_of_balance", "palpitations", "spinning_movements", "unsteadiness",
}


def clean_symptom(s: str) -> str:
    s = s.strip().lower().replace("(typhos)", "typhos")
    s = re.sub(r"[\s_]+", "_", s)
    return re.sub(r"[^a-z0-9_]", "", s).strip("_")


def load() -> tuple[pd.DataFrame, pd.Series]:
    frames = []
    for f in ("symptoms_training.csv", "symptoms_test.csv"):
        d = pd.read_csv(RAW / f)
        frames.append(d.loc[:, ~d.columns.str.startswith("Unnamed")])
    df = pd.concat(frames, ignore_index=True).drop_duplicates()
    y = df.pop("prognosis").map(lambda v: DISEASES[v][0])
    df.columns = [clean_symptom(c) for c in df.columns]
    # Drop symptoms that never occur (the source has an all-zero "fluid_overload" next to the
    # real "fluid_overload.1" column), then give the real one the clean name.
    df = df.loc[:, df.sum() > 0].rename(columns={"fluid_overload1": "fluid_overload"})
    assert df.columns.is_unique
    return df.astype(np.int8), y


# ----------------------------------------------------------------------------- ranking
# Inference-time ranking used by the app (v1.1.0). Two adjustments to plain Bernoulli NB:
#  1. An unticked symptom usually means "not mentioned", not "absent". Plain NB penalises every
#     unticked symptom fully, so with 1–2 symptoms it favours diseases that have FEW symptoms
#     (e.g. "high fever" alone → HIV/AIDS). The absent-symptom penalty is scaled by
#     min(1, (n_selected − 1) / ABSENT_RAMP): none for one symptom, full from ABSENT_RAMP+1.
#  2. The dataset has no prevalence information (every disease has the same number of rows).
#     A coarse prior gives conditions that are common in India COMMON_WEIGHT× the weight of the
#     others. This is a clinical-knowledge heuristic, NOT measured prevalence; it mainly orders
#     diseases that the symptoms cannot tell apart.
ABSENT_RAMP = 6
# 3. A symptom that is typical for a disease (P ≥ POS_CAP) counts the same for every such disease;
#    small differences between e.g. 0.54 and 0.66 are sampling noise in the synthetic table.
POS_CAP = 0.5
COMMON_WEIGHT = 3.0
COMMON_IN_INDIA = {
    "common_cold", "allergy", "gastroenteritis", "gerd", "migraine", "uti", "fungal_infection", "acne",
    "hypertension", "diabetes", "hypothyroidism", "asthma", "arthritis", "osteoarthritis",
    "cervical_spondylosis", "hemorrhoids", "peptic_ulcer", "dengue", "malaria", "typhoid",
    "tuberculosis", "pneumonia", "chicken_pox", "jaundice", "hepatitis_a", "hepatitis_e",
}


def rank_proba(model, X: np.ndarray, use_prior: bool = True, ramp: int = ABSENT_RAMP) -> np.ndarray:
    lp = model.feature_log_prob_
    ln = np.log1p(-np.exp(lp))
    n = X.sum(1, keepdims=True)
    w = np.clip((n - 1) / ramp, 0, 1)
    s = X @ np.minimum(lp, np.log(POS_CAP)).T + w * ((1 - X) @ ln.T)
    if use_prior:
        s = s + np.log(np.where(np.isin(model.classes_, list(COMMON_IN_INDIA)), COMMON_WEIGHT, 1.0))
    s = s - s.max(1, keepdims=True)
    e = np.exp(s)
    return e / e.sum(1, keepdims=True)


def k_symptoms(X: np.ndarray, k: int, rng) -> np.ndarray:
    Xp = np.zeros_like(X)
    for i in range(len(X)):
        on = np.flatnonzero(X[i])
        Xp[i, rng.choice(on, size=min(k, len(on)), replace=False)] = 1
    return Xp


def augment(X: np.ndarray, y: np.ndarray, k: int, rng) -> tuple[np.ndarray, np.ndarray]:
    """Add k random symptom subsets (30–100% of each pattern's symptoms) per training row."""
    Xs, ys = [X], [y]
    for _ in range(k):
        keep = rng.random(X.shape) < rng.uniform(0.3, 1.0, size=(X.shape[0], 1))
        Xa = X * keep
        empty = Xa.sum(1) == 0
        Xa[empty] = X[empty]
        Xs.append(Xa)
        ys.append(y)
    return np.vstack(Xs), np.concatenate(ys)


def partial(X: np.ndarray, frac: float, rng) -> np.ndarray:
    Xp = X.copy()
    for i in range(len(Xp)):
        on = np.flatnonzero(Xp[i])
        drop = rng.choice(on, size=int(len(on) * (1 - frac)), replace=False) if len(on) > 1 else []
        Xp[i, drop] = 0
    return Xp


def topk(proba: np.ndarray, classes: np.ndarray, y: np.ndarray, k: int) -> float:
    top = classes[np.argsort(-proba, axis=1)[:, :k]]
    return float(np.mean([yy in row for yy, row in zip(y, top)]))


CANDIDATES = {
    "bernoulli_nb": lambda: BernoulliNB(alpha=1.0),
    "logistic_regression": lambda: LogisticRegression(C=1.0, max_iter=5000),
    "random_forest": lambda: RandomForestClassifier(n_estimators=300, random_state=SEED, n_jobs=-1),
}

if __name__ == "__main__":
    X_df, y_s = load()
    X, y = X_df.values, y_s.values
    min_per_class = y_s.value_counts().min()
    rng = np.random.default_rng(SEED)
    cv = RepeatedStratifiedKFold(n_splits=min(5, min_per_class), n_repeats=3, random_state=SEED)

    results = {}
    for name, make in CANDIDATES.items():
        for aug in (0, 20):
            scores = {k: [] for k in ("full_top1", "full_top3", "full_macro_f1", "partial_top1", "partial_top3", "partial_macro_f1")}
            for tr, te in cv.split(X, y):
                Xtr, ytr = (augment(X[tr], y[tr], aug, rng) if aug else (X[tr], y[tr]))
                m = make().fit(Xtr, ytr)
                for tag, Xt in (("full", X[te]), ("partial", partial(X[te], 0.5, rng))):
                    p = m.predict_proba(Xt)
                    scores[f"{tag}_top1"].append(topk(p, m.classes_, y[te], 1))
                    scores[f"{tag}_top3"].append(topk(p, m.classes_, y[te], 3))
                    scores[f"{tag}_macro_f1"].append(f1_score(y[te], m.classes_[p.argmax(1)], average="macro"))
            results[f"{name}{'+augment' if aug else ''}"] = {k: {"mean": np.mean(v), "std": np.std(v)} for k, v in scores.items()}
            r = results[f"{name}{'+augment' if aug else ''}"]
            print(f"{name:22} aug={aug:2}  full top1={r['full_top1']['mean']:.3f} top3={r['full_top3']['mean']:.3f} | partial top1={r['partial_top1']['mean']:.3f} top3={r['partial_top3']['mean']:.3f} f1={r['partial_macro_f1']['mean']:.3f}")

    # Select on the realistic partial-symptom top-3 accuracy.
    best = max(results, key=lambda k: (results[k]["partial_top3"]["mean"], results[k]["partial_top1"]["mean"]))
    algo, use_aug = best.split("+")[0], best.endswith("+augment")
    Xf, yf = augment(X, y, 20, np.random.default_rng(SEED)) if use_aug else (X, y)
    model = CANDIDATES[algo]().fit(Xf, yf)

    # Ranking evaluation (selected NB model): plain NB vs the app's ranking, incl. 1–3 symptoms.
    ranking_eval = {}
    if algo == "bernoulli_nb":
        rng2 = np.random.default_rng(SEED + 1)
        variants = {"plain_nb": None, "ramp_only": False, "ramp_plus_prior": True}
        acc = {}
        for tr, te in cv.split(X, y):
            Xtr, ytr = augment(X[tr], y[tr], 20, rng2) if use_aug else (X[tr], y[tr])
            m = BernoulliNB(alpha=1.0).fit(Xtr, ytr)
            sets = {"1 symptom": k_symptoms(X[te], 1, rng2), "2 symptoms": k_symptoms(X[te], 2, rng2), "3 symptoms": k_symptoms(X[te], 3, rng2), "50% of symptoms": partial(X[te], 0.5, rng2), "all symptoms": X[te]}
            for tag, Xt in sets.items():
                for vn, pr in variants.items():
                    p = m.predict_proba(Xt) if pr is None else rank_proba(m, Xt, use_prior=pr)
                    acc.setdefault((vn, tag), []).append([topk(p, m.classes_, y[te], k) for k in (1, 3, 5)])
        for (vn, tag), v in acc.items():
            mean = np.mean(v, 0)
            ranking_eval.setdefault(vn, {})[tag] = {"top1": mean[0], "top3": mean[1], "top5": mean[2]}
        for vn, d in ranking_eval.items():
            print(vn, {t: f"{r['top1']:.2f}/{r['top3']:.2f}/{r['top5']:.2f}" for t, r in d.items()})

    # Symptom ↔ disease table derived from the data (for "typical symptoms" display).
    typical = {d: sorted(X_df.columns[(X_df[y_s == d].mean() >= 0.5).values].tolist()) for d in sorted(set(y))}

    card = _clean({
        "key": "symptoms",
        "version": VERSION,
        "title": "Symptom checker",
        "task": "multiclass_matching",
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "algorithm": best,
        "symptoms": list(X_df.columns),
        "diseases": {v[0]: v[1] for v in DISEASES.values()},
        "typical_symptoms": typical,
        "urgent_diseases": sorted(URGENT_DISEASES),
        "ranking": {
            "absent_ramp": ABSENT_RAMP,
            "pos_cap": POS_CAP,
            "common_weight": COMMON_WEIGHT,
            "common_in_india": sorted(COMMON_IN_INDIA),
            "note": "Absent-symptom penalty scaled by min(1,(n-1)/absent_ramp). Prior: clinical-knowledge heuristic, not measured prevalence.",
        },
        "red_flag_symptoms": sorted(RED_FLAG_SYMPTOMS & set(X_df.columns)),
        "dataset": {
            "name": "Disease Prediction Using Machine Learning (41 diseases, 132 symptoms)",
            "source": "https://www.kaggle.com/datasets/kaushil268/disease-prediction-using-machine-learning (copy from https://github.com/anujdutt9/Disease-Prediction-from-Symptoms)",
            "license": "Not clearly stated by the original publisher — verify before commercial use",
            "population": "Synthetic: generated from a fixed disease–symptom table, not real patient records",
            "rows_raw": 4920 + 42,
            "unique_patterns": int(len(X)),
            "patterns_per_disease_min": int(min_per_class),
            "files": {f: sha256(RAW / f) for f in ("symptoms_training.csv", "symptoms_test.csv")},
        },
        "evaluation": {
            "protocol": f"Repeated stratified {cv.cvargs['n_splits']}-fold CV ×3 over unique symptom patterns; 'partial' keeps a random 50% of each test pattern's symptoms.",
            "candidates": results,
            "selected": results[best],
            "ranking": ranking_eval,
        },
        "limitations": [
            "The training data is synthetic, generated from a fixed table of diseases and symptoms. Scores show how well the model reproduces that table, not how accurately it identifies illness in real people.",
            "Only 41 conditions are covered. Your illness may be something not on the list, and the closest match will still be shown.",
            "With only one or two symptoms many conditions fit equally well; the order among them partly reflects a 'common in India' heuristic, not your individual risk. Add more symptoms for a more specific result.",
            "Match scores are relative to these 41 conditions and are not the probability that you have a disease.",
            "Not a diagnosis. Many conditions share symptoms; a doctor's examination and tests are needed.",
        ],
        "environment": {"sklearn": sklearn.__version__},
    })
    out = ARTIFACTS / "symptoms" / VERSION
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "symptoms": list(X_df.columns)}, out / "model.joblib", compress=3)
    (out / "card.json").write_text(json.dumps(card, indent=2, ensure_ascii=False))

    sel = results[best]
    report = [
        f"# Symptom checker — model report (v{VERSION})",
        "",
        f"*Generated {card['trained_at']} by `ml/train_symptoms.py`.*",
        "",
        "## Data",
        f"- {card['dataset']['name']} — {card['dataset']['source']}",
        f"- **Synthetic data.** {card['dataset']['rows_raw']} rows contain only **{len(X)} unique symptom patterns** (at least {min_per_class} per disease). Duplicates were removed before evaluation; the original test file's rows nearly all appear in its training file.",
        f"- Licence: {card['dataset']['license']}",
        "",
        "## Results (cross-validation over unique patterns)",
        "| Model | Full symptoms top-1 | Full top-3 | 50% symptoms top-1 | 50% top-3 | 50% macro-F1 |",
        "|---|---|---|---|---|---|",
        *[f"| {k}{' **(selected)**' if k == best else ''} | {v['full_top1']['mean']:.1%} | {v['full_top3']['mean']:.1%} | {v['partial_top1']['mean']:.1%} ± {v['partial_top1']['std']:.1%} | {v['partial_top3']['mean']:.1%} | {v['partial_macro_f1']['mean']:.3f} |" for k, v in results.items()],
        "",
        "Selection criterion: top-3 accuracy with 50% of symptoms (the realistic case).",
        "",
        "## Ranking used in the app (v1.1.0)",
        f"- Unticked symptoms are treated as 'not mentioned': their penalty is scaled by min(1, (n − 1)/{ABSENT_RAMP}), so one symptom alone no longer favours diseases with few symptoms. A symptom typical for a disease (probability ≥ {POS_CAP:g}) counts equally for every such disease.",
        f"- Conditions common in India get {COMMON_WEIGHT:g}× prior weight: {', '.join(sorted(COMMON_IN_INDIA))}. **This is a clinical-knowledge heuristic, not measured prevalence**; the dataset has none.",
        "- Accuracy (correct disease ranked 1st / in top 3 / in top 5). The test folds have every disease equally often, so they cannot reward the prior, and it costs a little accuracy for rare conditions here:",
        "",
        "| Input | Plain NB | Not-mentioned ramp | Ramp + India prior (app) |",
        "|---|---|---|---|",
        *[f"| {t} | " + " | ".join(f"{ranking_eval[v][t]['top1']:.0%} / {ranking_eval[v][t]['top3']:.0%} / {ranking_eval[v][t]['top5']:.0%}" for v in ("plain_nb", "ramp_only", "ramp_plus_prior")) + " |" for t in (ranking_eval.get("plain_nb") or {})],
        "",
        "## Safety rules (not learned — applied at inference)",
        f"- Red-flag symptoms always trigger an urgent-care message: {', '.join(card['red_flag_symptoms'])}.",
        f"- Urgent conditions are flagged whenever they appear in the top results: {', '.join(card['urgent_diseases'])}.",
        "",
        "## Limitations",
        *[f"- {x}" for x in card["limitations"]],
    ]
    (out / "report.md").write_text("\n".join(report) + "\n")
    print("selected:", best)
