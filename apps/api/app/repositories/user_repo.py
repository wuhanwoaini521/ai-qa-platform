from __future__ import annotations

import hashlib
import uuid

from project_model.models import User, UserCreate, UserRole, UserUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence import database
from app.persistence.models import UserORM, utc_now


class UserRepository:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    @property
    def session_factory(self):
        if self._session_factory is not None:
            return self._session_factory

        return database.get_session

    @staticmethod
    def _hash_password(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def create(self, data: UserCreate, session: AsyncSession | None = None) -> User:
        user_id = str(uuid.uuid4())
        pwd_hash = self._hash_password(data.password or "password123")
        orm = UserORM(
            id=user_id,
            email=data.email.lower().strip(),
            full_name=data.full_name,
            password_hash=pwd_hash,
            role=data.role.value if isinstance(data.role, UserRole) else str(data.role),
            is_active=data.is_active,
            avatar_url=data.avatar_url,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        async def _exec(s: AsyncSession) -> User:
            s.add(orm)
            await s.commit()
            await s.refresh(orm)
            return self._to_model(orm)

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def get_by_id(self, user_id: str, session: AsyncSession | None = None) -> User | None:
        async def _exec(s: AsyncSession) -> User | None:
            stmt = select(UserORM).where(UserORM.id == user_id)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            return self._to_model(orm) if orm else None

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def get_by_email(self, email: str, session: AsyncSession | None = None) -> User | None:
        async def _exec(s: AsyncSession) -> User | None:
            stmt = select(UserORM).where(UserORM.email == email.lower().strip())
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            return self._to_model(orm) if orm else None

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def list_all(self, limit: int = 100, session: AsyncSession | None = None) -> list[User]:
        async def _exec(s: AsyncSession) -> list[User]:
            stmt = select(UserORM).order_by(UserORM.created_at.desc()).limit(limit)
            res = await s.execute(stmt)
            return [self._to_model(orm) for orm in res.scalars().all()]

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def update(self, user_id: str, data: UserUpdate, session: AsyncSession | None = None) -> User | None:
        async def _exec(s: AsyncSession) -> User | None:
            stmt = select(UserORM).where(UserORM.id == user_id)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            if not orm:
                return None

            if data.email is not None:
                orm.email = data.email.lower().strip()
            if data.full_name is not None:
                orm.full_name = data.full_name
            if data.role is not None:
                orm.role = data.role.value if isinstance(data.role, UserRole) else str(data.role)
            if data.is_active is not None:
                orm.is_active = data.is_active
            if data.avatar_url is not None:
                orm.avatar_url = data.avatar_url
            orm.updated_at = utc_now()

            await s.commit()
            await s.refresh(orm)
            return self._to_model(orm)

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def verify_password(self, email: str, password: str, session: AsyncSession | None = None) -> User | None:
        pwd_hash = self._hash_password(password)

        async def _exec(s: AsyncSession) -> User | None:
            stmt = select(UserORM).where(UserORM.email == email.lower().strip(), UserORM.password_hash == pwd_hash)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            return self._to_model(orm) if orm else None

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def delete(self, user_id: str, session: AsyncSession | None = None) -> bool:
        async def _exec(s: AsyncSession) -> bool:
            stmt = select(UserORM).where(UserORM.id == user_id)
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
    def _to_model(orm: UserORM) -> User:
        return User(
            id=orm.id,
            email=orm.email,
            full_name=orm.full_name,
            role=UserRole(orm.role) if orm.role in UserRole.__members__.values() else UserRole.QA_ENGINEER,
            is_active=orm.is_active,
            avatar_url=orm.avatar_url,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
