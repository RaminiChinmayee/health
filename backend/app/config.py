"""Application settings, loaded from environment variables / backend/.env."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+psycopg://healthai@127.0.0.1:5432/healthai"

    # URLs
    # Public origin of the app. The API is served under {frontend_url}/api (Vite proxy in dev,
    # reverse proxy in production), so cookies are first-party.
    frontend_url: str = "http://localhost:5173"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # JWT access tokens (short-lived) — refresh tokens are opaque and stored hashed.
    jwt_secret: str = Field(default="CHANGE-ME-dev-only-secret-at-least-32-bytes!!", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days_remember: int = 30
    refresh_token_hours_session: int = 24

    # Token lifetimes
    email_verification_hours: int = 24
    password_reset_minutes: int = 30

    # Rate limits (count per window)
    login_max_attempts: int = 10
    login_window_minutes: int = 15
    register_max_per_hour_per_ip: int = 10
    resend_verification_max_per_hour: int = 3
    reset_max_requests: int = 3
    reset_window_minutes: int = 60

    # Email: "smtp" sends real mail; "console" logs messages (development only).
    email_backend: Literal["smtp", "console"] = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True  # STARTTLS
    smtp_use_ssl: bool = False  # implicit TLS (port 465)
    email_from: str = "HealthAssist AI <no-reply@localhost>"

    # Google OAuth 2.0
    google_client_id: str = ""
    google_client_secret: str = ""

    # Google Gemini (chatbot, transcription, speech, embeddings)
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-3.5-flash"
    gemini_fast_model: str = "gemini-3.5-flash-lite"
    # Used when the main chat model is overloaded or rate-limited (before any text has streamed).
    gemini_chat_fallback_models: list[str] = Field(default_factory=lambda: ["gemini-3.5-flash-lite"])
    # Tried in order; the dedicated model has a small free-tier daily quota (25), so a general
    # multimodal model is the fallback.
    gemini_transcribe_models: list[str] = Field(default_factory=lambda: ["gemini-3.5-transcribe", "gemini-3.5-flash-lite"])
    gemini_tts_model: str = "gemini-3.8-flash-tts"
    gemini_embed_model: str = "gemini-embedding-2"
    # Local embedding model for retrieval (no API quota).
    embedding_model: str = "intfloat/multilingual-e5-small"
    max_audio_bytes: int = 10 * 1024 * 1024
    max_audio_seconds: int = 120
    # Health-context memories expire unless re-confirmed (declared retention policy).
    health_memory_retention_days: int = 365

    # Trained model artifacts (ml/artifacts/<key>/<version>/{model.joblib,card.json})
    model_dir: Path = BACKEND_DIR.parent / "ml" / "artifacts"

    # Hospital finder (OpenStreetMap). Public Overpass servers are tried in order.
    overpass_urls: list[str] = Field(default_factory=lambda: [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ])
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    # OSM usage policies require an identifying User-Agent with contact details for production.
    osm_user_agent: str = "HealthAssistAI/0.1 (development)"

    # Private file storage (avatars, uploads). Never served statically.
    storage_dir: Path = BACKEND_DIR / "storage"
    max_avatar_bytes: int = 2 * 1024 * 1024

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.frontend_url}/api/auth/google/callback"

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
