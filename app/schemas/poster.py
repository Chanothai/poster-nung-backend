"""Pydantic v2 schemas สำหรับ F2 Poster Catalog (ตรง docs/openapi.yaml)."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PosterCondition, PosterStatus


# ---- Responses ----
class PosterImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    is_primary: bool
    sort_order: int


class PosterListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    price: Decimal
    status: PosterStatus
    condition_grade: PosterCondition | None
    era_decade: int | None
    studio: str | None
    primary_image_url: str | None = None


class PosterDetailResponse(PosterListItem):
    tmdb_id: int | None
    size: str | None
    description: str | None
    is_authenticated: bool
    authenticity_note: str | None
    provenance: str | None
    images: list[PosterImageResponse]
    created_at: datetime


class PaginatedPosterList(BaseModel):
    items: list[PosterListItem]
    total: int
    limit: int
    offset: int


# ---- Requests ----
class PosterFilterParams(BaseModel):
    era_decade: int | None = None
    condition_grade: PosterCondition | None = None
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    in_stock_only: bool = False
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
