"""firebase phone auth: nullable email + oauth_provider password/phone

Revision ID: f1b2a3c4d5e6
Revises: 3d29b01d15de
Create Date: 2026-07-21 00:00:00.000000

รองรับ Firebase Phone Auth (phone-only user ไม่มี email) + email/password ผ่าน Firebase:
  - users.email / oauth_identities.email → nullable
  - oauth_provider enum เพิ่มค่า 'password', 'phone'

จัดการ enum ด้วย recreate-type (RENAME + CREATE + ALTER COLUMN + DROP) แทน ADD VALUE
เพื่อให้ downgrade→upgrade วนซ้ำได้ ตาม convention ของ repo (create_type=False)
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1b2a3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "3d29b01d15de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- oauth_provider: เพิ่ม password/phone (recreate type — reversible) ---
    op.execute("ALTER TYPE oauth_provider RENAME TO oauth_provider_old")
    op.execute("CREATE TYPE oauth_provider AS ENUM ('google', 'password', 'phone')")
    op.execute(
        "ALTER TABLE oauth_identities ALTER COLUMN provider TYPE oauth_provider "
        "USING provider::text::oauth_provider"
    )
    op.execute("DROP TYPE oauth_provider_old")

    # --- email → nullable (phone-only user ไม่มี email) ---
    op.alter_column("users", "email", existing_type=postgresql.CITEXT(), nullable=True)
    op.alter_column(
        "oauth_identities", "email", existing_type=postgresql.CITEXT(), nullable=True
    )


def downgrade() -> None:
    """Downgrade schema.

    ลบข้อมูลที่พึ่งค่าใหม่ก่อน (phone/password identity + phone-only user ที่ email NULL)
    — downgrade เป็น dev-only operation, data loss ตรงนี้ยอมรับได้.
    """
    # ลบ identity ที่ใช้ provider ใหม่ + row ที่ email NULL (ก่อน revert constraint/enum)
    op.execute("DELETE FROM oauth_identities WHERE provider IN ('password', 'phone')")
    op.execute("DELETE FROM oauth_identities WHERE email IS NULL")
    op.execute("DELETE FROM users WHERE email IS NULL")

    # email กลับเป็น NOT NULL
    op.alter_column(
        "oauth_identities", "email", existing_type=postgresql.CITEXT(), nullable=False
    )
    op.alter_column("users", "email", existing_type=postgresql.CITEXT(), nullable=False)

    # oauth_provider กลับเหลือแค่ google (recreate type)
    op.execute("ALTER TYPE oauth_provider RENAME TO oauth_provider_old")
    op.execute("CREATE TYPE oauth_provider AS ENUM ('google')")
    op.execute(
        "ALTER TABLE oauth_identities ALTER COLUMN provider TYPE oauth_provider "
        "USING provider::text::oauth_provider"
    )
    op.execute("DROP TYPE oauth_provider_old")
