"""Read and derive the structured evidence of one discovery run.

The run row stays the projection its existing consumers read; this service is the queryable view:
raw vs deduped counts, locator uniqueness, request/action association, candidate scenarios matched
against existing test cases, and a run-to-run diff. Derivation is deterministic and re-runnable.
"""

from __future__ import annotations

from typing import Any

from app.persistence.models import DiscoveryEvidenceORM, DiscoveryScenarioORM
from app.repositories.discovery_evidence_repo import DiscoveryEvidenceRepository
from app.repositories.quality_discovery_repo import QualityDiscoveryRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.services.discovery_evidence_analysis import (
    analyze_collection,
    build_scenarios,
    coverage_summary,
    diff_runs,
    match_scenarios,
)


class DiscoveryEvidenceNotFound(LookupError):
    pass


def evidence_dict(row: DiscoveryEvidenceORM) -> dict[str, Any]:
    return {
        "evidence_id": row.evidence_id,
        "kind": row.kind,
        "state_id": row.state_id,
        "step_id": row.step_id,
        "artifact_id": row.artifact_id,
        "source": row.source,
        "redacted": bool(row.redacted),
        "observed_at": row.observed_at.isoformat() if row.observed_at else None,
        "dedupe_key": row.dedupe_key,
        "payload": row.payload or {},
    }


def scenario_dict(row: DiscoveryScenarioORM) -> dict[str, Any]:
    return {
        "scenario_id": row.scenario_id,
        "title": row.title,
        "url_template": row.url_template,
        "evidence_ids": list(row.evidence_ids or []),
        "test_case_ids": list(row.test_case_ids or []),
        "coverage_status": row.coverage_status,
        "match_method": row.match_method,
        "note": row.note,
    }


class DiscoveryEvidenceService:
    def __init__(
        self,
        evidence: DiscoveryEvidenceRepository,
        discovery: QualityDiscoveryRepository,
        cases: TestCaseRepository,
    ):
        self.evidence = evidence
        self.discovery = discovery
        self.cases = cases

    async def _run(self, run_id: str):
        row = await self.discovery.get(run_id)
        if row is None:
            raise DiscoveryEvidenceNotFound("Quality Discovery run not found")
        return row

    async def collection(self, run_id: str) -> dict[str, Any]:
        row = await self._run(run_id)
        states = (row.result or {}).get("states") or []
        rows = await self.evidence.list_by_run(run_id, limit=20_000)
        return {
            "run_id": run_id,
            "project_id": row.project_id,
            "capture_enabled": bool((row.result or {}).get("runtime_config", {}).get("capture_evidence", True)),
            "counts": await self.evidence.counts_by_kind(run_id),
            "analysis": analyze_collection(rows, states),
        }

    async def list_evidence(
        self, run_id: str, *, kind: str | None = None, state_id: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        await self._run(run_id)
        rows = await self.evidence.list_by_run(run_id, kind=kind, state_id=state_id, limit=limit)
        return [evidence_dict(row) for row in rows]

    async def evidence_detail(self, run_id: str, evidence_id: str) -> dict[str, Any]:
        await self._run(run_id)
        row = await self.evidence.get(run_id, evidence_id)
        if row is None:
            raise DiscoveryEvidenceNotFound("Evidence not found")
        return evidence_dict(row)

    async def refresh_scenarios(self, run_id: str) -> dict[str, Any]:
        """Derive candidate scenarios from this run's evidence and match them to existing cases."""
        row = await self._run(run_id)
        rows = await self.evidence.list_by_run(run_id, limit=20_000)
        scenarios = build_scenarios(rows)
        case_rows = await self.cases.list_by_project(row.project_id, limit=2000)
        cases = [
            {
                "id": case.id,
                "title": case.title,
                "steps": case.steps or [],
                "expected_result": case.expected_result,
                "preconditions": case.preconditions,
                "tags": case.tags or [],
                "binding": {"file_path": case.binding.file_path, "test_name": case.binding.nodeid}
                if case.binding is not None
                else None,
            }
            for case in case_rows
        ]
        matched = match_scenarios(scenarios, cases)
        stored = await self.evidence.replace_scenarios(run_id, row.project_id, matched)
        await self.evidence.session.commit()
        return {
            "run_id": run_id,
            "project_id": row.project_id,
            "summary": coverage_summary(stored),
            "scenarios": [scenario_dict(item) for item in stored],
        }

    async def scenarios(self, run_id: str) -> dict[str, Any]:
        row = await self._run(run_id)
        stored = await self.evidence.list_scenarios(run_id)
        return {
            "run_id": run_id,
            "project_id": row.project_id,
            "summary": coverage_summary(stored),
            "scenarios": [scenario_dict(item) for item in stored],
        }

    async def diff(self, run_id: str, against: str | None = None) -> dict[str, Any]:
        """Compare this run with another run of the same scope, by stable dedupe keys."""
        current_run = await self._run(run_id)
        previous_id = against or await self._previous_run_id(current_run)
        if not previous_id:
            return {
                "current_run_id": run_id,
                "previous_run_id": None,
                "comparable": False,
                "reason": "no_earlier_run_with_the_same_start_url",
                "kinds": {},
            }
        previous_run = await self._run(previous_id)
        current_rows = await self.evidence.list_by_run(run_id, limit=20_000)
        previous_rows = await self.evidence.list_by_run(previous_id, limit=20_000)
        result = diff_runs(current_rows, previous_rows, current_run_id=run_id, previous_run_id=previous_id)
        result["scope"] = {
            "same_start_url": current_run.start_url == previous_run.start_url,
            "same_mode": current_run.mode == previous_run.mode,
            "current": {
                "start_url": current_run.start_url,
                "mode": current_run.mode,
                "created_at": current_run.created_at.isoformat() if current_run.created_at else None,
                "evidence_rows": len(current_rows),
            },
            "previous": {
                "start_url": previous_run.start_url,
                "mode": previous_run.mode,
                "created_at": previous_run.created_at.isoformat() if previous_run.created_at else None,
                "evidence_rows": len(previous_rows),
            },
        }
        return result

    async def _previous_run_id(self, current) -> str | None:
        rows = await self.discovery.list_by_project(current.project_id, limit=50)
        for row in rows:
            if row.id == current.id:
                continue
            if row.start_url != current.start_url:
                continue
            if row.created_at and current.created_at and row.created_at >= current.created_at:
                continue
            return row.id
        return None
