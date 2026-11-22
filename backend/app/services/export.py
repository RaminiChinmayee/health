"""Personal-data export and file cleanup.

Each feature module registers an exporter (and optionally a file-cleanup hook) so the export
always covers every table that holds user data.
"""
import shutil
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AccountSecurityEvent, User
from app.services.users import user_out

Exporter = Callable[[Session, User], object]
_exporters: dict[str, Exporter] = {}


def register_exporter(name: str, fn: Exporter) -> None:
    _exporters[name] = fn


def collect_user_export(db: Session, user: User) -> dict:
    hp = user.health_profile
    out: dict = {
        "account": user_out(user).model_dump(),
        "health_profile": None
        if hp is None
        else {
            "height_cm": hp.height_cm,
            "weight_kg": hp.weight_kg,
            "bmi": hp.bmi,
            "activity_level": hp.activity_level,
            "dietary_preference": hp.dietary_preference,
            "food_allergies": hp.food_allergies,
            "health_conditions": hp.health_conditions,
            "emergency_contact_name": hp.emergency_contact_name,
            "emergency_contact_phone": hp.emergency_contact_phone,
            "preferred_units": hp.preferred_units,
        },
        "linked_accounts": [
            {"provider": a.provider, "email": a.provider_email, "linked_at": a.created_at} for a in user.oauth_accounts
        ],
        "security_events": [
            {"event_type": e.event_type, "created_at": e.created_at, "ip_address": e.ip_address}
            for e in db.scalars(select(AccountSecurityEvent).where(AccountSecurityEvent.user_id == user.id)).all()
        ],
    }
    for name, fn in _exporters.items():
        out[name] = fn(db, user)
    return out


def delete_user_files(user: User) -> None:
    """Remove every private file stored for the user (avatars, uploads, audio)."""
    root = get_settings().storage_dir.resolve()
    for sub in ("avatars", "uploads", "audio"):
        d = (root / sub / str(user.id)).resolve()
        if root in d.parents and d.exists():
            shutil.rmtree(d)
