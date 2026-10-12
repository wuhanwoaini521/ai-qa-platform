from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import uuid4

from project_model.models import FailureRepairState
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import AIInvocationORM, FailureRecordORM, LocatorRepairORM, TestRunORM, utc_now


class LocatorRepairRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, repair_id: str) -> LocatorRepairORM | None:
        return await self.session.get(LocatorRepairORM, repair_id)

    async def get_by_analysis(self, analysis_id: str) -> LocatorRepairORM | None:
        result = await self.session.execute(select(LocatorRepairORM).where(LocatorRepairORM.analysis_id == analysis_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        failure_id: str,
        *,
        analysis_id: str | None = None,
        state: FailureRepairState = FailureRepairState.CREATED,
        block_reason: str | None = None,
        candidate_id: str | None = None,
        verification_run_id: str | None = None,
        finished_at: datetime | None = None,
    ) -> LocatorRepairORM:
        if analysis_id:
            existing = await self.get_by_analysis(analysis_id)
            if existing is not None:
                return existing
        now = utc_now()
        row = LocatorRepairORM(
            id=str(uuid4()),
            failure_id=failure_id,
            analysis_id=analysis_id,
            state=state,
            block_reason=block_reason,
            candidate_id=candidate_id,
            verification_run_id=verification_run_id,
            created_at=now,
            updated_at=now,
            finished_at=finished_at,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            existing = await self.get_by_analysis(analysis_id) if analysis_id else None
            if existing is None:
                raise
            return existing
        return row

    async def flush(self) -> None:
        await self.session.flush()

    async def funnel(self, project_id: str | None = None) -> dict:
        filters = []
        if project_id:
            filters.append(TestRunORM.project_id == project_id)

        stages_result = await self.session.execute(
            select(LocatorRepairORM.state, func.count(LocatorRepairORM.id))
            .join(FailureRecordORM, FailureRecordORM.id == LocatorRepairORM.failure_id)
            .join(TestRunORM, TestRunORM.id == FailureRecordORM.run_id)
            .where(*filters)
            .group_by(LocatorRepairORM.state)
        )
        state_counts = {state.value: count for state, count in stages_result.all()}

        block_result = await self.session.execute(
            select(LocatorRepairORM.block_reason, func.count(LocatorRepairORM.id))
            .join(FailureRecordORM, FailureRecordORM.id == LocatorRepairORM.failure_id)
            .join(TestRunORM, TestRunORM.id == FailureRecordORM.run_id)
            .where(LocatorRepairORM.block_reason.is_not(None), *filters)
            .group_by(LocatorRepairORM.block_reason)
            .order_by(LocatorRepairORM.block_reason)
        )
        block_reasons = {reason: count for reason, count in block_result.all()}

        invocation_result = await self.session.execute(
            select(
                AIInvocationORM.task,
                AIInvocationORM.provider,
                AIInvocationORM.status,
                AIInvocationORM.fallback_used,
                func.count(AIInvocationORM.id),
            )
            .join(LocatorRepairORM, LocatorRepairORM.id == AIInvocationORM.locator_repair_id)
            .join(FailureRecordORM, FailureRecordORM.id == LocatorRepairORM.failure_id)
            .join(TestRunORM, TestRunORM.id == FailureRecordORM.run_id)
            .where(*filters)
            .group_by(
                AIInvocationORM.task,
                AIInvocationORM.provider,
                AIInvocationORM.status,
                AIInvocationORM.fallback_used,
            )
        )
        invocations_by_task: dict[str, int] = defaultdict(int)
        invocations_by_provider: dict[str, int] = defaultdict(int)
        invocations_by_status: dict[str, int] = defaultdict(int)
        invocation_total = fallback_total = 0
        for task, provider, status, fallback_used, count in invocation_result.all():
            invocations_by_task[task] += count
            invocations_by_provider[provider] += count
            invocations_by_status[status] += count
            invocation_total += count
            fallback_total += count if fallback_used else 0

        state_invocation_result = await self.session.execute(
            select(LocatorRepairORM.state, func.count(AIInvocationORM.id))
            .outerjoin(AIInvocationORM, AIInvocationORM.locator_repair_id == LocatorRepairORM.id)
            .join(FailureRecordORM, FailureRecordORM.id == LocatorRepairORM.failure_id)
            .join(TestRunORM, TestRunORM.id == FailureRecordORM.run_id)
            .where(*filters)
            .group_by(LocatorRepairORM.state)
        )
        invocations_by_state = {state.value: count for state, count in state_invocation_result.all()}

        return {
            "state_counts": state_counts,
            "blocking_reasons": block_reasons,
            "ai_invocations": {
                "total": invocation_total,
                "fallback": fallback_total,
                "by_task": dict(invocations_by_task),
                "by_provider": dict(invocations_by_provider),
                "by_status": dict(invocations_by_status),
                "by_repair_state": {state: invocations_by_state.get(state, 0) for state in state_counts},
                "linked_repairs": len(
                    {
                        repair_id
                        for (repair_id,) in (
                            await self.session.execute(
                                select(AIInvocationORM.locator_repair_id)
                                .join(
                                    LocatorRepairORM,
                                    LocatorRepairORM.id == AIInvocationORM.locator_repair_id,
                                )
                                .join(FailureRecordORM, FailureRecordORM.id == LocatorRepairORM.failure_id)
                                .join(TestRunORM, TestRunORM.id == FailureRecordORM.run_id)
                                .where(*filters, AIInvocationORM.locator_repair_id.is_not(None))
                                .distinct()
                            )
                        ).all()
                    }
                ),
            },
        }
