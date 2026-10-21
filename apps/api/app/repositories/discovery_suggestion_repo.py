from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import DiscoverySuggestionORM, utc_now


class DiscoverySuggestionRepository:
    """Persist model-assisted suggestions apart from the rule verdict, keyed for idempotency."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_many(
        self,
        run_id: str,
        project_id: str,
        suggestions: Sequence[dict[str, Any]],
    ) -> dict[str, int]:
        """Write one row per (scenario, input hash); an identical request only bumps the attempt count."""
        counts = {"inserted": 0, "updated": 0, "skipped": 0}
        if not suggestions:
            return counts
        keys = {(item["scenario_id"], item["input_hash"]) for item in suggestions}
        existing = {
            (row.scenario_id, row.input_hash): row
            for row in (
                await self.session.execute(
                    select(DiscoverySuggestionORM).where(
                        DiscoverySuggestionORM.run_id == run_id,
                        DiscoverySuggestionORM.input_hash.in_({key[1] for key in keys}),
                    )
                )
            ).scalars()
        }
        for item in suggestions:
            key = (item["scenario_id"], item["input_hash"])
            row = existing.get(key)
            if row is None:
                self.session.add(
                    DiscoverySuggestionORM(
                        id=str(uuid4()),
                        project_id=project_id,
                        run_id=run_id,
                        suggestion_id=item["suggestion_id"],
                        scenario_id=item["scenario_id"],
                        source=item.get("source", "ai"),
                        provider=item.get("provider", ""),
                        model=item.get("model", ""),
                        analysis_status=item["analysis_status"],
                        review_status="PENDING",
                        input_hash=item["input_hash"],
                        attempts=1,
                        task_id=item.get("task_id"),
                        invocation_id=item.get("invocation_id"),
                        evidence_ids=list(item.get("evidence_ids", [])),
                        related_case_ids=list(item.get("related_case_ids", [])),
                        payload=dict(item.get("payload", {})),
                        jev=dict(item.get("jev", {})),
                        review={},
                        duration_ms=item.get("duration_ms"),
                        input_tokens=item.get("input_tokens"),
                        output_tokens=item.get("output_tokens"),
                        token_source=item.get("token_source", "unknown"),
                        error_type=item.get("error_type"),
                        error_detail=item.get("error_detail"),
                    )
                )
                counts["inserted"] += 1
                continue
            if row.payload.get("fingerprint") != item.get("payload", {}).get("fingerprint"):
                counts["skipped"] += 1
                continue
            row.attempts = (row.attempts or 0) + 1
            row.analysis_status = item["analysis_status"]
            row.error_type = item.get("error_type")
            row.error_detail = item.get("error_detail")
            row.task_id = item.get("task_id") or row.task_id
            row.invocation_id = item.get("invocation_id") or row.invocation_id
            row.duration_ms = item.get("duration_ms")
            row.input_tokens = item.get("input_tokens")
            row.output_tokens = item.get("output_tokens")
            row.token_source = item.get("token_source", row.token_source)
            row.updated_at = utc_now()
            counts["updated"] += 1
        await self.session.flush()
        return counts

    async def list_by_run(
        self,
        run_id: str,
        *,
        review_status: str | None = None,
        limit: int = 200,
    ) -> list[DiscoverySuggestionORM]:
        statement = select(DiscoverySuggestionORM).where(DiscoverySuggestionORM.run_id == run_id)
        if review_status:
            statement = statement.where(DiscoverySuggestionORM.review_status == review_status)
        statement = statement.order_by(DiscoverySuggestionORM.created_at, DiscoverySuggestionORM.suggestion_id).limit(
            limit
        )
        return list((await self.session.execute(statement)).scalars())

    async def get(self, run_id: str, suggestion_id: str) -> DiscoverySuggestionORM | None:
        return (
            await self.session.execute(
                select(DiscoverySuggestionORM).where(
                    DiscoverySuggestionORM.run_id == run_id,
                    DiscoverySuggestionORM.suggestion_id == suggestion_id,
                )
            )
        ).scalar_one_or_none()

    async def latest_by_scenario(self, run_id: str) -> dict[str, DiscoverySuggestionORM]:
        """The newest suggestion per scenario, so a re-analysis does not hide the previous reading."""
        rows = await self.list_by_run(run_id, limit=1000)
        latest: dict[str, DiscoverySuggestionORM] = {}
        for row in rows:
            current = latest.get(row.scenario_id)
            if current is None or (row.created_at or utc_now()) >= (current.created_at or utc_now()):
                latest[row.scenario_id] = row
        return latest

    async def set_jev(self, run_id: str, suggestion_id: str, jev: dict[str, Any]) -> DiscoverySuggestionORM | None:
        row = await self.get(run_id, suggestion_id)
        if row is None:
            return None
        row.jev = dict(jev)
        row.updated_at = utc_now()
        await self.session.flush()
        return row

    async def set_review(
        self,
        run_id: str,
        suggestion_id: str,
        review: dict[str, Any],
    ) -> DiscoverySuggestionORM | None:
        row = await self.get(run_id, suggestion_id)
        if row is None:
            return None
        row.review = dict(review)
        row.review_status = str(review.get("decision", "PENDING"))
        row.updated_at = utc_now()
        await self.session.flush()
        return row

    async def counts_by_review(self, run_id: str) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(DiscoverySuggestionORM.review_status, func.count())
                .where(DiscoverySuggestionORM.run_id == run_id)
                .group_by(DiscoverySuggestionORM.review_status)
            )
        ).all()
        return {str(status): int(count) for status, count in rows}

    async def counts_by_status(self, run_id: str) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(DiscoverySuggestionORM.analysis_status, func.count())
                .where(DiscoverySuggestionORM.run_id == run_id)
                .group_by(DiscoverySuggestionORM.analysis_status)
            )
        ).all()
        return {str(status): int(count) for status, count in rows}
