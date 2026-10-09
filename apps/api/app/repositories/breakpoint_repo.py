from __future__ import annotations

from collections.abc import Sequence

from project_model.models import Breakpoint, BreakpointUpsert
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import BreakpointORM


class BreakpointRepository:
    """Persistence operations for debugger breakpoints; transaction ownership stays above."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_workspace(self, workspace_id: str) -> Sequence[Breakpoint]:
        result = await self.session.execute(
            select(BreakpointORM)
            .where(BreakpointORM.workspace_id == workspace_id)
            .order_by(BreakpointORM.file_path, BreakpointORM.line_number, BreakpointORM.source)
        )
        return [Breakpoint.model_validate(row, from_attributes=True) for row in result.scalars()]

    async def list_enabled_for_workspace(self, workspace_id: str) -> Sequence[Breakpoint]:
        result = await self.session.execute(
            select(BreakpointORM)
            .where(BreakpointORM.workspace_id == workspace_id, BreakpointORM.enabled.is_(True))
            .order_by(BreakpointORM.file_path, BreakpointORM.line_number)
        )
        return [Breakpoint.model_validate(row, from_attributes=True) for row in result.scalars()]

    async def upsert_manual(self, workspace_id: str, payload: BreakpointUpsert, file_path: str) -> Breakpoint:
        result = await self.session.execute(
            select(BreakpointORM).where(
                BreakpointORM.workspace_id == workspace_id,
                BreakpointORM.file_path == file_path,
                BreakpointORM.line_number == payload.line_number,
                BreakpointORM.source == "manual",
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = BreakpointORM(
                workspace_id=workspace_id,
                file_path=file_path,
                line_number=payload.line_number,
                enabled=payload.enabled,
                source="manual",
            )
            self.session.add(row)
        else:
            row.enabled = payload.enabled
        await self.session.flush()
        return Breakpoint.model_validate(row, from_attributes=True)

    async def upsert_failure(self, workspace_id: str, file_path: str, line_number: int, run_id: str) -> Breakpoint:
        result = await self.session.execute(
            select(BreakpointORM).where(
                BreakpointORM.workspace_id == workspace_id,
                BreakpointORM.file_path == file_path,
                BreakpointORM.line_number == line_number,
                BreakpointORM.source == "auto_failure",
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = BreakpointORM(
                workspace_id=workspace_id,
                file_path=file_path,
                line_number=line_number,
                enabled=True,
                source="auto_failure",
                run_id=run_id,
            )
            self.session.add(row)
        else:
            row.enabled = True
            row.run_id = run_id
        await self.session.flush()
        return Breakpoint.model_validate(row, from_attributes=True)

    async def delete(self, workspace_id: str, breakpoint_id: str) -> bool:
        result = await self.session.execute(
            select(BreakpointORM).where(
                BreakpointORM.workspace_id == workspace_id,
                BreakpointORM.id == breakpoint_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True
