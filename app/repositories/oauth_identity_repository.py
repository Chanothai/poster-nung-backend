"""OAuth identity table access — thin DB layer (ไม่มี business logic)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OAuthProvider
from app.models.user import OAuthIdentity


async def get_by_provider_user_id(
    session: AsyncSession, *, provider: OAuthProvider, provider_user_id: str
) -> OAuthIdentity | None:
    result = await session.execute(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider,
            OAuthIdentity.provider_user_id == provider_user_id,
        )
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    provider: OAuthProvider,
    provider_user_id: str,
    email: str | None,
) -> OAuthIdentity:
    identity = OAuthIdentity(
        user_id=user_id,
        provider=provider,
        provider_user_id=provider_user_id,
        email=email,
    )
    session.add(identity)
    await session.flush()
    return identity
