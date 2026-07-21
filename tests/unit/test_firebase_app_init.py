"""Unit test ของ auth_service._ensure_firebase_app — เลือก credential source ระหว่าง
FIREBASE_SERVICE_ACCOUNT_PATH (ไฟล์, best practice prod) กับ FIREBASE_SERVICE_ACCOUNT_JSON
(เนื้อ JSON ใน env, fallback dev/test). mock Certificate + initialize_app เพื่อไม่ต้องมี
credential จริง.

ไฟล์นี้แยกจาก test_google_login.py เพราะที่นั่น autouse fixture patch _ensure_firebase_app
เป็น no-op — ที่นี่ต้องเรียกฟังก์ชันจริงเพื่อตรวจ branch การเลือก cred.
"""

from unittest.mock import patch

import pytest

from app.core.config import settings
from app.services import auth_service


@pytest.fixture(autouse=True)
def _reset_firebase_state():
    """คืนค่า global init flag + settings ที่แตะ ให้แต่ละ test เริ่มสะอาด
    (init ครั้งเดียวเป็น idempotent — ถ้าไม่ reset test ที่สองจะ early-return)."""
    orig_pid = settings.FIREBASE_PROJECT_ID
    orig_json = settings.FIREBASE_SERVICE_ACCOUNT_JSON
    orig_path = settings.FIREBASE_SERVICE_ACCOUNT_PATH
    auth_service._firebase_initialized = False
    settings.FIREBASE_PROJECT_ID = "posternung"
    settings.FIREBASE_SERVICE_ACCOUNT_JSON = ""
    settings.FIREBASE_SERVICE_ACCOUNT_PATH = ""
    yield
    settings.FIREBASE_PROJECT_ID = orig_pid
    settings.FIREBASE_SERVICE_ACCOUNT_JSON = orig_json
    settings.FIREBASE_SERVICE_ACCOUNT_PATH = orig_path
    auth_service._firebase_initialized = False


def test_ensure_firebase_app_uses_path_when_set() -> None:
    """ตั้ง PATH → ส่ง path string ตรงๆ เข้า Certificate (ไม่ parse JSON)."""
    settings.FIREBASE_SERVICE_ACCOUNT_PATH = "/run/secrets/firebase-sa.json"
    # ตั้ง JSON ด้วยให้เห็นชัดว่า PATH ต้องมาก่อน (JSON นี้ถ้าถูกใช้จะ error เพราะไม่ใช่ JSON)
    settings.FIREBASE_SERVICE_ACCOUNT_JSON = "not-valid-json-should-be-ignored"

    with patch.object(
        auth_service.firebase_credentials, "Certificate"
    ) as mock_cert, patch.object(auth_service.firebase_admin, "initialize_app"):
        auth_service._ensure_firebase_app()

    mock_cert.assert_called_once_with("/run/secrets/firebase-sa.json")


def test_ensure_firebase_app_uses_json_when_no_path() -> None:
    """ไม่มี PATH แต่มี JSON → parse JSON เป็น dict แล้วส่งเข้า Certificate."""
    settings.FIREBASE_SERVICE_ACCOUNT_JSON = '{"type": "service_account", "x": 1}'

    with patch.object(
        auth_service.firebase_credentials, "Certificate"
    ) as mock_cert, patch.object(auth_service.firebase_admin, "initialize_app"):
        auth_service._ensure_firebase_app()

    mock_cert.assert_called_once_with({"type": "service_account", "x": 1})


def test_ensure_firebase_app_idempotent() -> None:
    """เรียกซ้ำ → init แค่ครั้งเดียว (Certificate/initialize_app ไม่ถูกเรียกรอบสอง)."""
    settings.FIREBASE_SERVICE_ACCOUNT_PATH = "/run/secrets/firebase-sa.json"

    with patch.object(
        auth_service.firebase_credentials, "Certificate"
    ) as mock_cert, patch.object(
        auth_service.firebase_admin, "initialize_app"
    ) as mock_init:
        auth_service._ensure_firebase_app()
        auth_service._ensure_firebase_app()

    assert mock_cert.call_count == 1
    assert mock_init.call_count == 1
