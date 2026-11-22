"""Register every user-data table with the personal-data export."""
from sqlalchemy import select

from app.models import MedicalImageAnalysis, ChatMessage, Conversation, ConversationSummary, DietPlan, FoodFeedback, MealLog, Prediction, UserChatMemory, VoiceTranscription
from app.services.export import register_exporter


def _rows(model, cols):
    def fn(db, user):
        return [{c: getattr(r, c) for c in cols} for r in db.scalars(select(model).where(model.user_id == user.id)).all()]
    return fn


register_exporter("predictions", _rows(Prediction, ["id", "prediction_type", "model_key", "model_version", "inputs", "result", "score", "label", "contributions", "safety", "created_at"]))
register_exporter("diet_plans", _rows(DietPlan, ["id", "title", "inputs", "targets", "plan", "is_favorite", "created_at"]))
register_exporter("meal_logs", _rows(MealLog, ["id", "plan_id", "log_date", "slot", "dish_key", "servings", "nutrients", "note", "created_at"]))
register_exporter("food_feedback", _rows(FoodFeedback, ["dish_key", "rating", "favorite", "updated_at"]))
register_exporter("conversations", _rows(Conversation, ["id", "title", "reply_language", "message_count", "created_at", "last_message_at"]))
register_exporter("chat_messages", _rows(ChatMessage, ["id", "conversation_id", "role", "message_type", "content", "detected_language", "reply_language", "citations", "created_at"]))
register_exporter("chat_memories", _rows(UserChatMemory, ["id", "category", "content", "status", "source", "expires_at", "created_at"]))
register_exporter("conversation_summaries", _rows(ConversationSummary, ["id", "conversation_id", "summary", "messages_covered", "created_at"]))
register_exporter("voice_transcriptions", _rows(VoiceTranscription, ["id", "conversation_id", "language_hint", "detected_language", "transcript", "duration_seconds", "status", "created_at"]))
register_exporter("image_analyses", _rows(MedicalImageAnalysis, ["id", "conversation_id", "model_key", "model_version", "status", "predicted_class", "probability", "probabilities", "gate", "question", "created_at"]))
