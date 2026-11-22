"""Diet planner & nutrition tracking: /api/diet/*"""
import time as _time
import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import DietPlan, FoodFeedback, MealLog, User
from app.services import diet as svc
from app.services.users import age_from_dob

router = APIRouter(prefix="/api/diet", tags=["diet"])

Slot = Literal["breakfast", "lunch", "snack", "dinner"]


def _err(status: int, code: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, **extra})


def _profile_inputs(user: User) -> tuple[dict, list[str]]:
    hp = user.health_profile
    age = age_from_dob(user.date_of_birth)
    missing = [k for k, v in {"date_of_birth": age, "height_cm": hp and hp.height_cm, "weight_kg": hp and hp.weight_kg, "activity_level": hp and hp.activity_level}.items() if not v]
    return (
        {
            "age": age,
            "sex": user.gender if user.gender in ("female", "male") else None,
            "height_cm": hp.height_cm if hp else None,
            "weight_kg": hp.weight_kg if hp else None,
            "bmi": hp.bmi if hp else None,
            "activity_level": hp.activity_level if hp else None,
            "dietary_preference": hp.dietary_preference if hp else None,
            "food_allergies": list(hp.food_allergies) if hp else [],
            "has_health_conditions": bool(hp and hp.health_conditions),
        },
        missing,
    )


def _check_eligibility(p: dict, goal: str) -> None:
    if p["age"] is not None and p["age"] < 18:
        raise _err(422, "diet_minor_not_supported")
    if goal == "lose" and p["bmi"] is not None and p["bmi"] < 18.5:
        raise _err(422, "weight_loss_not_advised")


def _feedback(db: Session, user: User) -> tuple[set[str], set[str]]:
    rows = db.scalars(select(FoodFeedback).where(FoodFeedback.user_id == user.id)).all()
    return {r.dish_key for r in rows if r.rating < 0}, {r.dish_key for r in rows if r.favorite or r.rating > 0}


def plan_out(p: DietPlan) -> dict:
    return {"id": str(p.id), "title": p.title, "inputs": p.inputs, "targets": p.targets, "plan": p.plan, "is_favorite": p.is_favorite, "created_at": p.created_at.isoformat()}


@router.get("/meta")
def meta(goal: Literal["lose", "maintain", "gain"] = "maintain", user: User = Depends(get_current_user)):
    p, missing = _profile_inputs(user)
    targets = None
    if not missing:
        targets = svc.compute_targets(age=p["age"], sex=p["sex"], height_cm=p["height_cm"], weight_kg=p["weight_kg"], activity=p["activity_level"], goal=goal)
    return {"profile": p, "missing": missing, "targets": targets, "catalogue": svc.catalogue()}


class PlanIn(BaseModel):
    goal: Literal["lose", "maintain", "gain"] = "maintain"
    days: int = Field(7, ge=1, le=7)
    title: str | None = Field(default=None, max_length=200)


@router.post("/plans", status_code=201)
def create_plan(body: PlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p, missing = _profile_inputs(user)
    if missing:
        raise _err(422, "health_profile_incomplete", missing=missing)
    _check_eligibility(p, body.goal)
    targets = svc.compute_targets(age=p["age"], sex=p["sex"], height_cm=p["height_cm"], weight_kg=p["weight_kg"], activity=p["activity_level"], goal=body.goal)
    disliked, favorites = _feedback(db, user)
    try:
        plan = svc.generate_plan(
            targets=targets, diet=p["dietary_preference"], allergies=p["food_allergies"], disliked=disliked,
            favorites=favorites, days=body.days, seed=hash((str(user.id), _time.time_ns())) & 0xFFFFFFFF,
        )
    except svc.DietError as e:
        raise _err(422, e.code)
    if p["has_health_conditions"]:
        plan["notes"].append({"code": "check_with_professional"})
    rec = DietPlan(user_id=user.id, title=body.title or f"{body.goal}-{date.today().isoformat()}", inputs={**p, "goal": body.goal}, targets=targets, plan=plan)
    db.add(rec)
    db.commit()
    return plan_out(rec)


def _owned_plan(db: Session, user: User, pid: uuid.UUID) -> DietPlan:
    rec = db.scalar(select(DietPlan).where(DietPlan.id == pid, DietPlan.user_id == user.id))
    if rec is None:
        raise _err(404, "not_found")
    return rec


@router.get("/plans/{pid}")
def get_plan(pid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return plan_out(_owned_plan(db, user, pid))


class PlanPatch(BaseModel):
    is_favorite: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)


@router.patch("/plans/{pid}")
def patch_plan(pid: uuid.UUID, body: PlanPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = _owned_plan(db, user, pid)
    if body.is_favorite is not None:
        rec.is_favorite = body.is_favorite
    if body.title:
        rec.title = body.title
    db.commit()
    return plan_out(rec)


# ------------------------------------------------------------------ meal logs (completed meals)
class LogIn(BaseModel):
    log_date: date
    slot: Slot
    dish_key: str = Field(max_length=64)
    servings: float = Field(gt=0, le=5)
    plan_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


def log_out(m: MealLog) -> dict:
    return {"id": str(m.id), "log_date": m.log_date.isoformat(), "slot": m.slot, "dish_key": m.dish_key, "servings": m.servings, "nutrients": m.nutrients, "plan_id": str(m.plan_id) if m.plan_id else None, "note": m.note}


@router.post("/logs", status_code=201)
def add_log(body: LogIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dish = svc.foods()["dishes"].get(body.dish_key)
    if dish is None:
        raise _err(422, "unknown_dish")
    if body.log_date > date.today() + timedelta(days=1):
        raise _err(422, "date_in_future")
    if body.plan_id:
        _owned_plan(db, user, body.plan_id)  # can't attach to someone else's plan
    n = {k: round(v * body.servings, 1) for k, v in dish["per_serving"].items()}
    rec = MealLog(user_id=user.id, plan_id=body.plan_id, log_date=body.log_date, slot=body.slot, dish_key=body.dish_key, servings=body.servings, nutrients=n, note=body.note)
    db.add(rec)
    db.commit()
    return log_out(rec)


@router.get("/logs")
def list_logs(date_from: date = Query(...), date_to: date = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if (date_to - date_from).days > 62:
        raise _err(422, "range_too_large")
    rows = db.scalars(select(MealLog).where(MealLog.user_id == user.id, MealLog.log_date >= date_from, MealLog.log_date <= date_to).order_by(MealLog.log_date, MealLog.created_at)).all()
    return [log_out(r) for r in rows]


@router.get("/summary")
def weekly_summary(week_start: date = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    end = week_start + timedelta(days=6)
    rows = db.scalars(select(MealLog).where(MealLog.user_id == user.id, MealLog.log_date >= week_start, MealLog.log_date <= end)).all()
    keys = ("kcal", "protein_g", "fat_g", "carbs_g", "fiber_g")
    days = {(week_start + timedelta(days=i)).isoformat(): {k: 0.0 for k in keys} | {"meals": 0} for i in range(7)}
    for r in rows:
        d = days[r.log_date.isoformat()]
        d["meals"] += 1
        for k in keys:
            d[k] = round(d[k] + r.nutrients.get(k, 0), 1)
    latest = db.scalar(select(DietPlan).where(DietPlan.user_id == user.id).order_by(DietPlan.created_at.desc()).limit(1))
    logged = [d for d in days.values() if d["meals"]]
    avg = {k: round(sum(d[k] for d in logged) / len(logged), 1) for k in keys} if logged else None
    return {"week_start": week_start.isoformat(), "days": days, "average_logged_day": avg, "targets": latest.targets if latest else None, "days_logged": len(logged)}


# ------------------------------------------------------------------ feedback & favourites
class FeedbackIn(BaseModel):
    rating: Literal[-1, 0, 1] = 0
    favorite: bool = False


@router.put("/feedback/{dish_key}")
def put_feedback(dish_key: str, body: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if dish_key not in svc.foods()["dishes"]:
        raise _err(422, "unknown_dish")
    rec = db.get(FoodFeedback, (user.id, dish_key))
    if rec is None:
        rec = FoodFeedback(user_id=user.id, dish_key=dish_key)
        db.add(rec)
    rec.rating, rec.favorite = body.rating, body.favorite
    db.commit()
    return {"dish_key": dish_key, "rating": rec.rating, "favorite": rec.favorite}


@router.get("/feedback")
def get_feedback(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(FoodFeedback).where(FoodFeedback.user_id == user.id)).all()
    return {r.dish_key: {"rating": r.rating, "favorite": r.favorite} for r in rows}
