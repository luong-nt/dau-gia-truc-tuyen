"""Băm mật khẩu (Argon2) và tạo/giải mã JWT (NFR-04)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_password_hash = PasswordHash.recommended()


def hash_password(raw_password: str) -> str:
    return _password_hash.hash(raw_password)


def verify_password(raw_password: str, hashed: str) -> bool:
    return _password_hash.verify(raw_password, hashed)


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Giải mã token. Ném jwt.ExpiredSignatureError / jwt.PyJWTError nếu không hợp lệ."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
