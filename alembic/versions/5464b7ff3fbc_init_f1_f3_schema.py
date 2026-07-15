"""init F1-F3 schema

Revision ID: 5464b7ff3fbc
Revises:
Create Date: 2026-07-15 21:38:02.623384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5464b7ff3fbc'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- Enum types (จัดการ CREATE/DROP เองด้วย create_type=False เพื่อให้ downgrade→upgrade วนซ้ำได้) ---
poster_status = postgresql.ENUM(
    'available', 'reserved', 'sold', name='poster_status', create_type=False
)
poster_condition = postgresql.ENUM(
    'mint', 'near_mint', 'very_fine', 'fine', 'very_good', 'good', 'fair', 'poor',
    name='poster_condition', create_type=False,
)
otp_purpose = postgresql.ENUM(
    'registration', 'login', name='otp_purpose', create_type=False
)
reservation_status = postgresql.ENUM(
    'active', 'expired', 'converted', name='reservation_status', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # extension สำหรับ users.email (CITEXT) — autogenerate ไม่เติมให้ ต้องมาก่อนตารางที่ใช้
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # สร้าง enum types ก่อน create_table (create_type=False จึงไม่ถูกสร้างซ้ำโดย create_table)
    poster_status.create(bind, checkfirst=True)
    poster_condition.create(bind, checkfirst=True)
    otp_purpose.create(bind, checkfirst=True)
    reservation_status.create(bind, checkfirst=True)

    op.create_table('posters',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('tmdb_id', sa.Integer(), nullable=True),
    sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('status', poster_status, server_default='available', nullable=False),
    sa.Column('is_unique', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('condition_grade', poster_condition, nullable=True),
    sa.Column('size', sa.String(length=50), nullable=True),
    sa.Column('era_decade', sa.SmallInteger(), nullable=True),
    sa.Column('studio', sa.String(length=100), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_authenticated', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('authenticity_note', sa.Text(), nullable=True),
    sa.Column('provenance', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('price >= 0', name='ck_posters_price_non_negative'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_posters_status_era_price', 'posters', ['status', 'era_decade', 'price'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('is_verified', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('otp_codes',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('code_hash', sa.String(length=255), nullable=False),
    sa.Column('purpose', otp_purpose, server_default='registration', nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempt_count', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_otp_codes_user_created', 'otp_codes', ['user_id', 'created_at'], unique=False)
    op.create_table('poster_images',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('poster_id', sa.UUID(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('sort_order', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['poster_id'], ['posters.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_poster_images_poster', 'poster_images', ['poster_id', 'sort_order'], unique=False)
    op.create_index('uq_poster_images_primary', 'poster_images', ['poster_id'], unique=True, postgresql_where=sa.text('is_primary'))
    op.create_table('refresh_tokens',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index('ix_refresh_tokens_user', 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('reservations',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('poster_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('status', reservation_status, server_default='active', nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['poster_id'], ['posters.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_reservations_status_expires', 'reservations', ['status', 'expires_at'], unique=False)
    op.create_index('uq_active_reservation_per_poster', 'reservations', ['poster_id'], unique=True, postgresql_where=sa.text("status = 'active'"))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    op.drop_index('uq_active_reservation_per_poster', table_name='reservations', postgresql_where=sa.text("status = 'active'"))
    op.drop_index('ix_reservations_status_expires', table_name='reservations')
    op.drop_table('reservations')
    op.drop_index('ix_refresh_tokens_user', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index('uq_poster_images_primary', table_name='poster_images', postgresql_where=sa.text('is_primary'))
    op.drop_index('ix_poster_images_poster', table_name='poster_images')
    op.drop_table('poster_images')
    op.drop_index('ix_otp_codes_user_created', table_name='otp_codes')
    op.drop_table('otp_codes')
    op.drop_table('users')
    op.drop_index('ix_posters_status_era_price', table_name='posters')
    op.drop_table('posters')

    # drop enum types หลังทุกตารางที่ใช้ถูกลบแล้ว (ไม่ drop extension citext เผื่อของอื่นใช้)
    reservation_status.drop(bind, checkfirst=True)
    otp_purpose.drop(bind, checkfirst=True)
    poster_condition.drop(bind, checkfirst=True)
    poster_status.drop(bind, checkfirst=True)
