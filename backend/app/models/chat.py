"""Chatbot tables: conversations, messages, memory, summaries, attachments, transcriptions."""
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _user() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ChatPreference(Base):
    """Per-user consent for long-term memory. Off by default."""

    __tablename__ = "chat_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    memory_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Allow the assistant to see the user's health profile and saved prediction results.
    use_profile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    response_style: Mapped[str] = mapped_column(String(16), default="balanced", nullable=False)  # brief|balanced|detailed
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_last", "user_id", "last_message_at"),)

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _user()
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    title_is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reply_language: Mapped[str | None] = mapped_column(String(8))  # overrides the profile setting
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = _created()
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Embedding of title + latest summary, for retrieving relevant past conversations.
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_conv_created", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = _pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = _user()
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    # text | voice (transcribed speech) | image (phase 5)
    message_type: Mapped[str] = mapped_column(String(16), default="text", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    detected_language: Mapped[str | None] = mapped_column(String(8))
    reply_language: Mapped[str | None] = mapped_column(String(8))
    # Assistant only: sources actually cited, with their numbers as shown.
    citations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    safety: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    model: Mapped[str | None] = mapped_column(String(64))
    usage: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="complete", nullable=False)  # complete | failed
    created_at: Mapped[datetime] = _created()


class ConversationSummary(Base):
    """Generated summary of older messages, used instead of resending the full history."""

    __tablename__ = "conversation_summaries"

    id: Mapped[uuid.UUID] = _pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = _user()
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    messages_covered: Mapped[int] = mapped_column(Integer, nullable=False)
    covers_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()


class UserChatMemory(Base):
    __tablename__ = "user_chat_memories"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _user()
    # language | diet | allergy | meal_preference | health_context | response_style | other
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    # active | pending (awaiting the user's confirmation) | disabled
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="user_added", nullable=False)  # user_added | extracted
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ChatAttachment(Base):
    """Private file attached to a conversation (voice recordings now; images in phase 5)."""

    __tablename__ = "chat_attachments"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _user()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # audio | image
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)  # relative to private storage
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _created()


class VoiceTranscription(Base):
    __tablename__ = "voice_transcription_history"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _user()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"))
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_attachments.id", ondelete="SET NULL"))
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    language_hint: Mapped[str | None] = mapped_column(String(8))
    detected_language: Mapped[str | None] = mapped_column(String(8))
    transcript: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok | failed | empty
    error: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created()
