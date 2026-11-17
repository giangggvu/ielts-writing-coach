from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import get_settings

_hasher = PasswordHasher()
ALGORITHM = "HS256"

# Hash used when the email does not exist, so login takes the same time either way.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
