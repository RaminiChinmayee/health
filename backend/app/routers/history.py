"""User history: /api/history/*  — every query is filtered by the authenticated user's id."""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Conversation, DietPlan, MealLog, Prediction, User
from app.routers.predict import prediction_out
from app.services import predictors

router = APIRouter(prefix="/api/history", tags=["history"])

IST = timezone(timedelta(hours=5, minutes=30))


def _not_found() -> HTTPException:
    # Same response whether the record doesn't exist or belongs to someone else.
    return HTTPException(404, detail={"code": "not_found"})


@router.get("/predictions")
def list_predictions(
    type: Literal["symptoms", "diabetes", "diabetes_symptoms", "heart", "kidney", "lung", "parkinsons", "image"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(Prediction).where(Prediction.user_id == user.id)
    if type:
        q = q.where(Prediction.prediction_type == type)
    if date_from:
        q = q.where(Prediction.created_at >= datetime.combine(date_from, time.min, IST))
    if date_to:
        q = q.where(Prediction.created_at < datetime.combine(date_to + timedelta(days=1), time.min, IST))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Prediction.created_at.desc()).limit(limit).offset(offset)).all()
    counts = dict(
        db.execute(select(Prediction.prediction_type, func.count()).where(Prediction.user_id == user.id).group_by(Prediction.prediction_type)).all()
    )
    return {"total": total, "items": [prediction_out(r) for r in rows], "counts_by_type": counts}


@router.get("/predictions/{pid}")
def get_prediction(pid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.scalar(select(Prediction).where(Prediction.id == pid, Prediction.user_id == user.id))
    if p is None:
        raise _not_found()
    out = prediction_out(p)
    # Model card for the version that produced this record, if still installed.
    try:
        m = predictors.load_model(p.model_key)
        out["model_card"] = predictors.public_card(m.card) if m.version == p.model_version else None
        out["model_superseded"] = m.version != p.model_version
    except predictors.ModelUnavailable:
        out["model_card"], out["model_superseded"] = None, True
    return out


@router.get("/diets")
def list_diets(
    favorites_only: bool = False,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(DietPlan).where(DietPlan.user_id == user.id)
    if favorites_only:
        q = q.where(DietPlan.is_favorite.is_(True))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(DietPlan.created_at.desc()).limit(limit).offset(offset)).all()
    return {
        "total": total,
        "items": [
            {"id": str(r.id), "title": r.title, "targets": r.targets, "is_favorite": r.is_favorite, "created_at": r.created_at.isoformat(), "days": len(r.plan.get("days", []))}
            for r in rows
        ],
    }


@router.delete("/{record_id}", status_code=204)
def delete_record(record_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete one of the user's history records (prediction, diet plan, meal log or conversation)."""
    if db.scalar(select(Conversation.id).where(Conversation.id == record_id, Conversation.user_id == user.id)):
        from app.routers.chat import _delete_conv_files

        _delete_conv_files(db, user, [record_id])  # private audio files go with the conversation
    from app.models import ChatAttachment, MedicalImageAnalysis

    img = db.scalar(select(MedicalImageAnalysis).where(MedicalImageAnalysis.id == record_id, MedicalImageAnalysis.user_id == user.id))
    if img is not None:  # deleting an image analysis also deletes the stored image
        att = db.get(ChatAttachment, img.attachment_id) if img.attachment_id else None
        if att is not None and att.user_id == user.id:
            from app.config import get_settings

            root = get_settings().storage_dir.resolve()
            p = (root / att.storage_path).resolve()
            if root in p.parents:
                p.unlink(missing_ok=True)
            db.delete(att)
        db.delete(img)
        db.commit()
        return None
    for model in (Prediction, DietPlan, MealLog, Conversation):
        res = db.execute(delete(model).where(model.id == record_id, model.user_id == user.id))
        if res.rowcount:
            db.commit()
            return None
    raise _not_found()
