"""Thin controller ของ F1 Authentication — ห้ามมี DB query ตรงนี้ เรียก service ล้วน."""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    OTPVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    data: RegisterRequest, session: AsyncSession = Depends(get_db)
) -> RegisterResponse:
    user, plain_otp = await auth_service.register(session, data)
    await session.commit()
    return RegisterResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        is_verified=user.is_verified,
        created_at=user.created_at,
        dev_otp=plain_otp if settings.DEBUG else None,
    )


@router.post("/verify-otp", response_model=TokenResponse)
# callable — slowapi ประเมิน limit string ตอน request จาก config (Global Rule 5)
@limiter.limit(lambda: f"{settings.OTP_RATE_LIMIT_PER_10MIN}/10 minutes")
async def verify_otp(
    request: Request,
    response: Response,  # ให้ slowapi inject rate-limit headers เข้า response นี้ (ไม่ใช้ตรงๆ)
    data: OTPVerifyRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await auth_service.verify_otp(session, data)
    await session.commit()
    return result


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,  # ให้ slowapi inject rate-limit headers เข้า response นี้ (ไม่ใช้ตรงๆ)
    data: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await auth_service.login(session, data)
    await session.commit()
    return result


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    data: RefreshRequest, session: AsyncSession = Depends(get_db)
) -> TokenResponse:
    result = await auth_service.refresh_token(session, data)
    await session.commit()
    return result


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """ข้อมูลผู้ใช้จาก access token ปัจจุบัน (protected — ต้องแนบ Bearer token)."""
    return current_user
