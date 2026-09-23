from __future__ import annotations

import statistics
from datetime import datetime

from project_model.models import (
    FailureRecurrenceItem,
    FlakyClassification,
    FlakyScore,
    FlakyTestItem,
    RunStatus,
    TestHistoryItem,
    TestHistoryResponse,
    TestTrend,
)
from sqlalchemy import desc, select

from app.persistence import database
from app.persistence.models import (
    FailureRecordORM,
    TestExecutionORM,
    TestRunORM,
)


class RunHistoryRepository:
    """Repository providing historical execution analytics, trend calculation, and deterministic flaky scoring."""

    def __init__(self, session_factory=None, min_samples_threshold: int = 3) -> None:
        self._session_factory = session_factory
        self.min_samples_threshold = min_samples_threshold

    @property
    def session_factory(self):
        if self._session_factory is not None:
            return self._session_factory

        return database.get_session

    async def get_test_executions(
        self,
        nodeid: str,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[TestExecutionORM]:
        async with self.session_factory() as session:
            stmt = (
                select(TestExecutionORM)
                .join(TestRunORM, TestExecutionORM.run_id == TestRunORM.id)
                .where(TestExecutionORM.nodeid == nodeid)
            )
            if project_id:
                stmt = stmt.where(TestRunORM.project_id == project_id)

            stmt = stmt.order_by(desc(TestExecutionORM.started_at), desc(TestExecutionORM.id)).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_test_history_detail(
        self,
        nodeid: str,
        project_id: str,
        limit: int = 20,
    ) -> TestHistoryResponse:
        executions = await self.get_test_executions(nodeid=nodeid, project_id=project_id, limit=limit)
        items = [
            TestHistoryItem(
                id=e.id,
                run_id=e.run_id,
                nodeid=e.nodeid,
                status=RunStatus(e.status),
                duration_ms=e.duration_ms,
                retry_count=e.retry_count,
                failure_category=e.failure_category,
                error_message=e.error_message,
                started_at=e.started_at,
            )
            for e in executions
        ]

        trend = self.calculate_trend(executions)
        flaky = self.calculate_flaky_score(executions)

        return TestHistoryResponse(
            nodeid=nodeid,
            project_id=project_id,
            executions=items,
            trend=trend,
            flaky_score=flaky,
        )

    def calculate_trend(self, executions: list[TestExecutionORM]) -> TestTrend:
        sample_count = len(executions)
        if sample_count == 0:
            return TestTrend()

        pass_count = sum(1 for e in executions if e.status == RunStatus.PASSED.value)
        fail_count = sum(1 for e in executions if e.status == RunStatus.FAILED.value)
        skip_count = sum(1 for e in executions if e.status == RunStatus.SKIPPED.value)
        retry_count = sum(e.retry_count for e in executions)

        durations = [e.duration_ms for e in executions if e.duration_ms > 0]
        avg_dur = float(statistics.mean(durations)) if durations else 0.0
        p95_dur = (
            float(statistics.quantiles(durations, n=20)[-1])
            if len(durations) >= 5
            else (max(durations) if durations else 0.0)
        )

        categories: dict[str, int] = {}
        for e in executions:
            if e.failure_category:
                categories[e.failure_category] = categories.get(e.failure_category, 0) + 1

        return TestTrend(
            sample_count=sample_count,
            pass_count=pass_count,
            fail_count=fail_count,
            skip_count=skip_count,
            average_duration_ms=round(avg_dur, 2),
            p95_duration_ms=round(p95_dur, 2),
            retry_count=retry_count,
            failure_categories=categories,
        )

    def calculate_flaky_score(self, executions: list[TestExecutionORM]) -> FlakyScore:
        sample_count = len(executions)

        # Gate 6.6: Minimum sample guard
        if sample_count < self.min_samples_threshold:
            return FlakyScore(
                sample_count=sample_count,
                failure_rate=0.0,
                rerun_recovery_rate=0.0,
                alternation_rate=0.0,
                recent_instability=0.0,
                score=0.0,
                confidence=round(sample_count / 10.0, 2),
                classification=FlakyClassification.INSUFFICIENT_DATA,
            )

        # Calculate failure rate
        fail_count = sum(1 for e in executions if e.status == RunStatus.FAILED.value)
        pass_count = sum(1 for e in executions if e.status == RunStatus.PASSED.value)
        failure_rate = fail_count / sample_count

        # All pass -> STABLE
        if fail_count == 0:
            return FlakyScore(
                sample_count=sample_count,
                failure_rate=0.0,
                rerun_recovery_rate=0.0,
                alternation_rate=0.0,
                recent_instability=0.0,
                score=0.0,
                confidence=min(1.0, round(sample_count / 10.0, 2)),
                classification=FlakyClassification.STABLE,
            )

        # All fail -> PERSISTENT_FAILURE
        if pass_count == 0:
            return FlakyScore(
                sample_count=sample_count,
                failure_rate=1.0,
                rerun_recovery_rate=0.0,
                alternation_rate=0.0,
                recent_instability=1.0,
                score=0.05,
                confidence=min(1.0, round(sample_count / 10.0, 2)),
                classification=FlakyClassification.PERSISTENT_FAILURE,
            )

        # Alternation rate: chronological ordering (oldest -> newest)
        ordered = list(reversed(executions))
        status_seq = [e.status for e in ordered]
        transitions = 0
        for i in range(len(status_seq) - 1):
            if status_seq[i] != status_seq[i + 1]:
                transitions += 1
        alternation_rate = transitions / (sample_count - 1) if sample_count > 1 else 0.0

        # Rerun recovery rate
        recovered = sum(1 for e in executions if e.retry_count > 0 and e.status == RunStatus.PASSED.value)
        rerun_recovery_rate = recovered / fail_count if fail_count > 0 else 0.0

        # Recent instability (weighted toward most recent 5 executions)
        recent_slice = executions[:5]
        recent_fails = sum(1 for e in recent_slice if e.status == RunStatus.FAILED.value)
        recent_passes = sum(1 for e in recent_slice if e.status == RunStatus.PASSED.value)
        recent_instability = (recent_fails / len(recent_slice)) if (recent_fails > 0 and recent_passes > 0) else 0.0

        # Composite score
        raw_score = (0.45 * alternation_rate) + (0.35 * rerun_recovery_rate) + (0.20 * recent_instability)
        score = min(1.0, round(raw_score, 3))
        confidence = min(1.0, round(sample_count / 10.0, 2))

        # Main failure category & last failure timestamp
        main_cat: str | None = None
        categories: dict[str, int] = {}
        last_failure_at: datetime | None = None

        for e in executions:
            if e.status == RunStatus.FAILED.value:
                if last_failure_at is None and e.started_at:
                    last_failure_at = e.started_at
                if e.failure_category:
                    categories[e.failure_category] = categories.get(e.failure_category, 0) + 1

        if categories:
            main_cat = max(categories.items(), key=lambda x: x[1])[0]

        # Classification decision
        if failure_rate >= 0.85:
            classification = FlakyClassification.PERSISTENT_FAILURE
        elif score >= 0.25:
            classification = FlakyClassification.LIKELY_FLAKY
        else:
            classification = FlakyClassification.STABLE

        return FlakyScore(
            sample_count=sample_count,
            failure_rate=round(failure_rate, 3),
            rerun_recovery_rate=round(rerun_recovery_rate, 3),
            alternation_rate=round(alternation_rate, 3),
            recent_instability=round(recent_instability, 3),
            score=score,
            confidence=confidence,
            classification=classification,
            main_failure_category=main_cat,
            last_failure_at=last_failure_at,
        )

    async def list_flaky_tests(
        self,
        project_id: str | None = None,
        min_score: float = 0.0,
        classification: FlakyClassification | None = None,
    ) -> list[FlakyTestItem]:
        async with self.session_factory() as session:
            # Query distinct nodeids
            stmt = select(TestExecutionORM.nodeid, TestRunORM.project_id).join(
                TestRunORM, TestExecutionORM.run_id == TestRunORM.id
            )
            if project_id:
                stmt = stmt.where(TestRunORM.project_id == project_id)
            stmt = stmt.distinct()

            result = await session.execute(stmt)
            distinct_tests = result.all()

        flaky_items: list[FlakyTestItem] = []
        for row in distinct_tests:
            nodeid = row[0]
            pid = row[1]
            executions = await self.get_test_executions(nodeid=nodeid, project_id=pid, limit=20)
            score = self.calculate_flaky_score(executions)
            trend = self.calculate_trend(executions)

            if score.score >= min_score:
                if classification is None or score.classification == classification:
                    flaky_items.append(
                        FlakyTestItem(
                            nodeid=nodeid,
                            test_name=nodeid.split("::")[-1],
                            project_id=pid,
                            flaky_score=score,
                            trend=trend,
                        )
                    )

        # Sort by flaky score descending
        flaky_items.sort(key=lambda x: x.flaky_score.score, reverse=True)
        return flaky_items

    async def get_failure_recurrence(
        self,
        nodeid: str,
        classification: str,
        exclude_failure_id: str | None = None,
        limit: int = 10,
    ) -> list[FailureRecurrenceItem]:
        async with self.session_factory() as session:
            stmt = (
                select(FailureRecordORM)
                .where(
                    FailureRecordORM.test_nodeid == nodeid,
                    FailureRecordORM.classification == classification,
                )
                .order_by(desc(FailureRecordORM.created_at))
                .limit(limit)
            )
            if exclude_failure_id:
                stmt = stmt.where(FailureRecordORM.id != exclude_failure_id)

            result = await session.execute(stmt)
            records = list(result.scalars().all())

            return [
                FailureRecurrenceItem(
                    failure_id=r.id,
                    run_id=r.run_id,
                    nodeid=r.test_nodeid,
                    test_name=r.test_name,
                    classification=r.classification,
                    error_message=r.error_message,
                    created_at=r.created_at,
                )
                for r in records
            ]
