"""F3 Reservation model — reservations (จุดวิกฤต race condition ของสต็อก=1)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import CreatedAtMixin, uuid_pk
from app.models.enums import ReservationStatus

reservation_status_enum = PgEnum(
    ReservationStatus, name="reservation_status", create_type=False
)


class Reservation(Base, CreatedAtMixin):
    __tablename__ = "reservations"
    __table_args__ = (
        # ชั้นที่ 2 ของ concurrency defense — active reservation ได้ตัวเดียวต่อโปสเตอร์
        # (ชั้นที่ 1 คือ SELECT ... FOR UPDATE ใน service layer — ดู database-design.md §6)
        Index(
            "uq_active_reservation_per_poster",
            "poster_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_reservations_status_expires", "status", "expires_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # RESTRICT — ห้ามลบ poster ที่ยังมีประวัติการจองอยู่
    poster_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("posters.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ReservationStatus] = mapped_column(
        reservation_status_enum,
        nullable=False,
        server_default=ReservationStatus.active.value,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
