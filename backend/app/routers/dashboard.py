"""Dashboard summary: /api/dashboard — one call with the user's own recent data."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import ChatMessage, Conversation, DietPlan, MealLog, MedicalImageAnalysis, Prediction, User
from app.services.users import age_from_dob, bmi_category

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    uid = user.id
    hp = user.health_profile
    profile_fields = {"date_of_birth": user.date_of_birth, "height": hp and hp.height_cm, "weight": hp and hp.weight_kg, "activity": hp and hp.activity_level, "diet": hp and hp.dietary_preference}
    completeness = round(100 * sum(bool(v) for v in profile_fields.values()) / len(profile_fields))

    count = lambda model: db.scalar(select(func.count()).select_from(model).where(model.user_id == uid)) or 0  # noqa: E731
    latest_preds = db.scalars(select(Prediction).where(Prediction.user_id == uid).order_by(Prediction.created_at.desc()).limit(4)).all()
    chats = db.scalars(select(Conversation).where(Conversation.user_id == uid, Conversation.message_count > 0).order_by(Conversation.last_message_at.desc()).limit(3)).all()
    latest_plan = db.scalar(select(DietPlan).where(DietPlan.user_id == uid).order_by(DietPlan.created_at.desc()).limit(1))
    today = date.today()
    logs_today = db.scalars(select(MealLog).where(MealLog.user_id == uid, MealLog.log_date == today)).all()
    week = db.execute(
        select(MealLog.log_date, func.sum(MealLog.nutrients["kcal"].as_float())).where(MealLog.user_id == uid, MealLog.log_date >= today - timedelta(days=6)).group_by(MealLog.log_date)
    ).all()
    images = db.scalars(select(MedicalImageAnalysis).where(MedicalImageAnalysis.user_id == uid).order_by(MedicalImageAnalysis.created_at.desc()).limit(1)).all()

    activity = (
        [{"kind": "prediction", "type": p.prediction_type, "label": p.label, "at": p.created_at.isoformat(), "id": str(p.id)} for p in latest_preds]

        + [{"kind": "image", "status": i.status, "label": i.predicted_class, "at": i.created_at.isoformat(), "id": str(i.id)} for i in images]
        + ([{"kind": "diet_plan", "kcal": latest_plan.targets.get("kcal"), "at": latest_plan.created_at.isoformat(), "id": str(latest_plan.id)}] if latest_plan else [])
    )
    first_user_msg = {}
    for c in chats:
        first_user_msg[c.id] = db.scalar(select(ChatMessage.content).where(ChatMessage.conversation_id == c.id, ChatMessage.role == "user").order_by(ChatMessage.created_at).limit(1))
    activity += [{"kind": "chat", "title": c.title or (first_user_msg.get(c.id) or "")[:60], "at": c.last_message_at.isoformat(), "id": str(c.id)} for c in chats]
    activity.sort(key=lambda a: a["at"], reverse=True)

    return {
        "profile": {"completeness": completeness, "missing": [k for k, v in profile_fields.items() if not v], "age": age_from_dob(user.date_of_birth),
                    "bmi": hp.bmi if hp else None, "bmi_category": bmi_category(hp.bmi) if hp else None},
        "counts": {"predictions": count(Prediction), "conversations": db.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == uid, Conversation.message_count > 0)) or 0,
                   "diet_plans": count(DietPlan), "image_analyses": count(MedicalImageAnalysis)},
        "latest_predictions": [{"id": str(p.id), "type": p.prediction_type, "label": p.label, "score": p.score, "display": (p.result or {}).get("display", "probability"), "at": p.created_at.isoformat()} for p in latest_preds],
        "nutrition_today": {"kcal": round(sum(l.nutrients.get("kcal", 0) for l in logs_today)), "protein_g": round(sum(l.nutrients.get("protein_g", 0) for l in logs_today)),
                            "meals": len(logs_today), "target_kcal": latest_plan.targets.get("kcal") if latest_plan else None, "target_protein_g": latest_plan.targets.get("protein_g") if latest_plan else None},
        "nutrition_week": [{"date": d.isoformat(), "kcal": round(k or 0)} for d, k in sorted(week)],
        "recent_chats": [{"id": str(c.id), "title": c.title or (first_user_msg.get(c.id) or "")[:60], "at": c.last_message_at.isoformat()} for c in chats],
        "activity": activity[:6],
    }
