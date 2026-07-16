"""Password hashing, JWT, OTP helpers.

หมายเหตุ: ใช้ bcrypt โดยตรง (ไม่ผ่าน passlib) เพราะ passlib 1.7.4 + bcrypt 5.0
เข้ากันไม่ได้ (passlib อ่าน bcrypt.__about__ ที่ถูกลบใน bcrypt 4+) → error fatal
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt รับ input ได้สูงสุด 72 bytes — schema จำกัดความยาว password ไว้แล้ว
_BCRYPT_MAX_BYTES = 72


def _to_bcrypt_bytes(value: str) -> bytes:
    return value.encode("utf-8")[:_BCRYPT_MAX_BYTES]


# ---- Password ----
def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---- OTP ----
def generate_otp() -> str:
    """สุ่ม OTP 6 หลักแบบ cryptographically secure."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_bytes(code), bcrypt.gensalt()).decode("utf-8")


def verify_otp_hash(code: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(code), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---- Refresh token hashing (deterministic — ใช้ lookup ใน refresh_tokens.token_hash) ----
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---- JWT ----
def _create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        # jti กัน token ซ้ำกัน byte-ต่อ-byte เมื่อออกให้ user เดียวกัน 2 ครั้งในวินาทีเดียวกัน
        # (iat ถูก truncate เป็นวินาที — ไม่มี jti จะทำให้ sha256(token) ชนกัน แล้ว insert
        # ลง refresh_tokens.token_hash UNIQUE พังด้วย IntegrityError)
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(
        str(user_id),
        "access",
        timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: str) -> tuple[str, datetime]:
    """คืน (token, expires_at) — service เก็บ hash ของ token ลง refresh_tokens."""
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_EXPIRE_DAYS
    )
    token = _create_token(
        str(user_id),
        "refresh",
        timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
    )
    return token, expires_at


def decode_token(token: str) -> dict:
    """decode + verify signature/exp — raise JWTError ถ้าไม่ถูกต้อง/หมดอายุ."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


__all__ = [
    "hash_password",
    "verify_password",
    "generate_otp",
    "hash_otp",
    "verify_otp_hash",
    "hash_token",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "JWTError",
]
