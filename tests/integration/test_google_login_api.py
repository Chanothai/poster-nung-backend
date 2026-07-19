"""Integration tests (HTTP-level) ของ POST /auth/google — mock Google token
verification เพื่อไม่ต้องพึ่ง Google server จริง."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.core.config import settings

API = "/api/v1/auth"


def _firebase_payload(
    *, sub: str = "firebase-uid-http", email: str = "ghttp@test.example", verified=True
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
    original = settings.FIREBASE_PROJECT_ID
    settings.FIREBASE_PROJECT_ID = "posternung"
    yield
    settings.FIREBASE_PROJECT_ID = original


async def test_google_login_returns_token_and_me_works(client: AsyncClient) -> None:
    payload = _firebase_payload(email="google-flow@test.example")
    with patch(
        "app.services.auth_service.google_id_token.verify_firebase_token",
        return_value=payload,
    ):
        res = await client.post(f"{API}/google", json={"id_token": "fake-token"})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"

    me = await client.get(
        f"{API}/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    me_body = me.json()
    assert me_body["email"] == "google-flow@test.example"
    assert me_body["is_verified"] is True
    assert "hashed_password" not in me_body


async def test_google_login_email_not_verified_403(client: AsyncClient) -> None:
    payload = _firebase_payload(email="unverified-http@test.example", verified=False)
    with patch(
        "app.services.auth_service.google_id_token.verify_firebase_token",
        return_value=payload,
    ):
        res = await client.post(f"{API}/google", json={"id_token": "fake-token"})

    assert res.status_code == 403
    assert res.json()["error_code"] == "OAUTH_EMAIL_NOT_VERIFIED"


async def test_google_login_invalid_token_401(client: AsyncClient) -> None:
    with patch(
        "app.services.auth_service.google_id_token.verify_firebase_token",
        side_effect=ValueError("bad token"),
    ):
        res = await client.post(f"{API}/google", json={"id_token": "garbage"})

    assert res.status_code == 401
    assert res.json()["error_code"] == "OAUTH_TOKEN_INVALID"


async def test_google_login_missing_id_token_is_422(client: AsyncClient) -> None:
    res = await client.post(f"{API}/google", json={})
    assert res.status_code == 422
    assert res.json()["error_code"] == "VALIDATION_ERROR"


async def test_google_login_provider_not_configured_503(client: AsyncClient) -> None:
    settings.FIREBASE_PROJECT_ID = ""  # จำลอง env ไม่ได้ตั้งค่า (override fixture)
    res = await client.post(f"{API}/google", json={"id_token": "fake-token"})
    assert res.status_code == 503
    assert res.json()["error_code"] == "OAUTH_PROVIDER_NOT_CONFIGURED"
