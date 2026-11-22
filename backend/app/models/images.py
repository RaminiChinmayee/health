"""Medical image analysis records and the image-model registry."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ImageModelMetadata(Base):
    """One row per deployed image model version (registered from its model card)."""

    __tablename__ = "image_model_metadata"
    __table_args__ = (UniqueConstraint("model_key", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_key: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "skin"
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "skin_lesion_dermatoscopic"
    architecture: Mapped[str] = mapped_column(String(200), nullable=False)
    classes: Mapped[list] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dataset: Mapped[dict] = mapped_column(JSONB, nullable=False)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MedicalImageAnalysis(Base):
    __tablename__ = "medical_image_analysis"
    __table_args__ = (Index("ix_image_analysis_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"))
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_attachments.id", ondelete="SET NULL"))
    model_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    # ok | rejected_not_skin | rejected_out_of_distribution | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    predicted_class: Mapped[str | None] = mapped_column(String(32))
    probability: Mapped[float | None] = mapped_column(Float)  # calibrated probability of the top class
    probabilities: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    ood_distance: Mapped[float | None] = mapped_column(Float)
    gate: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # vision-model check result
    question: Mapped[str | None] = mapped_column(Text)
    safety: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
