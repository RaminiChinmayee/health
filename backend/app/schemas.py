"""Pydantic request/response models for auth and profile."""
import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models import SUPPORTED_LANGUAGES

LanguageCode = Literal["en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "or", "ml"]
assert set(LanguageCode.__args__) == set(SUPPORTED_LANGUAGES)

Gender = Literal["female", "male", "other", "prefer_not_to_say"]
ActivityLevel = Literal["sedentary", "light", "moderate", "active", "very_active"]
DietaryPreference = Literal["vegetarian", "vegan", "eggetarian", "non_vegetarian", "jain", "other"]

_PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,20}$")


def _clean_phone(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    v = v.strip()
    if not _PHONE_RE.match(v):
        raise ValueError("invalid_phone")
    return v


def _check_dob(v: date | None) -> date | None:
    if v is None:
        return v
    today = date.today()
    if v > today:
        raise ValueError("dob_in_future")
    if (today.year - v.year) > 120:
        raise ValueError("dob_too_old")
    return v


# ------------------------------------------------------------------ auth
class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str | None = None
    password: str = Field(max_length=128)
    confirm_password: str
    date_of_birth: date
    gender: Gender | None = None
    accept_terms: bool
    language: LanguageCode = "en"

    _phone = field_validator("phone")(_clean_phone)
    _dob = field_validator("date_of_birth")(_check_dob)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("name_too_short")
        return v

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, v: bool) -> bool:
        if not v:
            raise ValueError("terms_required")
        return v

    @model_validator(mode="after")
    def _match(self):
        if self.password != self.confirm_password:
            raise ValueError("passwords_do_not_match")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
    remember_me: bool = False


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(max_length=128)
    confirm_password: str

    @model_validator(mode="after")
    def _match(self):
        if self.password != self.confirm_password:
            raise ValueError("passwords_do_not_match")
        return self


class ChangePasswordIn(BaseModel):
    current_password: str | None = None  # absent for Google-only accounts setting a first password
    new_password: str = Field(max_length=128)
    confirm_password: str

    @model_validator(mode="after")
    def _match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("passwords_do_not_match")
        return self


class ChangeEmailIn(BaseModel):
    new_email: EmailStr
    current_password: str | None = None


class AccessTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class MessageOut(BaseModel):
    code: str
    detail: str | None = None
    email_delivery: Literal["sent", "not_configured", "failed"] | None = None


# ------------------------------------------------------------------ profile
class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool
    full_name: str
    phone: str | None
    date_of_birth: date | None
    age: int | None
    gender: str | None
    has_avatar: bool
    has_password: bool
    auth_methods: list[str]
    ui_language: str
    chatbot_language: str
    created_at: datetime
    needs_onboarding: bool


class ProfileUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    accept_terms: bool | None = None  # used by Google sign-up onboarding

    _phone = field_validator("phone")(_clean_phone)
    _dob = field_validator("date_of_birth")(_check_dob)


class HealthProfileIn(BaseModel):
    height_cm: float | None = Field(default=None, gt=40, lt=260)
    weight_kg: float | None = Field(default=None, gt=2, lt=400)
    activity_level: ActivityLevel | None = None
    dietary_preference: DietaryPreference | None = None
    food_allergies: list[str] = Field(default_factory=list, max_length=50)
    health_conditions: list[str] = Field(default_factory=list, max_length=50)
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = None
    preferred_units: Literal["metric", "imperial"] = "metric"

    _phone = field_validator("emergency_contact_phone")(_clean_phone)

    @field_validator("food_allergies", "health_conditions")
    @classmethod
    def _items(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v:
            item = " ".join(item.split())[:100]
            if item and item.lower() not in {o.lower() for o in out}:
                out.append(item)
        return out


class HealthProfileOut(HealthProfileIn):
    age: int | None
    bmi: float | None
    bmi_category: str | None
    updated_at: datetime | None


class LanguageIn(BaseModel):
    ui_language: LanguageCode
    chatbot_language: LanguageCode | None = None  # defaults to ui_language


class NotificationPrefsIn(BaseModel):
    email_security_alerts: bool = True
    email_health_reminders: bool = False
    email_product_updates: bool = False


class DeleteAccountIn(BaseModel):
    # Password for password accounts; for Google-only accounts the user types their email.
    current_password: str | None = None
    confirm_email: str | None = None


class SessionOut(BaseModel):
    family_id: uuid.UUID
    created_at: datetime
    last_used_at: datetime | None
    user_agent: str | None
    ip_address: str | None
    current: bool


AccessTokenOut.model_rebuild()
