import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.routers import auth, chat, dashboard, diet, history, hospitals, predict, profile
from app.services import exporters  # noqa: F401  (registers data-export sections)

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(
    title="HealthAssist AI API",
    version="0.1.0",
    docs_url=None if settings.environment == "production" else "/api/docs",
    openapi_url=None if settings.environment == "production" else "/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-HealthAI-CSRF", "Accept-Language"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/api/") and "Cache-Control" not in resp.headers:
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Uniform validation errors: {"detail": {"code": "validation_error", "fields": {field: code}}}.
    Field codes are translation keys on the frontend."""
    fields: dict[str, str] = {}
    for e in exc.errors():
        loc = [str(p) for p in e["loc"] if p not in ("body", "query", "path")]
        key = ".".join(loc) or "_form"
        msg = str(e.get("ctx", {}).get("error", "")) or e["type"]
        # Our validators raise ValueError("code"); pydantic built-ins use their type name.
        fields[key] = msg if msg.replace("_", "").isalpha() else e["type"]
    return JSONResponse(status_code=422, content={"detail": {"code": "validation_error", "fields": fields}})


def _register_image_models() -> None:
    """Record each deployed image model version in image_model_metadata."""
    from sqlalchemy import select as _select

    from app.db import SessionLocal
    from app.models import ImageModelMetadata
    from app.services import skin

    c = skin.card()
    if c is None:
        return
    with SessionLocal() as db:
        exists = db.scalar(_select(ImageModelMetadata).where(ImageModelMetadata.model_key == "skin", ImageModelMetadata.version == c["version"]))
        if exists is None:
            from datetime import datetime

            db.add(ImageModelMetadata(model_key="skin", version=c["version"], category="skin_lesion_dermatoscopic", architecture=c["architecture"],
                                      classes=c["classes"], metrics={k: v for k, v in c["evaluation"]["test"].items() if k != "confusion_matrix"},
                                      dataset={k: c["dataset"][k] for k in ("name", "source", "license", "population")},
                                      trained_at=datetime.fromisoformat(c["trained_at"])))
            db.commit()


@app.on_event("startup")
def _warm_up() -> None:
    """Load the embedding model and knowledge base in the background so the first chat message
    doesn't wait ~15 s."""
    import threading

    def load():
        try:
            from app.services import embeddings, knowledge

            embeddings.embed_queries(["warm up"])
            if knowledge.kb_available():
                knowledge._kb()
            _register_image_models()
            from app.services import skin

            if skin.available():
                skin.load()  # ~3 s; otherwise the first image upload waits for it
            from app.services import places

            places.local_index()  # facility extract for instant hospital search
        except Exception:  # never block startup
            logging.getLogger("healthai").exception("warm-up failed")

    if settings.environment != "test":
        threading.Thread(target=load, daemon=True).start()


@app.get("/api/health")
def health():
    with engine.connect() as c:
        c.execute(text("select 1"))
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(predict.router)
app.include_router(history.router)
app.include_router(hospitals.router)
app.include_router(diet.router)
app.include_router(chat.router)
app.include_router(dashboard.router)
