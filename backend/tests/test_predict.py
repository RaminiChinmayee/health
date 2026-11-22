import json

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import auth, verified_login

HEART_OK = {"age": 58, "sex": 1, "cp": 4, "trestbps": 150, "chol": 270, "fbs": 0, "thalach": 120, "exang": 1, "oldpeak": 2.5, "restecg": 2, "slope": 2, "ca": 2, "thal": 7}
HEART_LOW = {"age": 35, "sex": 0, "cp": 3, "trestbps": 115, "chol": 180, "fbs": 0, "thalach": 180, "exang": 0, "oldpeak": 0, "slope": 1, "ca": 0, "thal": 3}


def test_meta_returns_card_and_profile_prefill(client, mailbox):
    t = verified_login(client, mailbox)  # registered as female, born 1995
    client.put("/api/profile/health", headers=auth(t), json={"height_cm": 160, "weight_kg": 64})
    m = client.get("/api/predict/heart/meta", headers=auth(t)).json()
    assert m["prefill"]["sex"] == 0 and m["prefill"]["age"] >= 30 and m["prefill"]["bmi"] == 25.0
    card = m["card"]
    assert card["dataset"]["license"] and card["limitations"]
    assert 0 < card["metrics"]["test"]["roc_auc"] <= 1 and card["metrics"]["ci95"]["roc_auc"]
    sym = client.get("/api/predict/symptoms/meta", headers=auth(t)).json()
    assert len(sym["vocabulary"]["symptoms"]) == 131 and "chest_pain" in sym["vocabulary"]["red_flag_symptoms"]


def test_heart_prediction_is_saved_and_explained(client, mailbox):
    t = verified_login(client, mailbox)
    hi = client.post("/api/predict/heart", headers=auth(t), json={"inputs": HEART_OK}).json()
    lo = client.post("/api/predict/heart", headers=auth(t), json={"inputs": HEART_LOW}).json()
    assert 0 <= lo["score"] < hi["score"] <= 1
    assert hi["label"] == "higher" and lo["label"] == "lower"
    assert hi["contributions"] and {"feature", "effect", "typical_value"} <= set(hi["contributions"][0])
    assert hi["safety"]["disclaimer"] == "not_a_diagnosis"
    assert any(w["code"] == "consult_doctor" for w in hi["safety"]["warnings"])
    assert hi["model_version"] == "1.0.0"


def test_validation_errors(client, mailbox):
    t = verified_login(client, mailbox)
    bad = {**HEART_OK, "age": 300, "cp": 9, "extra": 1}
    del bad["chol"]
    r = client.post("/api/predict/heart", headers=auth(t), json={"inputs": bad})
    assert r.status_code == 422
    f = r.json()["detail"]["fields"]
    assert f == {"age": "out_of_range", "cp": "literal_error", "chol": "required", "extra": "unknown_field"}


def test_missing_optional_inputs_are_flagged(client, mailbox):
    t = verified_login(client, mailbox)
    inp = {k: v for k, v in HEART_OK.items() if k not in ("ca", "thal", "slope", "restecg")}
    r = client.post("/api/predict/heart", headers=auth(t), json={"inputs": inp}).json()
    w = next(w for w in r["safety"]["warnings"] if w["code"] == "missing_optional_inputs")
    assert set(w["fields"]) == {"ca", "thal", "slope", "restecg"}


def test_diabetes_models(client, mailbox):
    t = verified_login(client, mailbox)
    r = client.post("/api/predict/diabetes", headers=auth(t), json={"inputs": {"plas": 180, "pres": 80, "mass": 34, "age": 50}})
    assert r.status_code == 200 and r.json()["score"] > 0.5
    q = {"age": 45, "sex": 1, **{k: 0 for k in ["polyuria", "polydipsia", "sudden_weight_loss", "weakness", "polyphagia", "genital_thrush", "visual_blurring", "itching", "irritability", "delayed_healing", "partial_paresis", "muscle_stiffness", "alopecia", "obesity"]}}
    low = client.post("/api/predict/diabetes_symptoms", headers=auth(t), json={"inputs": q}).json()
    high = client.post("/api/predict/diabetes_symptoms", headers=auth(t), json={"inputs": {**q, "polyuria": 1, "polydipsia": 1, "sudden_weight_loss": 1}}).json()
    assert low["score"] < high["score"]


def test_symptom_checker(client, mailbox):
    t = verified_login(client, mailbox)
    r = client.post("/api/predict/symptoms", headers=auth(t), json={"symptoms": ["high_fever", "headache", "pain_behind_the_eyes", "joint_pain", "skin_rash"]}).json()
    assert r["label"] == "dengue" and len(r["result"]["matches"]) == 5
    assert r["safety"]["emergency"] is True  # dengue is flagged urgent
    assert r["contributions"] and r["result"]["typical_not_reported"]
    chest = client.post("/api/predict/symptoms", headers=auth(t), json={"symptoms": ["chest_pain"]}).json()
    codes = {w["code"] for w in chest["safety"]["warnings"]}
    assert {"red_flag_symptoms", "few_symptoms"} <= codes
    assert client.post("/api/predict/symptoms", headers=auth(t), json={"symptoms": ["made_up"]}).status_code == 422


def test_history_filter_detail_delete_and_isolation(client, mailbox):
    ta = verified_login(client, mailbox, email="a@example.com")
    other = TestClient(app)
    tb = verified_login(other, mailbox, email="b@example.com")
    p1 = client.post("/api/predict/heart", headers=auth(ta), json={"inputs": HEART_OK}).json()
    client.post("/api/predict/symptoms", headers=auth(ta), json={"symptoms": ["cough", "high_fever"]})

    h = client.get("/api/history/predictions", headers=auth(ta)).json()
    assert h["total"] == 2 and h["counts_by_type"] == {"heart": 1, "symptoms": 1}
    assert client.get("/api/history/predictions?type=heart", headers=auth(ta)).json()["total"] == 1
    assert client.get("/api/history/predictions?date_from=2000-01-01&date_to=2000-01-02", headers=auth(ta)).json()["total"] == 0
    d = client.get(f"/api/history/predictions/{p1['id']}", headers=auth(ta)).json()
    assert d["model_card"]["version"] == "1.0.0" and d["model_superseded"] is False

    # Another user can neither see nor delete it, and gets no hint it exists.
    assert other.get(f"/api/history/predictions/{p1['id']}", headers=auth(tb)).status_code == 404
    assert other.delete(f"/api/history/{p1['id']}", headers=auth(tb)).status_code == 404
    assert other.get("/api/history/predictions", headers=auth(tb)).json()["total"] == 0

    assert client.delete(f"/api/history/{p1['id']}", headers=auth(ta)).status_code == 204
    assert client.get("/api/history/predictions", headers=auth(ta)).json()["total"] == 1


def test_export_includes_predictions(client, mailbox):
    t = verified_login(client, mailbox)
    client.post("/api/predict/heart", headers=auth(t), json={"inputs": HEART_OK})
    data = json.loads(client.get("/api/profile/export", headers=auth(t)).content)
    assert len(data["predictions"]) == 1 and data["predictions"][0]["prediction_type"] == "heart"


def test_parkinsons_uses_v2_and_never_shows_a_risk_level(client, mailbox):
    t = verified_login(client, mailbox)
    meta = client.get("/api/predict/parkinsons/meta", headers=auth(t)).json()["card"]
    assert meta["version"] == "2.0.0" and meta["display"] == "similarity"  # rejected v1 is never served
    healthy_like = {"jitter_local": 0.002, "jitter_local_abs": 0.00001, "jitter_rap": 0.0003, "jitter_ppq5": 0.0006, "jitter_ddp": 0.0009,
                    "shimmer_local": 0.03, "shimmer_local_db": 0.3, "shimmer_apq3": 0.015, "shimmer_apq5": 0.018, "shimmer_apq11": 0.025,
                    "shimmer_dda": 0.045, "nhr": 0.005, "hnr": 25, "period_mean": 0.006, "period_sd": 0.00005}
    r = client.post("/api/predict/parkinsons", headers=auth(t), json={"inputs": healthy_like}).json()
    assert r["label"] in ("resembles_healthy", "inconclusive", "resembles_condition")
    assert r["result"]["display"] == "similarity"
    assert any(w["code"] == "not_a_risk_estimate" for w in r["safety"]["warnings"])


def _vowel_wav(seconds=4.0, rate=44100, jitter=0.003, noise=0.02, f0=130.0):
    """Synthetic sustained vowel: harmonic source with pitch jitter and breath noise."""
    import io
    import wave

    import numpy as np

    rng = np.random.default_rng(1)
    n = int(rate * seconds)
    f = f0 * (1 + jitter * rng.standard_normal(n).cumsum() / 200)
    phase = 2 * np.pi * np.cumsum(f) / rate
    x = sum(np.sin(k * phase) / k**1.2 for k in range(1, 20)) * 0.25 + noise * rng.standard_normal(n)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32000).astype(np.int16).tobytes())
    return buf.getvalue()


def test_parkinsons_recording_measures_with_praat_and_gates_quality(client, mailbox):
    t = verified_login(client, mailbox)
    ok = client.post("/api/predict/parkinsons/recording", headers=auth(t), files={"file": ("a.wav", _vowel_wav(), "audio/wav")})
    if ok.status_code == 422:  # synthetic voice may fall outside the study's range — that gate must be explicit
        assert ok.json()["detail"]["code"] == "measurements_out_of_range"
    else:
        r = ok.json()
        assert r["result"]["source"] == "recording" and r["result"]["display"] == "similarity"
        assert set(r["inputs"]) >= {"jitter_local", "shimmer_local", "hnr", "period_mean"}
        assert any(w["code"] == "recording_based_experimental" for w in r["safety"]["warnings"])
    short = client.post("/api/predict/parkinsons/recording", headers=auth(t), files={"file": ("a.wav", _vowel_wav(1.0), "audio/wav")})
    assert short.json()["detail"]["code"] == "recording_too_short"
    silence = client.post("/api/predict/parkinsons/recording", headers=auth(t), files={"file": ("a.wav", _vowel_wav(4, noise=0.0, f0=130) [:44] + bytes(352800), "audio/wav")})
    assert silence.json()["detail"]["code"] in ("recording_too_quiet", "unsupported_audio_type")
    bad = client.post("/api/predict/parkinsons/recording", headers=auth(t), files={"file": ("a.wav", b"not audio" * 100, "audio/wav")})
    assert bad.json()["detail"]["code"] == "unsupported_audio_type"


def test_single_symptom_is_not_biased_to_few_symptom_diseases():
    from app.services import predictors

    r = predictors.predict_symptoms(["high_fever"])
    names = [m["disease"] for m in r["matches"]]
    assert {"typhoid", "dengue", "malaria"} <= set(names) and "aids" not in names
    assert "equal_matches" in {w["code"] for w in r["safety"]["warnings"]}
    # Specific symptom combinations still find the matching (also urgent / rarer) conditions.
    assert predictors.predict_symptoms(["high_fever", "headache", "joint_pain"])["matches"][0]["disease"] == "dengue"
    assert predictors.predict_symptoms(["chest_pain", "breathlessness", "sweating"])["matches"][0]["disease"] == "heart_attack"
    assert predictors.predict_symptoms(["muscle_wasting", "patches_in_throat", "high_fever"])["matches"][0]["disease"] == "aids"


def test_kidney_and_lung_models(client, mailbox):
    t = verified_login(client, mailbox)
    sick = {"age": 60, "bp": 90, "sc": 4.5, "hemo": 8.5, "al": 4, "htn": 1, "dm": 1, "appet": 1, "pe": 1, "ane": 1}
    well = {"age": 35, "bp": 75, "sc": 0.9, "hemo": 14.5, "al": 0, "htn": 0, "dm": 0, "appet": 0, "pe": 0, "ane": 0}
    hi = client.post("/api/predict/kidney", headers=auth(t), json={"inputs": sick}).json()
    lo = client.post("/api/predict/kidney", headers=auth(t), json={"inputs": well}).json()
    assert hi["result"]["probability"] > 0.8 > 0.2 > lo["result"]["probability"]
    assert client.post("/api/predict/kidney", headers=auth(t), json={"inputs": {**well, "sc": 99}}).status_code == 422

    lung = {"age": 62, "sex": 1, **{k: 1 for k in ("smoking", "yellow_fingers", "fatigue", "wheezing", "coughing", "shortness_of_breath", "chest_pain")},
            **{k: 0 for k in ("anxiety", "chronic_disease", "allergy", "alcohol", "swallowing_difficulty")}}
    r = client.post("/api/predict/lung", headers=auth(t), json={"inputs": lung}).json()
    assert r["result"]["display"] == "similarity" and r["result"]["risk_band"] in {"resembles_healthy", "inconclusive", "resembles_condition"}
    m = client.get("/api/predict/lung/meta", headers=auth(t)).json()
    assert "non-commercial" in m["card"]["dataset"]["license"]
    assert client.get("/api/history/predictions?type=kidney", headers=auth(t)).json()["total"] == 2
