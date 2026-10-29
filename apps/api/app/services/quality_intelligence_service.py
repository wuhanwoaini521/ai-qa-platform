from __future__ import annotations

from typing import Any

from project_model.models import (
    FlakyClassification,
    ImpactAnalysisResult,
    QualityCoverageSummary,
    QualityRiskItem,
    QualityRiskLevel,
    QualityRiskMatrix,
    RequirementCoverageItem,
)

from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.workspace_service import SecurityException, WorkspaceService


class QualityIntelligenceService:
    """Service providing multi-dimensional quality intelligence, coverage analysis, risk scoring, and regression impact selection."""

    def __init__(
        self,
        requirement_repo: RequirementRepository,
        test_case_repo: TestCaseRepository,
        test_design_repo: TestDesignRepository,
        binding_repo: AutomationBindingRepository,
        test_run_repo: TestRunRepository,
        history_repo: RunHistoryRepository | None = None,
        workspace_service: WorkspaceService | None = None,
    ) -> None:
        self.requirement_repo = requirement_repo
        self.test_case_repo = test_case_repo
        self.test_design_repo = test_design_repo
        self.binding_repo = binding_repo
        self.test_run_repo = test_run_repo
        self.history_repo = history_repo or RunHistoryRepository()
        self.workspace_service = workspace_service or WorkspaceService()

    async def calculate_coverage(self, project_id: str) -> QualityCoverageSummary:
        requirements = await self.requirement_repo.list_by_project(project_id)
        test_cases = await self.test_case_repo.list_by_project(project_id)
        recent_runs = await self.test_run_repo.list_runs(project_id=project_id, limit=10)
        bindings = await self.binding_repo.list_by_project(project_id)

        executed_targets = {
            (run.workspace_id, execution.nodeid)
            for run in recent_runs
            for execution in run.executions or []
            if execution.status in {"PASSED", "FAILED", "ERROR"}
        }

        # Map test cases by requirement
        cases_by_req: dict[str, list[Any]] = {}
        for tc in test_cases:
            if tc.requirement_id:
                cases_by_req.setdefault(tc.requirement_id, []).append(tc)

        total_reqs = len(requirements)
        covered_reqs = 0
        req_details: list[RequirementCoverageItem] = []

        for req in requirements:
            designs = await self.test_design_repo.list_by_requirement(req.id)
            associated_cases = cases_by_req.get(req.id, [])
            automated_count = sum(1 for c in associated_cases if c.automation_status == "AUTOMATED")

            design_count = len(designs)
            case_count = len(associated_cases)

            # Coverage score: has design (30%), has cases (40%), has automated cases (30%)
            cov_score = 0.0
            if design_count > 0:
                cov_score += 30.0
            if case_count > 0:
                cov_score += 40.0
            if automated_count > 0:
                cov_score += 30.0

            is_covered = cov_score >= 70.0
            if is_covered:
                covered_reqs += 1

            req_details.append(
                RequirementCoverageItem(
                    requirement_id=req.id,
                    title=req.title,
                    test_design_count=design_count,
                    test_case_count=case_count,
                    automated_case_count=automated_count,
                    status=req.status,
                    coverage_percentage=round(cov_score, 1),
                    has_automation=automated_count > 0,
                )
            )

        total_cases = len(test_cases)
        manual_count = sum(1 for c in test_cases if c.automation_status == "MANUAL")
        draft_count = sum(1 for c in test_cases if c.automation_status == "DRAFT")
        automated_count = sum(1 for c in test_cases if c.automation_status == "AUTOMATED")

        case_ids = {case.id for case in test_cases}
        cases_by_target: dict[tuple[str, str], set[str]] = {}
        for binding in bindings:
            if binding.status in {"ACTIVE", "VALIDATED"} and binding.test_case_id in case_ids:
                cases_by_target.setdefault((binding.workspace_id, binding.nodeid), set()).add(binding.test_case_id)
        executed_cases_count = len(
            {
                next(iter(case_ids_for_target))
                for target, case_ids_for_target in cases_by_target.items()
                if len(case_ids_for_target) == 1 and target in executed_targets
            }
        )

        req_cov_pct = round((covered_reqs / total_reqs * 100.0), 1) if total_reqs > 0 else 0.0
        auto_cov_pct = round((automated_count / total_cases * 100.0), 1) if total_cases > 0 else 0.0
        exec_cov_pct = round((executed_cases_count / total_cases * 100.0), 1) if total_cases > 0 else 0.0

        return QualityCoverageSummary(
            total_requirements=total_reqs,
            covered_requirements=covered_reqs,
            requirement_coverage_pct=req_cov_pct,
            total_test_cases=total_cases,
            manual_cases=manual_count,
            draft_cases=draft_count,
            automated_cases=automated_count,
            automation_coverage_pct=auto_cov_pct,
            executed_cases_recent=executed_cases_count,
            execution_coverage_pct=exec_cov_pct,
            requirement_details=req_details,
        )

    async def calculate_risk_matrix(self, project_id: str) -> QualityRiskMatrix:
        test_cases = await self.test_case_repo.list_by_project(project_id)
        failures = await self.test_run_repo.list_failures(limit=20, project_id=project_id)
        history_items = await self.history_repo.list_flaky_tests(project_id=project_id)
        flaky_items = [
            item for item in history_items if item.flaky_score.classification == FlakyClassification.LIKELY_FLAKY
        ]
        persistent_failures = [
            item for item in history_items if item.flaky_score.classification == FlakyClassification.PERSISTENT_FAILURE
        ]

        risks: list[QualityRiskItem] = []
        unautomated_p0 = 0
        # 1. Unautomated P0 Critical Tests
        for tc in test_cases:
            if tc.priority == "P0" and tc.automation_status != "AUTOMATED":
                unautomated_p0 += 1
                risks.append(
                    QualityRiskItem(
                        id=f"risk_p0_{tc.id}",
                        area=f"Core Feature: {tc.title}",
                        risk_level=QualityRiskLevel.CRITICAL,
                        score=90.0,
                        reasons=[f"P0 Critical test case '{tc.title}' has status {tc.automation_status}"],
                        impacted_nodeids=[],
                        recommended_actions=[
                            f"Generate automated Playwright/Pytest script for case {tc.id} in Automation Studio",
                            "Run manual verification before release approval",
                        ],
                    )
                )

        # 2. Flaky Tests Risk
        for flaky in flaky_items:
            level = QualityRiskLevel.HIGH if flaky.flaky_score.score >= 0.5 else QualityRiskLevel.MEDIUM
            risks.append(
                QualityRiskItem(
                    id=f"risk_flaky_{flaky.nodeid.replace('::', '_')}",
                    area=f"Test Reliability: {flaky.test_name}",
                    risk_level=level,
                    score=round(flaky.flaky_score.score * 100, 1),
                    reasons=[
                        f"Deterministic flaky rate of {round(flaky.flaky_score.score * 100, 1)}%",
                        f"Alternation rate {round(flaky.flaky_score.alternation_rate * 100, 1)}% "
                        f"across {flaky.flaky_score.sample_count} runs",
                    ],
                    impacted_nodeids=[flaky.nodeid],
                    recommended_actions=[
                        "Inspect locator stability and async wait conditions",
                        "Quarantine the test or review a locator repair proposal (applying it stays manual)",
                    ],
                )
            )

        for failure in persistent_failures:
            risks.append(
                QualityRiskItem(
                    id=f"risk_persistent_{failure.nodeid.replace('::', '_')}",
                    area=f"Persistent Failure: {failure.test_name}",
                    risk_level=QualityRiskLevel.HIGH,
                    score=100.0,
                    reasons=[
                        f"The test failed in all {failure.flaky_score.sample_count} observed runs",
                    ],
                    impacted_nodeids=[failure.nodeid],
                    recommended_actions=[
                        "Inspect the latest failure evidence and fix the underlying defect",
                        "Rerun the test after the fix",
                    ],
                )
            )

        # 3. Recurring Failure Signatures
        for f in failures[:5]:
            if f.classification in ("APPLICATION_BUG", "ENVIRONMENT_ISSUE"):
                risks.append(
                    QualityRiskItem(
                        id=f"risk_fail_{f.id}",
                        area=f"Defect: {f.test_name}",
                        risk_level=QualityRiskLevel.HIGH,
                        score=80.0,
                        reasons=[
                            f"Execution failure: {f.error_message[:100]}",
                            f"Classified as {f.classification}",
                        ],
                        impacted_nodeids=[f.test_nodeid],
                        recommended_actions=[
                            "Create Jira Defect ticket",
                            f"Apply fix: {f.suggested_action or 'Investigate error stack trace'}",
                        ],
                    )
                )

        # Compute overall quality score
        penalty = (
            (unautomated_p0 * 15.0)
            + (len(flaky_items) * 8.0)
            + (len(persistent_failures) * 10.0)
            + (len(failures) * 5.0)
        )
        overall_score = max(0.0, min(100.0, round(100.0 - penalty, 1)))

        if unautomated_p0 >= 3:
            overall_level = QualityRiskLevel.CRITICAL
        elif unautomated_p0 > 0 or persistent_failures:
            overall_level = QualityRiskLevel.HIGH
        elif overall_score >= 85.0:
            overall_level = QualityRiskLevel.LOW
        elif overall_score >= 65.0:
            overall_level = QualityRiskLevel.MEDIUM
        elif overall_score >= 40.0:
            overall_level = QualityRiskLevel.HIGH
        else:
            overall_level = QualityRiskLevel.CRITICAL

        return QualityRiskMatrix(
            project_id=project_id,
            overall_quality_score=overall_score,
            overall_risk_level=overall_level,
            risks=risks,
            high_risk_count=sum(1 for r in risks if r.risk_level in (QualityRiskLevel.HIGH, QualityRiskLevel.CRITICAL)),
            unautomated_p0_count=unautomated_p0,
            flaky_test_count=len(flaky_items),
        )

    async def analyze_impact_and_select_regression(
        self,
        project_id: str,
        changed_files: list[str],
        workspace_id: str | None = None,
    ) -> ImpactAnalysisResult:
        files = list(changed_files)

        # Auto-detect from git if workspace_id provided and files empty
        if not files and workspace_id:
            try:
                diff_res = await self.workspace_service.get_diff(workspace_id)
                files = [cf.path for cf in diff_res.changed_files]
            except (SecurityException, FileNotFoundError):
                # Unknown/unsafe workspace: fall back to an empty change set instead of guessing.
                files = []

        test_cases = await self.test_case_repo.list_by_project(project_id)
        requirements = await self.requirement_repo.list_by_project(project_id)
        bindings = await self.binding_repo.list_by_project(project_id)

        impacted_req_ids: set[str] = set()
        impacted_case_ids: set[str] = set()
        recommended_nodeids: set[str] = set()
        rationale: list[str] = []

        # Domain keyword mapping heuristics
        keywords: set[str] = set()
        for f in files:
            parts = f.lower().replace("_", "/").replace("-", "/").split("/")
            for p in parts:
                cleaned = p.replace(".py", "").replace(".ts", "").replace(".tsx", "").replace(".js", "")
                if len(cleaned) > 2 and cleaned not in ("src", "app", "tests", "test", "components", "pages", "index"):
                    keywords.add(cleaned)

        rationale.append(
            f"Analyzed {len(files)} changed files. Extracted domain components: {', '.join(keywords) or 'General'}"
        )

        # Match against bindings
        for b in bindings:
            if any(k in b.file_path.lower() for k in keywords) or any(f in b.file_path for f in files):
                impacted_case_ids.add(b.test_case_id)
                recommended_nodeids.add(b.nodeid or b.file_path)

        # Match against test cases
        for tc in test_cases:
            matches_title = any(k in tc.title.lower() for k in keywords)
            matches_tags = any(any(k in tag.lower() for k in keywords) for tag in (tc.tags or []))
            if matches_title or matches_tags:
                impacted_case_ids.add(tc.id)
                if tc.requirement_id:
                    impacted_req_ids.add(tc.requirement_id)
                # Formulate test nodeid heuristic
                node_heuristic = (
                    f"tests/test_{keywords.pop() if keywords else 'suite'}.py::{tc.title.lower().replace(' ', '_')}"
                )
                recommended_nodeids.add(node_heuristic)

        # Match requirements
        for req in requirements:
            if any(k in req.title.lower() or k in req.description.lower() for k in keywords):
                impacted_req_ids.add(req.id)

        if not recommended_nodeids and test_cases:
            # Fallback to high priority test cases
            for tc in test_cases:
                if tc.priority in ("P0", "P1"):
                    recommended_nodeids.add(f"tests/test_regression.py::{tc.title.lower().replace(' ', '_')}")
            rationale.append("No direct module match found; selected baseline P0/P1 regression test suite.")
        else:
            rationale.append(
                f"Mapped {len(impacted_case_ids)} test cases and {len(impacted_req_ids)} requirements directly to changed code paths."
            )

        return ImpactAnalysisResult(
            changed_files=files,
            impacted_requirements=list(impacted_req_ids),
            impacted_test_cases=list(impacted_case_ids),
            recommended_regression_tests=sorted(list(recommended_nodeids)),
            confidence_score=0.92 if len(files) > 0 else 0.70,
            rationale=rationale,
        )
