"""OTP code table access — thin DB layer."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OtpPurpose
from app.models.user import OtpCode


async def create_otp(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    code_hash: str,
    expires_at: datetime,
    purpose: OtpPurpose = OtpPurpose.registration,
) -> OtpCode:
    otp = OtpCode(
        user_id=user_id,
        code_hash=code_hash,
        expires_at=expires_at,
        purpose=purpose,
    )
    session.add(otp)
    await session.flush()
    return otp


async def get_latest_active(
    session: AsyncSession, user_id: uuid.UUID
) -> OtpCode | None:
    """OTP ล่าสุดที่ยังไม่ถูกใช้ (consumed_at IS NULL) ของ user."""
    result = await session.execute(
        select(OtpCode)
        .where(OtpCode.user_id == user_id, OtpCode.consumed_at.is_(None))
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def increment_attempt(session: AsyncSession, otp_id: uuid.UUID) -> None:
    # Core-style UPDATE ที่ SET เป็น SQL expression (Column + 1) — verified ว่า
    # SQLAlchemy 2.0 default synchronize_session="auto" evaluate expression นี้
    # กับ object ที่โหลดไว้ใน identity map ได้ถูกต้อง ไม่ค้างค่าเก่า
    await session.execute(
        update(OtpCode)
        .where(OtpCode.id == otp_id)
        .values(attempt_count=OtpCode.attempt_count + 1)
    )


async def mark_consumed(session: AsyncSession, otp_id: uuid.UUID) -> None:
    await session.execute(
        update(OtpCode)
        .where(OtpCode.id == otp_id)
        .values(consumed_at=datetime.now(timezone.utc))
    )


async def count_recent(
    session: AsyncSession, user_id: uuid.UUID, *, minutes: int = 10
) -> int:
    """จำนวน OTP ที่ขอในหน้าต่างเวลาล่าสุด — ใช้กัน resend rate-limit."""
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    result = await session.execute(
        select(func.count())
        .select_from(OtpCode)
        .where(OtpCode.user_id == user_id, OtpCode.created_at >= since)
    )
    return result.scalar_one()
