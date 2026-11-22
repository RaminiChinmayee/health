"""User health records: predictions, diet plans, meal logs, food feedback."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


class Prediction(Base):
    """One saved model output. Stored exactly as shown to the user at that time, including the
    model version and the safety information displayed; never re-labelled as a diagnosis."""

    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_user_created", "user_id", "created_at"),
        Index("ix_predictions_user_type", "user_id", "prediction_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    # symptoms | diabetes | diabetes_symptoms | heart | kidney | lung | parkinsons | image
    prediction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    model_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Headline number for sorting/filtering/comparison: calibrated probability (binary models)
    # or top match score (symptom checker).
    score: Mapped[float | None] = mapped_column(Float)
    label: Mapped[str | None] = mapped_column(String(64))  # e.g. risk band or top disease key
    contributions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    safety: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DietPlan(Base):
    __tablename__ = "diet_plans"
    __table_args__ = (Index("ix_diet_plans_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)  # profile snapshot + goal used
    targets: Mapped[dict] = mapped_column(JSONB, nullable=False)  # kcal & macro targets
    plan: Mapped[dict] = mapped_column(JSONB, nullable=False)  # days → meals → dishes
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MealLog(Base):
    """A meal the user marked as eaten (completed meals / daily nutrition records)."""

    __tablename__ = "meal_logs"
    __table_args__ = (Index("ix_meal_logs_user_date", "user_id", "log_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = _user_fk()
    plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("diet_plans.id", ondelete="SET NULL"))
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    slot: Mapped[str] = mapped_column(String(16), nullable=False)  # breakfast|lunch|snack|dinner
    dish_key: Mapped[str] = mapped_column(String(64), nullable=False)
    servings: Mapped[float] = mapped_column(Float, nullable=False)
    nutrients: Mapped[dict] = mapped_column(JSONB, nullable=False)  # computed at log time
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FoodFeedback(Base):
    """Per-dish preference. Disliked dishes are avoided in future plans; favourites preferred."""

    __tablename__ = "food_feedback"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    dish_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    rating: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)  # -1 dislike, 0 neutral, 1 like
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
