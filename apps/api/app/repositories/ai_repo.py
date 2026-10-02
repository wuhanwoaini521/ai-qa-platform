from __future__ import annotations

import uuid
from datetime import datetime

from project_model.models import AIInvocationDTO, AIUsageSummary
from sqlalchemy import case, desc, func, select

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
        decision_name: str | None = None,
        decision_choice: str | None = None,
        decision_confidence: float | None = None,
        request_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> AIInvocationORM:
        async with self.session_factory() as session:
            inv = AIInvocationORM(
                id=str(uuid.uuid4()),
                request_id=request_id,
                task_id=task_id,
                run_id=run_id,
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
                token_source="provider"
                if provider != "fake" and (input_tokens is not None or output_tokens is not None)
                else "unknown",
                decision_name=decision_name,
                decision_choice=decision_choice,
                decision_confidence=decision_confidence,
            )
            session.add(inv)
            await session.commit()
            await session.refresh(inv)
            return inv

    async def get_usage_summary(
        self, limit: int = 50, since: datetime | None = None, feature: str | None = None
    ) -> AIUsageSummary:
        async with self.session_factory() as session:
            conditions = []
            if since:
                conditions.append(AIInvocationORM.started_at >= since)
            if feature:
                conditions.append(AIInvocationORM.task == feature)
            stmt = select(AIInvocationORM).where(*conditions).order_by(desc(AIInvocationORM.started_at)).limit(limit)
            result = await session.execute(stmt)
            orms = list(result.scalars().all())

            # Aggregates
            agg_stmt = select(
                func.count(AIInvocationORM.id),
                func.sum(case((AIInvocationORM.token_source == "provider", AIInvocationORM.input_tokens), else_=None)),
                func.sum(case((AIInvocationORM.token_source == "provider", AIInvocationORM.output_tokens), else_=None)),
                func.sum(
                    case(((AIInvocationORM.status == "SUCCESS") & AIInvocationORM.fallback_used.is_(False), 1), else_=0)
                ),
                func.sum(case((AIInvocationORM.status.in_(["FAILED", "CANCELLED"]), 1), else_=0)),
                func.sum(case((AIInvocationORM.fallback_used.is_(True), 1), else_=0)),
                func.sum(case((AIInvocationORM.token_source != "provider", 1), else_=0)),
            ).where(*conditions)
            agg_res = await session.execute(agg_stmt)
            row = agg_res.one()
            total_reqs = row[0] or 0
            total_in = row[1] or 0
            total_out = row[2] or 0

            dtos = [AIInvocationDTO.model_validate(o) for o in orms]
            feature_rows = await session.execute(
                select(
                    AIInvocationORM.task,
                    func.count(AIInvocationORM.id),
                    func.avg(AIInvocationORM.duration_ms),
                    func.sum(case((AIInvocationORM.status == "FAILED", 1), else_=0)),
                    func.sum(case((AIInvocationORM.fallback_used.is_(True), 1), else_=0)),
                )
                .where(*conditions)
                .group_by(AIInvocationORM.task)
            )
            return AIUsageSummary(
                total_requests=total_reqs,
                total_input_tokens=total_in,
                total_output_tokens=total_out,
                invocations=dtos,
                successful_requests=row[3] or 0,
                failed_requests=row[4] or 0,
                fallback_requests=row[5] or 0,
                unknown_token_requests=row[6] or 0,
                features=[
                    {
                        "feature": item[0],
                        "requests": item[1],
                        "duration_ms": round(item[2] or 0, 1),
                        "failed": item[3] or 0,
                        "fallback": item[4] or 0,
                    }
                    for item in feature_rows
                ],
            )
