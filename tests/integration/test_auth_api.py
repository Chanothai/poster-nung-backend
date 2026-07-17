"""Integration tests (HTTP-level) ของ F1 auth — เน้น /auth/me + auth dependency
+ edge case ที่เห็นผลชัดเฉพาะระดับ HTTP (envelope, status code, security)."""

from httpx import AsyncClient

API = "/api/v1/auth"


async def _register_verify_login(
    client: AsyncClient, email: str, password: str
) -> dict:
    """register → verify (ด้วย dev_otp) → login; คืน TokenResponse dict."""
    reg = await client.post(
        f"{API}/register", json={"email": email, "password": password}
    )
    assert reg.status_code == 201, reg.text
    dev_otp = reg.json()["dev_otp"]
    assert dev_otp is not None, "dev_otp ต้องมีตอน DEBUG=true (ใช้ยืนยันใน test)"

    verify = await client.post(
        f"{API}/verify-otp", json={"email": email, "code": dev_otp}
    )
    assert verify.status_code == 200, verify.text

    login = await client.post(
        f"{API}/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    return login.json()


async def test_full_flow_then_me_returns_current_user(client: AsyncClient) -> None:
    email = "flow@test.example"
    tokens = await _register_verify_login(client, email, "Passw0rd1")

    res = await client.get(
        f"{API}/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["email"] == email
    assert body["is_verified"] is True
    assert "hashed_password" not in body  # ห้าม leak


async def test_me_without_token_is_401_envelope(client: AsyncClient) -> None:
    res = await client.get(f"{API}/me")
    assert res.status_code == 401
    assert res.json()["error_code"] == "UNAUTHORIZED"


async def test_me_with_garbage_token_is_401(client: AsyncClient) -> None:
    res = await client.get(
        f"{API}/me", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert res.status_code == 401
    assert res.json()["error_code"] == "UNAUTHORIZED"


async def test_me_rejects_refresh_token_used_as_access(client: AsyncClient) -> None:
    tokens = await _register_verify_login(client, "rt-as-at@test.example", "Passw0rd1")
    # เอา refresh token มาใช้แทน access token → ต้องโดนปฏิเสธ (type != access)
    res = await client.get(
        f"{API}/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert res.status_code == 401
    assert res.json()["error_code"] == "UNAUTHORIZED"


async def test_register_duplicate_email_returns_409_not_500(
    client: AsyncClient,
) -> None:
    email = "dup-http@test.example"
    first = await client.post(
        f"{API}/register", json={"email": email, "password": "Passw0rd1"}
    )
    assert first.status_code == 201
    second = await client.post(
        f"{API}/register", json={"email": email, "password": "Passw0rd1"}
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "EMAIL_ALREADY_REGISTERED"


async def test_register_invalid_password_bytes_is_422(client: AsyncClient) -> None:
    res = await client.post(
        f"{API}/register",
        json={"email": "toolong@test.example", "password": "ก" * 25},  # 75 bytes
    )
    assert res.status_code == 422
    assert res.json()["error_code"] == "VALIDATION_ERROR"


async def test_refresh_with_access_token_is_401(client: AsyncClient) -> None:
    tokens = await _register_verify_login(client, "at-as-rt@test.example", "Passw0rd1")
    res = await client.post(
        f"{API}/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert res.status_code == 401
    assert res.json()["error_code"] == "REFRESH_TOKEN_INVALID"


async def test_refresh_rotated_token_reuse_is_401(client: AsyncClient) -> None:
    tokens = await _register_verify_login(client, "rotate@test.example", "Passw0rd1")
    old_refresh = tokens["refresh_token"]

    # ใช้ครั้งแรก → rotate สำเร็จ (revoke ตัวเก่า ออกตัวใหม่)
    first = await client.post(f"{API}/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200

    # ใช้ตัวเก่าซ้ำ → ต้องถูกปฏิเสธ (ถูก revoke แล้ว)
    reuse = await client.post(f"{API}/refresh", json={"refresh_token": old_refresh})
    assert reuse.status_code == 401
    assert reuse.json()["error_code"] == "REFRESH_TOKEN_INVALID"
