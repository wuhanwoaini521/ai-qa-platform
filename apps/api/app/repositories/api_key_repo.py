from __future__ import annotations

import hashlib
import secrets
import uuid

from project_model.models import ApiKey, ApiKeyCreate, ApiKeyCreatedResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_session
from app.persistence.models import ApiKeyORM, utc_now


class ApiKeyRepository:
    def __init__(self, session_factory=get_session) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async def create(self, data: ApiKeyCreate, session: AsyncSession | None = None) -> ApiKeyCreatedResponse:
        key_id = str(uuid.uuid4())
        # Generate raw token e.g. "aqp_live_abc12345..."
        random_part = secrets.token_urlsafe(32)
        raw_key = f"aqp_live_{random_part}"
        key_prefix = raw_key[:12]
        key_hash = self._hash_key(raw_key)

        orm = ApiKeyORM(
            id=key_id,
            user_id=data.user_id,
            name=data.name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            expires_at=data.expires_at,
            created_at=utc_now(),
        )

        async def _exec(s: AsyncSession) -> ApiKeyCreatedResponse:
            s.add(orm)
            await s.commit()
            await s.refresh(orm)
            return ApiKeyCreatedResponse(
                id=orm.id,
                user_id=orm.user_id,
                name=orm.name,
                key_prefix=orm.key_prefix,
                raw_api_key=raw_key,
                expires_at=orm.expires_at,
                last_used_at=orm.last_used_at,
                created_at=orm.created_at,
            )

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def get_by_raw_key(self, raw_key: str, session: AsyncSession | None = None) -> ApiKey | None:
        key_hash = self._hash_key(raw_key)

        async def _exec(s: AsyncSession) -> ApiKey | None:
            stmt = select(ApiKeyORM).where(ApiKeyORM.key_hash == key_hash)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            if not orm:
                return None
            orm.last_used_at = utc_now()
            await s.commit()
            return self._to_model(orm)

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def list_by_user(self, user_id: str, session: AsyncSession | None = None) -> list[ApiKey]:
        async def _exec(s: AsyncSession) -> list[ApiKey]:
            stmt = select(ApiKeyORM).where(ApiKeyORM.user_id == user_id).order_by(ApiKeyORM.created_at.desc())
            res = await s.execute(stmt)
            return [self._to_model(orm) for orm in res.scalars().all()]

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def delete(self, key_id: str, session: AsyncSession | None = None) -> bool:
        async def _exec(s: AsyncSession) -> bool:
            stmt = select(ApiKeyORM).where(ApiKeyORM.id == key_id)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            if not orm:
                return False
            await s.delete(orm)
            await s.commit()
            return True

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    @staticmethod
    def _to_model(orm: ApiKeyORM) -> ApiKey:
        return ApiKey(
            id=orm.id,
            user_id=orm.user_id,
            name=orm.name,
            key_prefix=orm.key_prefix,
            expires_at=orm.expires_at,
            last_used_at=orm.last_used_at,
            created_at=orm.created_at,
        )
