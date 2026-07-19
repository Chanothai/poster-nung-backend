"""Unit test ของ auth_service.google_login — mock google_id_token.verify_firebase_token
เพื่อไม่ต้องพึ่ง Firebase/Google server จริงตอน test."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    InvalidCredentials,
    OAuthEmailNotVerified,
    OAuthProviderNotConfigured,
    OAuthTokenInvalid,
)
from app.models.enums import OAuthProvider
from app.repositories import oauth_identity_repository, user_repository
from app.schemas.auth import GoogleLoginRequest, LoginRequest, RegisterRequest
from app.services import auth_service


def _firebase_payload(
    *, sub: str = "firebase-uid-123", email: str = "gtest@test.example", verified=True
) -> dict:
    """claim แบบ Firebase ID token (sub = Firebase uid)."""
    return {
        "iss": "https://securetoken.google.com/posternung",
        "aud": "posternung",
        "sub": sub,
        "email": email,
        "email_verified": verified,
        "firebase": {
            "identities": {"google.com": ["google-sub-x"], "email": [email]},
            "sign_in_provider": "google.com",
        },
    }


@pytest.fixture(autouse=True)
def _firebase_project_configured():
    """ตั้ง FIREBASE_PROJECT_ID ชั่วคราวระหว่าง test (default ว่างใน env ของ CI)."""
    original = settings.FIREBASE_PROJECT_ID
    settings.FIREBASE_PROJECT_ID = "posternung"
    yield
    settings.FIREBASE_PROJECT_ID = original


async def test_google_login_new_user_creates_account(db_session: AsyncSession) -> None:
    """ยังไม่เคยมี user/identity มาก่อน → สร้างใหม่, is_verified=True ทันที,
    hashed_password=None (social-only)."""
    payload = _firebase_payload(email="brand-new@test.example")
    with patch(
        "app.services.auth_service.google_id_token.verify_firebase_token",
        return_value=payload,
    ):
        result = await auth_service.google_login(
            db_session, GoogleLoginRequest(id_token="fake-token")
        )

    assert result.access_token and result.refresh_token

    user = await user_repository.get_by_email(db_session, "brand-new@test.example")
    assert user is not None
    assert user.is_verified is True
    assert user.hashed_password is None

    identity = await oauth_identity_repository.get_by_provider_user_id(
        db_session, provider=OAuthProvider.google, provider_user_id=payload["sub"]
    )
    assert identity is not None
    assert identity.user_id == user.id


async def test_google_login_existing_identity_reuses_same_user(
    db_session: AsyncSession,
) -> None:
    """login ซ้ำด้วย Google account เดิม → ไม่สร้าง user/identity ซ้ำ คืน user เดิม."""
    payload = _firebase_payload(email="repeat@test.example", sub="google-sub-repeat")
    with patch(
        "app.services.auth_service.google_id_token.verify_firebase_token",
        return_value=payload,
    ):
        await auth_service.google_login(
            db_session, GoogleLoginRequest(id_token="fake-token")
        )
        await auth_service.google_login(
            db_session, GoogleLoginRequest(id_token="fake-token")
        )

    users_with_email = await user_repository.get_by_email(
        db_session, "repeat@test.example"
    )
    assert users_with_email is not None
    # ยืนยันไม่มี identity ซ้ำ (unique constraint จะ error ถ้าโค้ด insert ซ้ำ — ผ่านแปลว่า
    # รอบสอง detect ว่ามี identity แล้วและไม่พยายาม insert อีก)
    identity = await oauth_identity_repository.get_by_provider_user_id(
        db_session, provider=OAuthProvider.google, provider_user_id="google-sub-repeat"
    )
    assert identity is not None


async def test_google_login_auto_links_existing_password_account(
    db_session: AsyncSession,
) -> None:
    """user สมัคร email/password ไว้ก่อนแล้ว (ยังไม่ verify) → login Google ด้วย email
    เดียวกัน (verified) → auto-link เข้า user เดิม + set is_verified=True."""
    email = "link-me@test.example"
    user, _ = await auth_service.register(
        db_session, RegisterRequest(email=email, password="Passw0rd1")
    )
    assert user.is_verified is False

    payload = _firebase_payload(email=email, sub="google-sub-link")
    with patch(
        "app.services.auth_service.google_id_token.verify_firebase_token",
        return_value=payload,
    ):
        await auth_service.google_login(
            db_session, GoogleLoginRequest(id_token="fake-token")
        )

    identity = await oauth_identity_repository.get_by_provider_user_id(
        db_session, provider=OAuthProvider.google, provider_user_id="google-sub-link"
    )
    assert identity is not None
    assert (
        identity.user_id == user.id
    )  # link เข้า user ที่มี password อยู่แล้ว ไม่สร้างใหม่

    linked_user = await user_repository.get_by_email(db_session, email)
    assert linked_user.is_verified is True  # Google ยืนยัน email แล้ว → auto-verify
    assert (
        linked_user.hashed_password is not None
    )  # ยังคง password เดิมไว้ (ไม่ถูกล้าง)


async def test_google_login_email_not_verified_rejected(
    db_session: AsyncSession,
) -> None:
    payload = _firebase_payload(email="unverified@test.example", verified=False)
    with patch(
        "app.services.auth_service.google_id_token.verify_firebase_token",
        return_value=payload,
    ):
        with pytest.raises(OAuthEmailNotVerified) as exc_info:
            await auth_service.google_login(
                db_session, GoogleLoginRequest(id_token="fake-token")
            )
    assert exc_info.value.status_code == 403


async def test_google_login_invalid_token_rejected(db_session: AsyncSession) -> None:
    with patch(
        "app.services.auth_service.google_id_token.verify_firebase_token",
        side_effect=ValueError("Token expired"),
    ):
        with pytest.raises(OAuthTokenInvalid) as exc_info:
            await auth_service.google_login(
                db_session, GoogleLoginRequest(id_token="garbage")
            )
    assert exc_info.value.status_code == 401


async def test_google_login_provider_not_configured(db_session: AsyncSession) -> None:
    settings.FIREBASE_PROJECT_ID = (
        ""  # override fixture's value เพื่อจำลอง env ไม่ได้ตั้งค่า
    )
    with pytest.raises(OAuthProviderNotConfigured) as exc_info:
        await auth_service.google_login(
            db_session, GoogleLoginRequest(id_token="fake-token")
        )
    assert exc_info.value.status_code == 503


async def test_password_login_rejected_for_social_only_account(
    db_session: AsyncSession,
) -> None:
    """user ที่สมัครผ่าน Google อย่างเดียว (ไม่มีรหัสผ่าน) เอา password มา login
    ต้องได้ INVALID_CREDENTIALS (401) ไม่ใช่ crash (G: nullable hashed_password)."""
    payload = _firebase_payload(email="social-only@test.example")
    with patch(
        "app.services.auth_service.google_id_token.verify_firebase_token",
        return_value=payload,
    ):
        await auth_service.google_login(
            db_session, GoogleLoginRequest(id_token="fake-token")
        )

    with pytest.raises(InvalidCredentials) as exc_info:
        await auth_service.login(
            db_session,
            LoginRequest(email="social-only@test.example", password="AnyPassword1"),
        )
    assert exc_info.value.status_code == 401
