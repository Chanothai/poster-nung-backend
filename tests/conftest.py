"""Test fixtures — ใช้ poster_nung_test แยกจาก dev DB (ไม่แตะข้อมูล dev)."""

import asyncio
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings

BACKEND_ROOT = Path(__file__).resolve().parent.parent
TEST_DB_NAME = "poster_nung_test"

_dev_url = make_url(settings.DATABASE_URL)
# str(url)/render_as_string() default เซ็นเซอร์รหัสผ่านเป็น '***' — ต้อง hide_password=False
# ไม่งั้น asyncpg auth fail เพราะ password กลายเป็น literal '***'
TEST_DATABASE_URL = _dev_url.set(database=TEST_DB_NAME).render_as_string(
    hide_password=False
)


async def _ensure_test_database_exists() -> None:
    """เชื่อมต่อ maintenance DB (postgres) เพื่อสร้าง poster_nung_test ถ้ายังไม่มี."""
    admin_url = _dev_url.set(database="postgres")
    conn = await asyncpg.connect(
        user=admin_url.username,
        password=admin_url.password,
        host=admin_url.host,
        port=admin_url.port,
        database=admin_url.database,
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
        )
        if not exists:
            # TEST_DB_NAME เป็นค่าคงที่ในโค้ด ไม่ใช่ user input — interpolate ตรงนี้ปลอดภัย
            # (CREATE DATABASE ไม่รองรับ parameterized identifier)
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()


def _run_migrations() -> None:
    """รัน alembic upgrade head บน poster_nung_test (sync — เรียกตอนยังไม่มี event loop)."""
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.attributes["sqlalchemy_url_override"] = TEST_DATABASE_URL
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _setup_test_database() -> None:
    """สร้าง DB + apply migration ครั้งเดียวต่อ test session."""
    asyncio.run(_ensure_test_database_exists())
    _run_migrations()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Session ต่อ 1 test — ครอบด้วย transaction เดียวแล้ว rollback ทิ้งเสมอ
    (join_transaction_mode="create_savepoint" กัน session.commit() ของ service
    ทะลุออกไป commit จริงบน DB)."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()
    await engine.dispose()
