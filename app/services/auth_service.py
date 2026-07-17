"""Business logic ของ F1 Authentication — register / verify-otp / login / refresh."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.exceptions import (
    AccountAlreadyVerified,
    AccountNotVerified,
    EmailAlreadyRegistered,
    InvalidCredentials,
    OtpExpired,
    OtpInvalid,
    OtpLocked,
    RefreshTokenInvalid,
    UserNotFound,
)
from app.models.user import User
from app.repositories import otp_repository, refresh_token_repository, user_repository
from app.schemas.auth import (
    LoginRequest,
    OTPVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)

OTP_EXPIRE_MINUTES = 10


async def register(session: AsyncSession, data: RegisterRequest) -> tuple[User, str]:
    """สมัครสมาชิก → คืน (user, plain_otp) ให้ caller ตัดสินใจว่าจะ expose otp หรือไม่."""
    existing = await user_repository.get_by_email(session, data.email)
    if existing is not None:
        raise EmailAlreadyRegistered()

    hashed = security.hash_password(data.password)
    try:
        user = await user_repository.create(
            session, email=data.email, hashed_password=hashed, phone=data.phone
        )
    except IntegrityError:
        # แพ้ race: อีก request สมัคร email เดียวกันพร้อมกัน แล้ว commit ก่อน
        # (pre-check ผ่านทั้งคู่) → unique violation. คืน 409 เดียวกัน ไม่ใช่ 500
        raise EmailAlreadyRegistered()

    plain_otp = security.generate_otp()
    await otp_repository.create_otp(
        session,
        user_id=user.id,
        code_hash=security.hash_otp(plain_otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES),
    )

    return user, plain_otp


async def _issue_and_store_tokens(session: AsyncSession, user: User) -> TokenResponse:
    access_token = security.create_access_token(str(user.id))
    refresh_token, expires_at = security.create_refresh_token(str(user.id))
    await refresh_token_repository.store(
        session,
        user_id=user.id,
        token_hash=security.hash_token(refresh_token),
        expires_at=expires_at,
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


async def verify_otp(session: AsyncSession, data: OTPVerifyRequest) -> TokenResponse:
    user = await user_repository.get_by_email(session, data.email)
    if user is None:
        raise UserNotFound()

    if user.is_verified:
        raise AccountAlreadyVerified()

    otp = await otp_repository.get_latest_active(session, user.id)
    if otp is None:
        # ไม่มี OTP ที่ยัง active เลย (ไม่เคยขอ/ใช้ไปแล้วก่อนหน้า) — ปฏิบัติเหมือนกรอกผิด
        raise OtpInvalid()

    # ครบ threshold ผิด 5 ครั้งของโค้ดเดียว → invalidate โค้ดนั้น บังคับขอใหม่
    if otp.attempt_count >= settings.OTP_MAX_ATTEMPTS:
        await otp_repository.mark_consumed(session, otp.id)
        raise OtpLocked()

    if otp.expires_at < datetime.now(timezone.utc):
        raise OtpExpired()

    if not security.verify_otp_hash(data.code, otp.code_hash):
        await otp_repository.increment_attempt(session, otp.id)
        raise OtpInvalid()

    await otp_repository.mark_consumed(session, otp.id)
    await user_repository.set_verified(session, user.id)
    user.is_verified = True  # sync in-memory ให้ _issue_and_store_tokens ใช้ค่าล่าสุด

    return await _issue_and_store_tokens(session, user)


async def login(session: AsyncSession, data: LoginRequest) -> TokenResponse:
    user = await user_repository.get_by_email(session, data.email)
    if user is None:
        # verify กับ dummy hash ให้เสีย bcrypt cost เท่ากับเคส password ผิด
        # กัน timing attack ที่ใช้เดาว่า email มีในระบบหรือไม่ (user enumeration)
        security.verify_password(data.password, security.DUMMY_PASSWORD_HASH)
        raise InvalidCredentials()

    # ข้อความเดียวกันทั้ง "ไม่มี email" และ "password ผิด" — กัน user enumeration
    if not security.verify_password(data.password, user.hashed_password):
        raise InvalidCredentials()

    if not user.is_verified:
        raise AccountNotVerified()

    return await _issue_and_store_tokens(session, user)


async def refresh_token(session: AsyncSession, data: RefreshRequest) -> TokenResponse:
    try:
        payload = security.decode_token(data.refresh_token)
    except security.JWTError:
        raise RefreshTokenInvalid()

    if payload.get("type") != "refresh":
        raise RefreshTokenInvalid()

    token_hash = security.hash_token(data.refresh_token)
    stored = await refresh_token_repository.get_active(session, token_hash)
    if stored is None:
        raise RefreshTokenInvalid()

    try:
        user_id = uuid.UUID(payload.get("sub"))
    except (TypeError, ValueError):
        raise RefreshTokenInvalid()
    user = await session.get(User, user_id)
    if user is None:
        raise RefreshTokenInvalid()

    # rotate: revoke token เก่า ออกชุดใหม่
    await refresh_token_repository.revoke(session, token_hash)
    return await _issue_and_store_tokens(session, user)
