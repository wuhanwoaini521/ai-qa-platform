from __future__ import annotations

import uuid
from datetime import datetime

from project_model.models import AIInvocationDTO, AIUsageSummary
from sqlalchemy import desc, func, select

from app.persistence import database
from app.persistence.models import AIInvocationORM, utc_now


class AIRepository:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    @property
    def session_factory(self):
        if self._session_factory is not None:
            return self._session_factory

        return database.get_session

    async def record_invocation(
        self,
        task: str,
        provider: str,
        model: str,
        duration_ms: float = 0.0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        retry_count: int = 0,
        fallback_used: bool = False,
        status: str = "SUCCESS",
        error_type: str | None = None,
        prompt_version: str | None = None,
        started_at: datetime | None = None,
    ) -> AIInvocationORM:
        async with self.session_factory() as session:
            inv = AIInvocationORM(
                id=str(uuid.uuid4()),
                task=task,
                provider=provider,
                model=model,
                started_at=started_at or utc_now(),
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                retry_count=retry_count,
                fallback_used=fallback_used,
                status=status,
                error_type=error_type,
                prompt_version=prompt_version,
            )
            session.add(inv)
            await session.commit()
            await session.refresh(inv)
            return inv

    async def get_usage_summary(self, limit: int = 50) -> AIUsageSummary:
        async with self.session_factory() as session:
            stmt = select(AIInvocationORM).order_by(desc(AIInvocationORM.started_at)).limit(limit)
            result = await session.execute(stmt)
            orms = list(result.scalars().all())

            # Aggregates
            agg_stmt = select(
                func.count(AIInvocationORM.id),
                func.sum(AIInvocationORM.input_tokens),
                func.sum(AIInvocationORM.output_tokens),
            )
            agg_res = await session.execute(agg_stmt)
            row = agg_res.one()
            total_reqs = row[0] or 0
            total_in = row[1] or 0
            total_out = row[2] or 0

            dtos = [AIInvocationDTO.model_validate(o) for o in orms]
            return AIUsageSummary(
                total_requests=total_reqs,
                total_input_tokens=total_in,
                total_output_tokens=total_out,
                invocations=dtos,
            )
