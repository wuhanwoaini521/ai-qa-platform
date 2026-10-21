"""Read, review and re-request the model-assisted readings of uncovered scenarios.

Nothing here changes the deterministic scenario verdict: a suggestion adds reasoning, the evidence
it read and a human decision. A test case is only written when a reviewer approved that exact step.
"""

from __future__ import annotations

from typing import Any

from project_model.models import TestCaseCreate, TestCasePriority
from project_model.task_models import TaskType

from app.persistence.models import DiscoverySuggestionORM
from app.repositories.discovery_evidence_repo import DiscoveryEvidenceRepository
from app.repositories.discovery_suggestion_repo import DiscoverySuggestionRepository
from app.repositories.quality_discovery_repo import QualityDiscoveryRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.services.test_case_service import TestCaseService

DECISIONS = {"ACCEPT", "REJECT", "LINK_CASE", "APPROVE_CREATE_CASE", "REANALYZE"}
LIVE_TASK_STATUSES = {"PENDING", "RUNNING", "PAUSED", "WAITING", "VERIFYING", "REPLANNING", "RETRYING"}


class DiscoverySuggestionNotFound(LookupError):
    pass


class DiscoverySuggestionError(ValueError):
    pass


def suggestion_dict(row: DiscoverySuggestionORM) -> dict[str, Any]:
    payload = row.payload or {}
    jev = row.jev or {}
    return {
        "suggestion_id": row.suggestion_id,
        "scenario_id": row.scenario_id,
        "source": row.source,
        "provider": row.provider,
        "model": row.model,
        "analysis_status": row.analysis_status,
        "review_status": row.review_status,
        "input_hash": row.input_hash,
        "attempts": row.attempts,
        "task_id": row.task_id,
        "invocation_id": row.invocation_id,
        "evidence_ids": list(row.evidence_ids or []),
        "related_case_ids": list(row.related_case_ids or []),
        "is_gap": payload.get("is_gap"),
        "summary": payload.get("summary") or "",
        "reasoning": payload.get("reasoning") or "",
        "grounded": bool(payload.get("grounded")),
        "suggested_title": payload.get("suggested_title") or "",
        "suggested_steps": list(payload.get("suggested_steps") or []),
        "uncertainty": payload.get("uncertainty") or "",
        "needs_human_review": payload.get("needs_human_review"),
        "risk": payload.get("risk") or "",
        "coverage_status": payload.get("coverage_status"),
        "match_method": payload.get("match_method"),
        "scenario_title": payload.get("scenario_title") or "",
        "url_template": payload.get("url_template") or "",
        "evidence_kinds": list(payload.get("evidence_kinds") or []),
        "rule_grade": jev.get("rule_grade"),
        "grade": jev.get("grade"),
        "grade_source": jev.get("source", "rules"),
        "jev": jev,
        "review": row.review or {},
        "reason": payload.get("reason") or "",
        "unknown_evidence_ids": list(payload.get("unknown_evidence_ids") or []),
        "unknown_test_case_ids": list(payload.get("unknown_test_case_ids") or []),
        "error_type": row.error_type,
        "duration_ms": row.duration_ms,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "token_source": row.token_source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def suggestion_summary(rows: list[DiscoverySuggestionORM]) -> dict[str, Any]:
    """One counting pass over the stored readings; the canvas reads the same numbers."""
    by_review: dict[str, int] = {}
    by_status: dict[str, int] = {}
    jev_statuses: dict[str, int] = {}
    grade_sources: dict[str, int] = {}
    for row in rows:
        by_review[str(row.review_status)] = by_review.get(str(row.review_status), 0) + 1
        by_status[str(row.analysis_status)] = by_status.get(str(row.analysis_status), 0) + 1
        jev_status = str((row.jev or {}).get("status") or "NOT_GRADED")
        jev_statuses[jev_status] = jev_statuses.get(jev_status, 0) + 1
        source = str((row.jev or {}).get("source") or "none")
        grade_sources[source] = grade_sources.get(source, 0) + 1
    return {
        "total": len(rows),
        "pending_review": by_review.get("PENDING", 0),
        "accepted": by_review.get("ACCEPTED", 0),
        "rejected": by_review.get("REJECTED", 0),
        "linked": by_review.get("LINKED", 0),
        "created_cases": by_review.get("CASE_CREATED", 0),
        "by_analysis_status": by_status,
        "by_review_status": by_review,
        "jev_graded": jev_statuses.get("JEV_GRADED", 0),
        "jev_fallback": sum(
            count
            for status, count in jev_statuses.items()
            if status in {"JEV_LOW_CONFIDENCE", "JEV_TIMEOUT", "JEV_FALLBACK", "JEV_UNAVAILABLE"}
        ),
        "jev_statuses": jev_statuses,
        "grade_sources": grade_sources,
    }


class DiscoveryIntelligenceService:
    """Own the review gate and the bounded re-analysis request for one discovery run."""

    def __init__(
        self,
        discovery: QualityDiscoveryRepository,
        evidence: DiscoveryEvidenceRepository,
        suggestions: DiscoverySuggestionRepository,
        tasks: TaskRepository,
        test_cases: TestCaseRepository,
    ) -> None:
        self.discovery = discovery
        self.evidence = evidence
        self.suggestions = suggestions
        self.tasks = tasks
        self.test_cases = test_cases

    async def _require_run(self, run_id: str) -> None:
        """A run that does not exist answers 404 instead of an empty advice list."""
        if await self.discovery.get(run_id) is None:
            raise DiscoverySuggestionNotFound(f"Discovery run not found: {run_id}")

    async def suggestions_for(self, run_id: str) -> dict[str, Any]:
        await self._require_run(run_id)
        rows = await self.suggestions.list_by_run(run_id, limit=500)
        summary = await self.summary(run_id)
        return {"suggestions": [suggestion_dict(row) for row in rows], "summary": summary}

    async def summary(self, run_id: str) -> dict[str, Any]:
        await self._require_run(run_id)
        return suggestion_summary(await self.suggestions.list_by_run(run_id, limit=500))

    async def detail(self, run_id: str, suggestion_id: str) -> dict[str, Any]:
        row = await self.suggestions.get(run_id, suggestion_id)
        if row is None:
            raise DiscoverySuggestionNotFound(suggestion_id)
        cited = []
        for evidence_id in row.evidence_ids or []:
            evidence_row = await self.evidence.get(run_id, evidence_id)
            if evidence_row is not None:
                cited.append(
                    {
                        "evidence_id": evidence_row.evidence_id,
                        "kind": evidence_row.kind,
                        "state_id": evidence_row.state_id,
                        "artifact_id": evidence_row.artifact_id,
                        "payload": evidence_row.payload or {},
                    }
                )
        cases = []
        for case_id in row.related_case_ids or []:
            case = await self.test_cases.get_by_id(case_id)
            if case is not None:
                cases.append(
                    {
                        "id": case.id,
                        "title": case.title,
                        "file_path": case.binding.file_path if case.binding else None,
                    }
                )
        return {**suggestion_dict(row), "evidence": cited, "related_cases": cases}

    async def review(
        self,
        run_id: str,
        suggestion_id: str,
        *,
        decision: str,
        actor_id: str,
        comment: str = "",
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if decision not in DECISIONS:
            raise DiscoverySuggestionError(f"Unsupported review decision: {decision}.")
        row = await self.suggestions.get(run_id, suggestion_id)
        if row is None:
            raise DiscoverySuggestionNotFound(suggestion_id)
        if row.analysis_status != "COMPLETED":
            raise DiscoverySuggestionError(
                f"Only a completed suggestion can be reviewed; this one is {row.analysis_status}."
            )
        linkage = list(dict.fromkeys(str(item) for item in (case_ids or row.related_case_ids or [])))
        created_case_id = None
        review_status = {
            "ACCEPT": "ACCEPTED",
            "REJECT": "REJECTED",
            "LINK_CASE": "LINKED",
            "APPROVE_CREATE_CASE": "CASE_CREATED",
            "REANALYZE": "REANALYZE_REQUESTED",
        }[decision]
        if decision == "APPROVE_CREATE_CASE":
            created_case_id = (row.review or {}).get("created_case_id")
            if not created_case_id:
                created_case_id = await self._create_case(row)
        if decision == "REJECT" and not comment.strip():
            raise DiscoverySuggestionError("A rejection needs a reason so the next analysis can use it.")
        review = {
            "decision": review_status,
            "actor_id": actor_id,
            "comment": comment,
            "case_ids": linkage,
            "created_case_id": created_case_id,
            "at": _now(),
        }
        updated = await self.suggestions.set_review(run_id, suggestion_id, review)
        if updated is None:
            raise DiscoverySuggestionNotFound(suggestion_id)
        return {
            "suggestion": suggestion_dict(updated),
            "created_case_id": created_case_id,
            "review": review,
        }

    async def _create_case(self, row: DiscoverySuggestionORM) -> str:
        payload = row.payload or {}
        title = str(payload.get("suggested_title") or payload.get("summary") or "").strip()
        if not title:
            raise DiscoverySuggestionError("This suggestion has no title to become a test case.")
        steps = [
            f"{step.get('action') or 'act'} {step.get('target') or ''}".strip()
            for step in payload.get("suggested_steps") or []
        ]
        expectations = [str(step.get("expectation") or "").strip() for step in payload.get("suggested_steps") or []]
        service = TestCaseService(
            test_case_repo=self.test_cases,
            requirement_repo=_Unavailable(),
            test_design_repo=_Unavailable(),
        )
        case = await service.create_test_case(
            TestCaseCreate(
                project_id=row.project_id,
                title=title[:250],
                preconditions=str(payload.get("reasoning") or "")[:2000],
                steps=steps or [str(payload.get("summary") or "Review the recorded behaviour")[:500]],
                expected_result="; ".join(item for item in expectations if item)[:2000]
                or str(payload.get("uncertainty") or "")[:2000]
                or "Confirm the expected result against the recorded evidence.",
                priority=TestCasePriority.P2,
                # Provenance is explicit so acceptance data created by the real approval path can be
                # singled out later without guessing from the title.
                tags=["discovery", "ai-suggestion", "candidate-gap", f"suggestion:{row.suggestion_id}"],
            )
        )
        return case.id

    async def live_task(self, project_id: str, run_id: str) -> dict[str, Any] | None:
        """An analysis already in flight for this run is the answer to a repeated request."""
        for row in await self.tasks.list_by_project(project_id, task_type=TaskType.ANALYZE_DISCOVERY.value, limit=20):
            if row.type != TaskType.ANALYZE_DISCOVERY.value:
                continue
            if str((row.inputs or {}).get("discovery_run_id")) != run_id:
                continue
            if row.status in LIVE_TASK_STATUSES:
                return {"task_id": row.id, "status": row.status, "reused": True}
        return None


class _Unavailable:
    """Case creation here never invents a requirement or design, so those repositories are unused."""

    async def get_by_id(self, _id: str):
        return None


def _now() -> str:
    from app.persistence.models import utc_now

    return utc_now().isoformat()
