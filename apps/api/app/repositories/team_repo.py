from __future__ import annotations

import uuid

from project_model.models import Team, TeamCreate, TeamMember, TeamUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_session
from app.persistence.models import TeamMemberORM, TeamORM, utc_now


class TeamRepository:
    def __init__(self, session_factory=get_session) -> None:
        self.session_factory = session_factory

    async def create(self, data: TeamCreate, session: AsyncSession | None = None) -> Team:
        team_id = str(uuid.uuid4())
        orm = TeamORM(
            id=team_id,
            name=data.name.strip(),
            description=data.description,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        async def _exec(s: AsyncSession) -> Team:
            s.add(orm)
            await s.commit()
            await s.refresh(orm)
            return self._to_model(orm, members=[])

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def get_by_id(self, team_id: str, session: AsyncSession | None = None) -> Team | None:
        async def _exec(s: AsyncSession) -> Team | None:
            stmt = select(TeamORM).where(TeamORM.id == team_id)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            if not orm:
                return None
            m_stmt = select(TeamMemberORM).where(TeamMemberORM.team_id == team_id)
            m_res = await s.execute(m_stmt)
            members = [self._to_member_model(m) for m in m_res.scalars().all()]
            return self._to_model(orm, members=members)

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def list_all(self, limit: int = 100, session: AsyncSession | None = None) -> list[Team]:
        async def _exec(s: AsyncSession) -> list[Team]:
            stmt = select(TeamORM).order_by(TeamORM.created_at.desc()).limit(limit)
            res = await s.execute(stmt)
            teams = []
            for orm in res.scalars().all():
                m_stmt = select(TeamMemberORM).where(TeamMemberORM.team_id == orm.id)
                m_res = await s.execute(m_stmt)
                members = [self._to_member_model(m) for m in m_res.scalars().all()]
                teams.append(self._to_model(orm, members=members))
            return teams

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def update(self, team_id: str, data: TeamUpdate, session: AsyncSession | None = None) -> Team | None:
        async def _exec(s: AsyncSession) -> Team | None:
            stmt = select(TeamORM).where(TeamORM.id == team_id)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            if not orm:
                return None

            if data.name is not None:
                orm.name = data.name.strip()
            if data.description is not None:
                orm.description = data.description
            orm.updated_at = utc_now()

            await s.commit()
            await s.refresh(orm)
            m_stmt = select(TeamMemberORM).where(TeamMemberORM.team_id == team_id)
            m_res = await s.execute(m_stmt)
            members = [self._to_member_model(m) for m in m_res.scalars().all()]
            return self._to_model(orm, members=members)

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def add_member(
        self, team_id: str, user_id: str, role: str = "MEMBER", session: AsyncSession | None = None
    ) -> TeamMember:
        member_id = str(uuid.uuid4())
        orm = TeamMemberORM(
            id=member_id,
            team_id=team_id,
            user_id=user_id,
            role=role,
            created_at=utc_now(),
        )

        async def _exec(s: AsyncSession) -> TeamMember:
            s.add(orm)
            await s.commit()
            await s.refresh(orm)
            return self._to_member_model(orm)

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def remove_member(self, team_id: str, user_id: str, session: AsyncSession | None = None) -> bool:
        async def _exec(s: AsyncSession) -> bool:
            stmt = select(TeamMemberORM).where(TeamMemberORM.team_id == team_id, TeamMemberORM.user_id == user_id)
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

    async def delete(self, team_id: str, session: AsyncSession | None = None) -> bool:
        async def _exec(s: AsyncSession) -> bool:
            stmt = select(TeamORM).where(TeamORM.id == team_id)
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
    def _to_model(orm: TeamORM, members: list[TeamMember]) -> Team:
        return Team(
            id=orm.id,
            name=orm.name,
            description=orm.description,
            member_count=len(members),
            members=members,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @staticmethod
    def _to_member_model(orm: TeamMemberORM) -> TeamMember:
        return TeamMember(
            team_id=orm.team_id,
            user_id=orm.user_id,
            role=orm.role,
            created_at=orm.created_at,
        )
