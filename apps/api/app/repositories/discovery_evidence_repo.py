"""Persistence for the structured discovery evidence index."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import DiscoveryEvidenceORM, DiscoveryScenarioORM, QualityDiscoveryRunORM


class EvidenceItem(Protocol):
    """What a capture record must look like; the repository never imports the capture service."""

    kind: str
    evidence_id: str
    dedupe_key: str
    payload: dict[str, Any]
    state_id: str | None
    step_id: str | None
    artifact_id: str | None
    source: str


class DiscoveryEvidenceRepository:
    """Writes capture batches and reads them back per run, kind and state."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def run_project_id(self, run_id: str) -> str | None:
        """The project a run belongs to, so a capture never has to open the run row itself."""
        row = await self.session.get(QualityDiscoveryRunORM, run_id)
        return row.project_id if row is not None else None

    async def record(
        self, run_id: str, project_id: str, records: Sequence[EvidenceItem], *, max_records: int
    ) -> dict[str, int]:
        """Insert new facts, keep an association the later capture learned, respect the run budget.

        A request can be captured twice: once as "present in this state" and once as "caused by this
        action". The second capture carries the association, so it upgrades the stored row instead of
        creating a duplicate — a fact we already know must not be lost by insert order.
        """
        if not records:
            return {"inserted": 0, "updated": 0, "skipped": 0, "capped": 0}
        ids = sorted({record.evidence_id for record in records})
        existing_rows = (
            (
                await self.session.execute(
                    select(DiscoveryEvidenceORM).where(
                        DiscoveryEvidenceORM.run_id == run_id, DiscoveryEvidenceORM.evidence_id.in_(ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        existing = {row.evidence_id: row for row in existing_rows}
        stored = await self.session.scalar(
            select(func.count()).select_from(DiscoveryEvidenceORM).where(DiscoveryEvidenceORM.run_id == run_id)
        )
        remaining = max(0, int(max_records) - int(stored or 0))

        inserted = updated = skipped = capped = 0
        for record in records:
            row = existing.get(record.evidence_id)
            if row is not None:
                if record.payload.get("action_evidence_id") and not (row.payload or {}).get("action_evidence_id"):
                    row.payload = {**(row.payload or {}), **record.payload}
                    row.step_id = record.step_id or row.step_id
                    updated += 1
                else:
                    skipped += 1
                continue
            if remaining <= 0:
                capped += 1
                continue
            remaining -= 1
            self.session.add(
                DiscoveryEvidenceORM(
                    id=str(uuid4()),
                    project_id=project_id,
                    run_id=run_id,
                    kind=record.kind,
                    evidence_id=record.evidence_id,
                    dedupe_key=record.dedupe_key[:600],
                    state_id=record.state_id,
                    step_id=record.step_id,
                    artifact_id=record.artifact_id,
                    source=record.source,
                    redacted=True,
                    payload=record.payload,
                )
            )
            inserted += 1
        await self.session.flush()
        return {"inserted": inserted, "updated": updated, "skipped": skipped, "capped": capped}

    async def list_by_run(
        self,
        run_id: str,
        *,
        kind: str | None = None,
        state_id: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[DiscoveryEvidenceORM]:
        query = select(DiscoveryEvidenceORM).where(DiscoveryEvidenceORM.run_id == run_id)
        if kind:
            query = query.where(DiscoveryEvidenceORM.kind == kind)
        if state_id:
            query = query.where(DiscoveryEvidenceORM.state_id == state_id)
        # Ordered by (created_at, evidence_id) so an offset page never repeats or skips a row.
        query = (
            query.order_by(DiscoveryEvidenceORM.created_at, DiscoveryEvidenceORM.evidence_id)
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.execute(query)).scalars().all())

    async def get(self, run_id: str, evidence_id: str) -> DiscoveryEvidenceORM | None:
        return (
            await self.session.execute(
                select(DiscoveryEvidenceORM).where(
                    DiscoveryEvidenceORM.run_id == run_id, DiscoveryEvidenceORM.evidence_id == evidence_id
                )
            )
        ).scalar_one_or_none()

    async def counts_by_kind(self, run_id: str) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(DiscoveryEvidenceORM.kind, func.count())
                .where(DiscoveryEvidenceORM.run_id == run_id)
                .group_by(DiscoveryEvidenceORM.kind)
            )
        ).all()
        return {str(kind): int(count) for kind, count in rows}

    async def count(self, run_id: str) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(DiscoveryEvidenceORM).where(DiscoveryEvidenceORM.run_id == run_id)
            )
            or 0
        )

    async def replace_scenarios(
        self, run_id: str, project_id: str, scenarios: Sequence[dict[str, Any]]
    ) -> list[DiscoveryScenarioORM]:
        """Recompute the derived scenario set for a run: derived rows are replaced, never merged."""
        existing = (
            (await self.session.execute(select(DiscoveryScenarioORM).where(DiscoveryScenarioORM.run_id == run_id)))
            .scalars()
            .all()
        )
        by_id = {row.scenario_id: row for row in existing}
        kept: list[DiscoveryScenarioORM] = []
        for item in scenarios:
            scenario_id = str(item["scenario_id"])
            row = by_id.get(scenario_id)
            if row is None:
                row = DiscoveryScenarioORM(
                    id=str(uuid4()),
                    project_id=project_id,
                    run_id=run_id,
                    scenario_id=scenario_id,
                    title=str(item.get("title") or scenario_id)[:300],
                    url_template=str(item.get("url_template") or "")[:600],
                    evidence_ids=list(item.get("evidence_ids") or []),
                    test_case_ids=list(item.get("test_case_ids") or []),
                    coverage_status=str(item.get("coverage_status") or "UNDETERMINED"),
                    match_method=item.get("match_method"),
                    note=item.get("note"),
                )
                self.session.add(row)
            else:
                row.title = str(item.get("title") or row.title)[:300]
                row.url_template = str(item.get("url_template") or "")[:600]
                row.evidence_ids = list(item.get("evidence_ids") or [])
                row.test_case_ids = list(item.get("test_case_ids") or [])
                row.coverage_status = str(item.get("coverage_status") or "UNDETERMINED")
                row.match_method = item.get("match_method")
                row.note = item.get("note")
            kept.append(row)
        keep_ids = {row.scenario_id for row in kept}
        for row in existing:
            if row.scenario_id not in keep_ids:
                await self.session.delete(row)
        await self.session.flush()
        return kept

    async def list_scenarios(self, run_id: str) -> list[DiscoveryScenarioORM]:
        return list(
            (
                await self.session.execute(
                    select(DiscoveryScenarioORM)
                    .where(DiscoveryScenarioORM.run_id == run_id)
                    .order_by(DiscoveryScenarioORM.scenario_id)
                )
            )
            .scalars()
            .all()
        )
