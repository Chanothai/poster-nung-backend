"""Unit test ของ auth_service — ครอบ acceptance criteria ของ F1:
1) register สำเร็จ  2) login ผิดรหัส 401  3) OTP เกิน rate-limit โดน block
"""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.exceptions import (
    AccountAlreadyVerified,
    EmailAlreadyRegistered,
    InvalidCredentials,
    OtpLocked,
)
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


# ---- Edge cases ----
async def test_register_duplicate_email_case_insensitive(
    db_session: AsyncSession,
) -> None:
    """สมัคร email ตัวพิมพ์ต่างกัน (CITEXT) ต้องถือว่าซ้ำ → 409 (G: case-insensitive)."""
    await auth_service.register(
        db_session, RegisterRequest(email="Dup-Case@test.example", password="Passw0rd1")
    )

    with pytest.raises(EmailAlreadyRegistered) as exc_info:
        await auth_service.register(
            db_session,
            RegisterRequest(email="dup-case@test.example", password="Passw0rd1"),
        )
    assert exc_info.value.status_code == 409


async def test_register_race_integrity_error_maps_to_409(
    db_session: AsyncSession,
) -> None:
    """แพ้ race (create ชน unique) → IntegrityError ต้องถูกแปลงเป็น 409 ไม่ใช่ 500 (G1)."""
    err = IntegrityError("INSERT", {}, Exception("duplicate key value"))
    with patch.object(user_repository, "create", AsyncMock(side_effect=err)):
        with pytest.raises(EmailAlreadyRegistered) as exc_info:
            await auth_service.register(
                db_session,
                RegisterRequest(email="race@test.example", password="Passw0rd1"),
            )
    assert exc_info.value.status_code == 409


async def test_verify_otp_already_verified_rejected(
    db_session: AsyncSession,
) -> None:
    """user ที่ verify แล้ว เรียก verify-otp ซ้ำ → 409 ACCOUNT_ALREADY_VERIFIED (G4)."""
    email = "already-verified@test.example"
    await _register_and_verify(db_session, email, "Passw0rd1")

    with pytest.raises(AccountAlreadyVerified) as exc_info:
        await auth_service.verify_otp(
            db_session, OTPVerifyRequest(email=email, code="000000")
        )
    assert exc_info.value.status_code == 409


async def test_login_unknown_email_runs_dummy_verify(
    db_session: AsyncSession,
) -> None:
    """login ด้วย email ที่ไม่มีในระบบ ต้องเรียก bcrypt verify กับ dummy hash
    (constant-time กัน timing enumeration) แล้วจึง 401 (G2)."""
    with patch.object(
        security, "verify_password", wraps=security.verify_password
    ) as spy:
        with pytest.raises(InvalidCredentials):
            await auth_service.login(
                db_session,
                LoginRequest(email="ghost@test.example", password="Passw0rd1"),
            )

    spy.assert_called_once()
    # ยืนยันว่า verify กับ dummy hash จริง (ไม่ได้ข้ามการ hash)
    assert spy.call_args.args[1] == security.DUMMY_PASSWORD_HASH


def test_register_request_rejects_password_over_72_bytes() -> None:
    """password ที่ยาวเกิน 72 bytes (multibyte) ต้องถูก schema ปฏิเสธ (G3)."""
    # ไทย 25 ตัว = 75 bytes > 72 (แต่ 25 char < max_length=72 char → char-check ไม่จับ)
    thai_password = "ก" * 25
    assert len(thai_password) <= 72  # ผ่าน max_length (char)
    assert len(thai_password.encode("utf-8")) > 72  # แต่เกิน byte limit
    with pytest.raises(ValidationError):
        RegisterRequest(email="bytes@test.example", password=thai_password)
