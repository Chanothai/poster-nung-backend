"""Pydantic v2 schemas สำหรับ F1 Authentication (ตรง docs/openapi.yaml)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---- Requests ----
class RegisterRequest(BaseModel):
    email: EmailStr
    # bcrypt รับได้สูงสุด 72 bytes → จำกัด max_length กัน truncate เงียบ
    password: str = Field(min_length=8, max_length=72)
    phone: str | None = Field(default=None, max_length=20)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


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
