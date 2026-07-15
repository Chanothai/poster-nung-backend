"""F2 Catalog models — posters, poster_images."""

import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import CreatedAtMixin, TimestampMixin, uuid_pk
from app.models.enums import PosterCondition, PosterStatus

# create_type=False → จัดการ CREATE/DROP TYPE เองใน migration
poster_status_enum = PgEnum(PosterStatus, name="poster_status", create_type=False)
poster_condition_enum = PgEnum(
    PosterCondition, name="poster_condition", create_type=False
)


class Poster(Base, TimestampMixin):
    __tablename__ = "posters"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_posters_price_non_negative"),
        Index("ix_posters_status_era_price", "status", "era_decade", "price"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # canonical movie id (TMDB) — future-proof สำหรับ marketplace (ดู database-design.md §8)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[PosterStatus] = mapped_column(
        poster_status_enum,
        nullable=False,
        server_default=PosterStatus.available.value,
    )
    is_unique: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    condition_grade: Mapped[PosterCondition | None] = mapped_column(
        poster_condition_enum, nullable=True
    )
    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    era_decade: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    studio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_authenticated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    authenticity_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[str | None] = mapped_column(Text, nullable=True)


class PosterImage(Base, CreatedAtMixin):
    __tablename__ = "poster_images"
    __table_args__ = (
        Index("ix_poster_images_poster", "poster_id", "sort_order"),
        # กันรูป primary ซ้ำต่อโปสเตอร์ (partial unique)
        Index(
            "uq_poster_images_primary",
            "poster_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    poster_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posters.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    sort_order: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
