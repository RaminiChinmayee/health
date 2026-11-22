from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    NotificationPreference,
    User,
    UserHealthProfile,
    UserLanguagePreference,
)
from app.schemas import UserOut


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def age_from_dob(dob: date | None) -> int | None:
    if dob is None:
        return None
    t = date.today()
    return t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))


def bmi_category(bmi: float | None) -> str | None:
    # WHO adult categories. Not meaningful for children; the UI says so.
    if bmi is None:
        return None
    if bmi < 18.5:
        return "underweight"
    if bmi < 25:
        return "normal"
    if bmi < 30:
        return "overweight"
    return "obese"


def ensure_user_rows(db: Session, user: User, language: str = "en") -> None:
    """Create the 1:1 preference rows every user has."""
    if user.language_preference is None:
        user.language_preference = UserLanguagePreference(ui_language=language, chatbot_language=language)
    if user.health_profile is None:
        user.health_profile = UserHealthProfile(food_allergies=[], health_conditions=[])
    if user.notification_preference is None:
        user.notification_preference = NotificationPreference()


def user_out(user: User) -> UserOut:
    methods = []
    if user.password_hash:
        methods.append("password")
    methods += sorted({a.provider for a in user.oauth_accounts})
    lang = user.language_preference
    return UserOut(
        id=user.id,
        email=user.email,
        email_verified=user.is_verified,
        full_name=user.full_name,
        phone=user.phone,
        date_of_birth=user.date_of_birth,
        age=age_from_dob(user.date_of_birth),
        gender=user.gender,
        has_avatar=bool(user.avatar_path),
        has_password=bool(user.password_hash),
        auth_methods=methods,
        ui_language=lang.ui_language if lang else "en",
        chatbot_language=lang.chatbot_language if lang else "en",
        created_at=user.created_at,
        needs_onboarding=user.terms_accepted_at is None or user.date_of_birth is None,
    )
