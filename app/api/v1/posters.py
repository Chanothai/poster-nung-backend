"""Thin controller ของ F2 Poster Catalog — ห้ามมี DB query ตรงนี้ เรียก service ล้วน."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.poster import (
    PaginatedPosterList,
    PosterDetailResponse,
    PosterFilterParams,
)
from app.services import poster_service

router = APIRouter(prefix="/posters", tags=["Posters"])


@router.get("", response_model=PaginatedPosterList)
async def list_posters(
    filters: PosterFilterParams = Depends(),
    session: AsyncSession = Depends(get_db),
) -> PaginatedPosterList:
    return await poster_service.list_posters(session, filters)


@router.get("/{poster_id}", response_model=PosterDetailResponse)
async def get_poster_detail(
    poster_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> PosterDetailResponse:
    return await poster_service.get_poster_detail(session, poster_id)
