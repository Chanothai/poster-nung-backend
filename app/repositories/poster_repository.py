"""Poster table access — thin DB layer (ไม่มี business logic)."""

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import PosterCondition, PosterStatus
from app.models.poster import Poster


def _apply_filters(
    stmt,
    *,
    era_decade: int | None,
    condition_grade: PosterCondition | None,
    min_price: Decimal | None,
    max_price: Decimal | None,
    in_stock_only: bool,
):
    if era_decade is not None:
        stmt = stmt.where(Poster.era_decade == era_decade)
    if condition_grade is not None:
        stmt = stmt.where(Poster.condition_grade == condition_grade)
    if min_price is not None:
        stmt = stmt.where(Poster.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Poster.price <= max_price)
    if in_stock_only:
        stmt = stmt.where(Poster.status == PosterStatus.available)
    return stmt


async def list_with_filters(
    session: AsyncSession,
    *,
    era_decade: int | None,
    condition_grade: PosterCondition | None,
    min_price: Decimal | None,
    max_price: Decimal | None,
    in_stock_only: bool,
    limit: int,
    offset: int,
) -> tuple[Sequence[Poster], int]:
    filters = {
        "era_decade": era_decade,
        "condition_grade": condition_grade,
        "min_price": min_price,
        "max_price": max_price,
        "in_stock_only": in_stock_only,
    }

    count_stmt = _apply_filters(select(func.count(Poster.id)), **filters)
    total = (await session.execute(count_stmt)).scalar_one()

    list_stmt = _apply_filters(select(Poster), **filters)
    list_stmt = (
        list_stmt.options(selectinload(Poster.images))
        .order_by(Poster.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    posters = (await session.execute(list_stmt)).scalars().all()

    return posters, total


async def get_by_id(session: AsyncSession, poster_id: uuid.UUID) -> Poster | None:
    stmt = (
        select(Poster)
        .options(selectinload(Poster.images))
        .where(Poster.id == poster_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
