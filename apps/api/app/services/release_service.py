from __future__ import annotations

from project_model.models import (
    Release,
    ReleaseCreate,
    ReleaseGateReport,
    ReleaseStatus,
    ReleaseUpdate,
)

from app.persistence.models import ReleaseORM
from app.repositories.release_repo import ReleaseRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.quality_intelligence_service import QualityIntelligenceService


class ReleaseService:
    """Service orchestrating Release governance, quality gate evaluation, and release tracking."""

    def __init__(
        self,
        release_repo: ReleaseRepository,
        test_run_repo: TestRunRepository,
        quality_service: QualityIntelligenceService,
        history_repo: RunHistoryRepository | None = None,
    ) -> None:
        self.release_repo = release_repo
        self.test_run_repo = test_run_repo
        self.quality_service = quality_service
        self.history_repo = history_repo or RunHistoryRepository()

    def _to_dto(self, orm: ReleaseORM) -> Release:
        return Release(
            id=orm.id,
            project_id=orm.project_id,
            version=orm.version,
            name=orm.name,
            description=orm.description or "",
            status=ReleaseStatus(orm.status),
            target_date=orm.target_date or "",
            pass_rate_threshold=orm.pass_rate_threshold,
            max_allowed_flaky=orm.max_allowed_flaky,
            quality_score=orm.quality_score,
            blockers=orm.blockers or [],
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def list_releases(self, project_id: str | None = None) -> list[Release]:
        if project_id:
            orms = await self.release_repo.list_by_project(project_id)
        else:
            orms = await self.release_repo.list_all()
        return [self._to_dto(orm) for orm in orms]

    async def get_release(self, release_id: str) -> Release | None:
        orm = await self.release_repo.get_by_id(release_id)
        if not orm:
            return None
        return self._to_dto(orm)

    async def create_release(self, data: ReleaseCreate) -> Release:
        orm = await self.release_repo.create(data)
        return self._to_dto(orm)

    async def update_release(self, release_id: str, data: ReleaseUpdate) -> Release | None:
        orm = await self.release_repo.update(release_id, data)
        if not orm:
            return None
        return self._to_dto(orm)

    async def delete_release(self, release_id: str) -> bool:
        return await self.release_repo.delete(release_id)

    async def evaluate_release_gate(self, release_id: str) -> ReleaseGateReport:
        release = await self.get_release(release_id)
        if not release:
            raise ValueError(f"Release '{release_id}' not found")

        # 1. Fetch recent runs for the project
        runs = await self.test_run_repo.list_runs(project_id=release.project_id, limit=5)
        total_executed = 0
        total_passed = 0
        for r in runs:
            total_executed += r.total or 0
            total_passed += r.passed or 0

        pass_rate = round((total_passed / total_executed * 100.0), 1) if total_executed > 0 else 0.0

        # 2. Risk Matrix & Quality Score
        risk_matrix = await self.quality_service.calculate_risk_matrix(release.project_id)
        flaky_count = risk_matrix.flaky_test_count
        unautomated_p0 = risk_matrix.unautomated_p0_count
        quality_score = risk_matrix.overall_quality_score

        # 3. Gate checks
        pass_rate_met = pass_rate >= release.pass_rate_threshold
        flaky_met = flaky_count <= release.max_allowed_flaky
        unautomated_p0_met = unautomated_p0 == 0

        blockers: list[str] = list(release.blockers)
        if not pass_rate_met:
            blockers.append(f"Pass rate {pass_rate}% is below required threshold of {release.pass_rate_threshold}%.")
        if not flaky_met:
            blockers.append(f"Flaky test count ({flaky_count}) exceeds allowed maximum of {release.max_allowed_flaky}.")
        if not unautomated_p0_met:
            blockers.append(f"Project has {unautomated_p0} unautomated P0 critical test case(s).")

        can_release = len(blockers) == 0
        verdict = "READY_TO_RELEASE" if can_release else "BLOCKED"

        # Update release status & quality score
        new_status = ReleaseStatus.PASSED if can_release else ReleaseStatus.BLOCKED
        await self.release_repo.update(
            release_id,
            ReleaseUpdate(
                status=new_status,
                quality_score=quality_score,
                blockers=blockers,
            ),
        )

        return ReleaseGateReport(
            release_id=release.id,
            version=release.version,
            can_release=can_release,
            pass_rate=pass_rate,
            pass_rate_met=pass_rate_met,
            flaky_count=flaky_count,
            flaky_met=flaky_met,
            unautomated_p0_count=unautomated_p0,
            unautomated_p0_met=unautomated_p0_met,
            quality_score=quality_score,
            blockers=blockers,
            verdict=verdict,
        )
