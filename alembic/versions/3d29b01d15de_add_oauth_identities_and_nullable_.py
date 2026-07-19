"""add oauth identities and nullable password

Revision ID: 3d29b01d15de
Revises: 5464b7ff3fbc
Create Date: 2026-07-19 06:55:31.560220

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3d29b01d15de"
down_revision: Union[str, Sequence[str], None] = "5464b7ff3fbc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False → จัดการ CREATE/DROP TYPE เองด้านล่าง (ให้ downgrade→upgrade วนซ้ำได้ —
# ดูรูปแบบเดียวกันใน 5464b7ff3fbc_init_f1_f3_schema.py)
oauth_provider = postgresql.ENUM("google", name="oauth_provider", create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # สร้าง enum ก่อน create_table (create_type=False จึงไม่ถูกสร้างซ้ำโดย create_table)
    oauth_provider.create(bind, checkfirst=True)

    op.create_table(
        "oauth_identities",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", oauth_provider, nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_user_id", name="uq_oauth_identities_provider_user"
        ),
    )
    op.create_index(
        "ix_oauth_identities_user", "oauth_identities", ["user_id"], unique=False
    )
    op.alter_column(
        "users", "hashed_password", existing_type=sa.VARCHAR(length=255), nullable=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.VARCHAR(length=255),
        nullable=False,
    )
    op.drop_index("ix_oauth_identities_user", table_name="oauth_identities")
    op.drop_table("oauth_identities")

    oauth_provider.drop(bind, checkfirst=True)
