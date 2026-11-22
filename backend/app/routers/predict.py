"""Prediction endpoints: /api/predict/*"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Prediction, User
from app.services import predictors
from app.services.users import age_from_dob

router = APIRouter(prefix="/api/predict", tags=["predict"])

PredictionType = Literal["symptoms", "diabetes", "diabetes_symptoms", "heart", "kidney", "lung", "parkinsons"]


class BinaryIn(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class SymptomsIn(BaseModel):
    symptoms: list[str] = Field(min_length=1, max_length=40)


def _unavailable(key: str) -> HTTPException:
    return HTTPException(503, detail={"code": "model_unavailable", "model": key})


def prediction_out(p: Prediction) -> dict:
    return {
        "id": str(p.id),
        "prediction_type": p.prediction_type,
        "model_key": p.model_key,
        "model_version": p.model_version,
        "inputs": p.inputs,
        "result": p.result,
        "score": p.score,
        "label": p.label,
        "contributions": p.contributions,
        "safety": p.safety,
        "created_at": p.created_at.isoformat(),
    }


def _prefill(user: User) -> dict:
    """Values from the user's own profile that can pre-fill a form. Gender is only mapped to
    the models' binary sex input when the user chose female or male."""
    hp = user.health_profile
    out: dict[str, Any] = {}
    if user.date_of_birth:
        out["age"] = age_from_dob(user.date_of_birth)
    if user.gender in ("female", "male"):
        out["sex"] = 1 if user.gender == "male" else 0
    if hp and hp.bmi:
        out["bmi"] = hp.bmi
    return out


@router.get("/{ptype}/meta")
def meta(ptype: PredictionType, user: User = Depends(get_current_user)):
    try:
        m = predictors.load_model(ptype)
    except predictors.ModelUnavailable:
        raise _unavailable(ptype)
    out = {"card": predictors.public_card(m.card), "prefill": _prefill(user)}
    if ptype == "symptoms":
        out["vocabulary"] = predictors.symptom_vocabulary()
    return out


@router.post("/symptoms")
def predict_symptoms(body: SymptomsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        r = predictors.predict_symptoms(body.symptoms)
    except predictors.ModelUnavailable:
        raise _unavailable("symptoms")
    except predictors.InputError as e:
        raise HTTPException(422, detail={"code": "validation_error", "fields": e.fields})
    rec = Prediction(
        user_id=user.id,
        prediction_type="symptoms",
        model_key=r["model_key"],
        model_version=r["model_version"],
        inputs=r["inputs"],
        result={"matches": r["matches"], "typical_not_reported": r["typical_not_reported"]},
        score=r["score"],
        label=r["top"],
        contributions=r["contributions"],
        safety=r["safety"],
    )
    db.add(rec)
    db.commit()
    return prediction_out(rec)


@router.post("/{ptype}")
def predict_binary(ptype: Literal["diabetes", "diabetes_symptoms", "heart", "kidney", "lung", "parkinsons"], body: BinaryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        r = predictors.predict_binary(ptype, body.inputs)
    except predictors.ModelUnavailable:
        raise _unavailable(ptype)
    except predictors.InputError as e:
        raise HTTPException(422, detail={"code": "validation_error", "fields": e.fields})
    rec = Prediction(
        user_id=user.id,
        prediction_type=ptype,
        model_key=r["model_key"],
        model_version=r["model_version"],
        inputs=r["inputs"],
        result={"probability": r["probability"], "risk_band": r["risk_band"], "display": r["display"]},
        score=r["probability"],
        label=r["risk_band"],
        contributions=r["contributions"],
        safety=r["safety"],
    )
    db.add(rec)
    db.commit()
    return prediction_out(rec)


@router.post("/parkinsons/recording")
async def predict_parkinsons_from_recording(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Experimental: measure voice features from a sustained 'aaa' WAV recording with Praat, then
    run the Parkinson's model. The audio is not stored; only the measured values are saved."""
    from app.services import voice_features

    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, detail={"code": "file_too_large"})
    try:
        m = predictors.load_model("parkinsons")
    except predictors.ModelUnavailable:
        raise _unavailable("parkinsons")
    try:
        measured = voice_features.measure(data)
    except voice_features.RecordingRejected as e:
        raise HTTPException(422, detail={"code": e.code, **e.details})
    outside = voice_features.check_range(measured["features"], m.card["features"])
    if outside:
        # Refuse instead of extrapolating far outside the training data.
        raise HTTPException(422, detail={"code": "measurements_out_of_range", "fields": outside, "features": measured["features"]})
    r = predictors.predict_binary("parkinsons", measured["features"])
    r["safety"]["warnings"].append({"code": "recording_based_experimental"})
    rec = Prediction(
        user_id=user.id, prediction_type="parkinsons", model_key=r["model_key"], model_version=r["model_version"],
        inputs={**r["inputs"]}, result={"probability": r["probability"], "risk_band": r["risk_band"], "display": r["display"], "source": "recording", "quality": measured["quality"]},
        score=r["probability"], label=r["risk_band"], contributions=r["contributions"], safety=r["safety"],
    )
    db.add(rec)
    db.commit()
    return prediction_out(rec)
