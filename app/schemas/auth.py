"""Pydantic v2 schemas สำหรับ F1 Authentication (ตรง docs/openapi.yaml)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# bcrypt ตัด input ที่ยาวเกิน 72 bytes ทิ้งเงียบ ๆ → password ที่ต่างกันหลัง byte ที่ 72
# จะได้ hash เดียวกัน; max_length นับ "ตัวอักษร" ไม่ใช่ byte (ไทย 1 ตัว = 3 bytes)
# จึงต้องเช็ค byte length เองกัน multibyte password ทะลุ limit โดยไม่รู้ตัว
_BCRYPT_MAX_BYTES = 72


def _validate_password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        raise ValueError(f"password ต้องไม่เกิน {_BCRYPT_MAX_BYTES} bytes (UTF-8)")
    return value


# ---- Requests ----
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    phone: str | None = Field(default=None, max_length=20)

    _check_password_bytes = field_validator("password")(_validate_password_bytes)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    _check_password_bytes = field_validator("password")(_validate_password_bytes)


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    # OTP เป็นตัวเลข 6 หลักเสมอ (generate_otp คืน 6 digit) — บังคับ numeric กัน input มั่ว
    code: str = Field(pattern=r"^\d{6}$")


class RefreshRequest(BaseModel):
    refresh_token: str


# ---- Responses ----
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    phone: str | None
    is_verified: bool
    created_at: datetime


class RegisterResponse(UserResponse):
    # populate เฉพาะตอน DEBUG=true — production เป็น None เสมอ (ไม่ log OTP)
    dev_otp: str | None = None


# ---- Error envelope (สำหรับ OpenAPI docs) ----
class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: list[dict] | None = None
