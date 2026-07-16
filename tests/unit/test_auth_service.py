"""Unit test ของ auth_service — ครอบ acceptance criteria ของ F1:
1) register สำเร็จ  2) login ผิดรหัส 401  3) OTP เกิน rate-limit โดน block
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidCredentials, OtpLocked
from app.repositories import user_repository
from app.schemas.auth import LoginRequest, OTPVerifyRequest, RegisterRequest
from app.services import auth_service


async def _register_and_verify(
    session: AsyncSession, email: str, password: str
) -> None:
    """helper: สมัคร + ยืนยัน OTP ให้ user พร้อม login (ใช้ในหลาย test)."""
    user, plain_otp = await auth_service.register(
        session, RegisterRequest(email=email, password=password)
    )
    await auth_service.verify_otp(
        session, OTPVerifyRequest(email=email, code=plain_otp)
    )


async def test_register_success(db_session: AsyncSession) -> None:
    data = RegisterRequest(email="new-user@test.example", password="P@ssw0rd123")

    user, plain_otp = await auth_service.register(db_session, data)

    assert user.id is not None
    assert user.email == "new-user@test.example"
    assert user.is_verified is False
    assert len(plain_otp) == 6 and plain_otp.isdigit()

    fetched = await user_repository.get_by_email(db_session, "new-user@test.example")
    assert fetched is not None
    assert fetched.id == user.id


async def test_login_wrong_password_401(db_session: AsyncSession) -> None:
    email = "login-user@test.example"
    await _register_and_verify(db_session, email, "CorrectPass1")

    with pytest.raises(InvalidCredentials) as exc_info:
        await auth_service.login(
            db_session, LoginRequest(email=email, password="WrongPass1")
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "INVALID_CREDENTIALS"


async def test_verify_otp_rate_limit_block(db_session: AsyncSession) -> None:
    email = "otp-lock-user@test.example"
    _, plain_otp = await auth_service.register(
        db_session, RegisterRequest(email=email, password="SomePass1")
    )
    wrong_code = "000000" if plain_otp != "000000" else "111111"

    # กรอกผิด 5 ครั้งติด — แต่ละครั้งต้องได้ OTP_INVALID (ยังไม่ล็อก)
    for _ in range(5):
        with pytest.raises(Exception) as exc_info:
            await auth_service.verify_otp(
                db_session, OTPVerifyRequest(email=email, code=wrong_code)
            )
        assert exc_info.value.error_code == "OTP_INVALID"

    # ครั้งที่ 6 ต้องโดน block ด้วย OTP_LOCKED (429) แม้จะกรอกรหัสถูกก็ตาม
    with pytest.raises(OtpLocked) as exc_info:
        await auth_service.verify_otp(
            db_session, OTPVerifyRequest(email=email, code=plain_otp)
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.error_code == "OTP_LOCKED"
