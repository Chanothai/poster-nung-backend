"""Business logic ของ F1 Authentication — register / verify-otp / login / refresh /
google_login (social)."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.exceptions import (
    AccountAlreadyVerified,
    AccountNotVerified,
    EmailAlreadyRegistered,
    InvalidCredentials,
    OAuthEmailNotVerified,
    OAuthLoginConflict,
    OAuthProviderNotConfigured,
    OAuthTokenInvalid,
    OtpExpired,
    OtpInvalid,
    OtpLocked,
    RefreshTokenInvalid,
    UserNotFound,
)
from app.models.enums import OAuthProvider
from app.models.user import User
from app.repositories import (
    oauth_identity_repository,
    otp_repository,
    refresh_token_repository,
    user_repository,
)
from app.schemas.auth import (
    GoogleLoginRequest,
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
    if user is None or user.hashed_password is None:
        # user ไม่มี หรือสมัครผ่าน social login อย่างเดียว (ไม่มีรหัสผ่านตั้งไว้) —
        # verify กับ dummy hash เสมอให้เสีย bcrypt cost เท่ากัน กัน timing attack
        # ที่ใช้เดาว่า email มีในระบบไหม/ใช้ auth method ไหน (user enumeration)
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


async def google_login(
    session: AsyncSession, data: GoogleLoginRequest
) -> TokenResponse:
    """Mobile login ผ่าน Google — client sign-in ด้วย Google ผ่าน Firebase Auth แล้ว
    ส่ง Firebase ID token มา backend verify แล้ว find-or-create user + ออก JWT ชุด
    เดียวกับ login ปกติ."""
    if not settings.FIREBASE_PROJECT_ID:
        raise OAuthProviderNotConfigured()

    try:
        # verify_firebase_token เป็น blocking call (fetch Google public certs ผ่าน HTTP)
        # ต้องรันใน thread แยกกัน block event loop หลักของ FastAPI
        # audience = Firebase project id → เช็ค aud + iss (securetoken.google.com/<project>)
        payload = await asyncio.to_thread(
            google_id_token.verify_firebase_token,
            data.id_token,
            google_requests.Request(),
            settings.FIREBASE_PROJECT_ID,
        )
    except ValueError:
        # ครอบคลุมทั้ง signature ผิด, หมดอายุ, audience/issuer ไม่ตรง — google-auth
        # library ใช้ ValueError เดียวสำหรับ token ที่ verify ไม่ผ่านทุกกรณี
        raise OAuthTokenInvalid()

    if not payload.get("email_verified", False):
        # ไม่เชื่อ email ที่ยังไม่ยืนยัน — กันเอา email มั่วมาผูกกับบัญชีคนอื่น
        raise OAuthEmailNotVerified()

    # sub ของ Firebase token = Firebase uid (stable ต่อ user ใน project) — ใช้เป็น key
    # เก็บใน provider_user_id. provider คงเป็น google (sign-in method ตอนนี้มีแค่ Google) —
    # ถ้าเพิ่ม Firebase sign-in provider อื่นภายหลัง ค่อยทบทวน key/provider
    provider_user_id: str = payload["sub"]
    email: str = payload["email"]

    identity = await oauth_identity_repository.get_by_provider_user_id(
        session, provider=OAuthProvider.google, provider_user_id=provider_user_id
    )
    if identity is not None:
        user = await session.get(User, identity.user_id)
        if user is None:
            # ไม่ควรเกิด (FK CASCADE ลบคู่กันเสมอ) — กันไว้เผื่อ data ผิดปกติ
            raise OAuthLoginConflict()
        return await _issue_and_store_tokens(session, user)

    # ยังไม่เคย link Google account นี้มาก่อน — หา user เดิมจาก email (auto-link ถ้า
    # Google ยืนยัน email แล้ว) หรือสร้างใหม่ (social-only, ไม่มีรหัสผ่าน)
    try:
        async with session.begin_nested():  # savepoint กันแพ้ race ทำ transaction หลักพัง
            user = await user_repository.get_by_email(session, email)
            if user is None:
                user = await user_repository.create(
                    session, email=email, hashed_password=None
                )
            if not user.is_verified:
                await user_repository.set_verified(session, user.id)
                user.is_verified = True

            await oauth_identity_repository.create(
                session,
                user_id=user.id,
                provider=OAuthProvider.google,
                provider_user_id=provider_user_id,
                email=email,
            )
    except IntegrityError:
        # แพ้ race: อีก request login Google account เดียวกันพร้อมกัน สร้าง
        # user/identity ไปก่อน — savepoint rollback แล้ว ลองอ่านซ้ำครั้งเดียว
        identity = await oauth_identity_repository.get_by_provider_user_id(
            session, provider=OAuthProvider.google, provider_user_id=provider_user_id
        )
        if identity is None:
            raise OAuthLoginConflict()
        user = await session.get(User, identity.user_id)
        if user is None:
            raise OAuthLoginConflict()

    return await _issue_and_store_tokens(session, user)
