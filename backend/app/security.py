"""Password hashing, password strength, opaque tokens and JWT access tokens."""
import hashlib
import re
import secrets
import uuid
from datetime import timezone, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from zxcvbn import zxcvbn

from app.config import get_settings

_hasher = PasswordHasher()  # Argon2id with library defaults (RFC 9106 low-memory profile)

# A valid hash to verify against when the user doesn't exist, so response time
# doesn't reveal whether an email is registered.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problems(password: str, user_inputs: list[str] | None = None) -> list[str]:
    """Return a list of machine-readable problem codes; empty means acceptable.

    Codes are translated on the frontend.
    """
    problems: list[str] = []
    if len(password) < 10:
        problems.append("password_too_short")
    if len(password) > 128:
        problems.append("password_too_long")
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        problems.append("password_needs_variety")
    if not problems:
        # Penalize passwords built from the user's own name/email/birth year, including
        # concatenations like "asharao".
        tokens: set[str] = set()
        for raw in user_inputs or []:
            if not raw:
                continue
            parts = [p for p in re.split(r"[\s@._+-]+", str(raw).lower()) if len(p) >= 2]
            tokens.update(parts)
            if len(parts) > 1:
                tokens.add("".join(parts))
        # zxcvbn only looks at the first 72 chars to bound cost.
        score = zxcvbn(password[:72], user_inputs=sorted(tokens))["score"]
        if score < 3:
            problems.append("password_too_guessable")
    return problems


# ---------------------------------------------------------------- opaque tokens
def new_token() -> str:
    """256-bit URL-safe random token, sent to the user. Only its hash is stored."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_subject(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


# ---------------------------------------------------------------- JWT access tokens
def create_access_token(user_id: uuid.UUID, session_family: uuid.UUID) -> str:
    s = get_settings()
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "sid": str(session_family),
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
        "typ": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    s = get_settings()
    payload = jwt.decode(
        token, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub", "sid"]}
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload
