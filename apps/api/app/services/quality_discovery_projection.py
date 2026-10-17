from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from app.persistence.models import QualityDiscoveryRunORM, utc_now
from app.repositories.quality_discovery_repo import QualityDiscoveryRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.quality_discovery_models import DiscoveryStatus


class QualityDiscoveryProjectionMixin:
    async def _build_quality_map(self, run_id: str, *, final_status: str | None = None) -> None:
        for attempt in range(5):
            try:
                await self._build_quality_map_once(run_id, final_status=final_status)
                return
            except (StaleDataError, OperationalError) as exc:
                if not self._is_retryable_write_conflict(exc) or attempt == 4:
                    raise
                await asyncio.sleep(0.01 * (attempt + 1))

    async def _build_quality_map_once(self, run_id: str, *, final_status: str | None = None) -> None:
        async with self.session_factory() as session:
            row = await QualityDiscoveryRepository(session).get(run_id)
            if row is None:
                return
            cases = await TestCaseRepository(session).list_by_project(row.project_id)
            runs = await TestRunRepository(session).list_runs(project_id=row.project_id, limit=500)
            config = self._get_config().discovery
            collected_tests = []
            workspace_test_scan_status = "NOT_CONFIGURED"
            if self.workspace_service is not None:
                workspace_test_scan_status = "AVAILABLE"
                try:
                    collected_tests = (await self.workspace_service.collect_tests(row.project_id)).tests
                except Exception:
                    # Keep a degraded but explicit map; missing workspace evidence is unverified, not a failed run.
                    collected_tests = []
                    workspace_test_scan_status = "UNAVAILABLE"
            collected_by_nodeid = {item.nodeid: item for item in collected_tests}
            cases_by_nodeid = {
                case.binding.nodeid: case for case in cases if case.binding is not None and case.binding.nodeid
            }
            result = json.loads(json.dumps(row.result or {}))
            result["workspace_test_scan"] = {
                "status": workspace_test_scan_status,
                "tests_collected": len(collected_tests) if workspace_test_scan_status == "AVAILABLE" else None,
                "message": (
                    "无法读取项目自动化工作区；自动化覆盖结果未验证。"
                    if workspace_test_scan_status == "UNAVAILABLE"
                    else None
                ),
            }
            requirements = result.get("requirements", [])
            features = result.get("features", [])
            coverage = []
            mapping_threshold = config.feature_mapping_confidence
            derived_gap_types = {
                "TEST_MISSING",
                "AUTOMATION_MISSING",
                "AUTOMATION_FAILING",
                "TEST_INCOMPLETE",
                "NOT_VERIFIED",
                "BLOCKED_BY_POLICY",
                "REQUIREMENT_MISSING",
                "IMPLEMENTATION_MISSING",
                "IMPLEMENTATION_PARTIAL",
                "REQUIRED_NOT_FOUND",
                "IMPLEMENTED_PARTIAL",
                "IMPLEMENTED_BROKEN",
                "UNDOCUMENTED_FEATURE",
                "FUNCTION_BROKEN",
                "REQUIREMENT_AMBIGUOUS",
            }
            gaps = [gap for gap in result.get("gaps", []) if gap.get("category") not in derived_gap_types]
            for requirement in requirements:
                matches = [
                    (feature, self._similarity(requirement.get("feature", ""), feature.get("name", "")))
                    for feature in features
                ]
                matches = [
                    (feature, score)
                    for feature, score in matches
                    if score >= 0.34 and feature.get("status") != "INFERRED"
                ]
                for feature, _score in matches:
                    if requirement["id"] not in feature.setdefault("requirement_ids", []):
                        feature["requirement_ids"].append(requirement["id"])
                top_score = max((score for _feature, score in matches), default=0.0)
                check_status, check_results = self._evaluate_requirement_checks(
                    requirement,
                    result.get("states", []),
                    result.get("edges", []),
                    result.get("actions", []),
                )
                check_evidence_ids = {item["evidence_id"] for item in check_results if item.get("evidence_id")}
                requirement["check_status"] = check_status
                requirement["check_results"] = check_results
                requirement["evidence_ids"] = sorted(
                    {evidence for feature, _ in matches for evidence in feature.get("evidence_ids", [])}
                    | check_evidence_ids
                )
                related_action_failed = any(
                    action.get("status") == "FAILED"
                    and action.get("target")
                    and self._similarity(requirement.get("feature", ""), action.get("target", "")) >= 0.34
                    for action in result.get("actions", [])
                )
                if requirement.get("ambiguous"):
                    status = "REQUIREMENT_AMBIGUOUS"
                elif check_status == "FAIL" or related_action_failed:
                    status = "IMPLEMENTED_BROKEN"
                elif check_status == "PASS":
                    status = "PASS"
                elif requirement.get("draft"):
                    status = "NOT_VERIFIED"
                elif not matches:
                    status = (
                        "REQUIRED_NOT_FOUND"
                        if (final_status or row.status) == DiscoveryStatus.COMPLETED.value
                        else "NOT_VERIFIED"
                    )
                elif top_score < mapping_threshold:
                    status = "NOT_VERIFIED"
                elif matches:
                    status = "IMPLEMENTED_PARTIAL"
                else:
                    status = "NOT_VERIFIED"
                requirement["status"] = status
                requirement["mapping_confidence"] = round(top_score, 2)
                requirement["mapping_status"] = "MAPPED" if top_score >= mapping_threshold else "NEEDS_REVIEW"
                if status in {
                    "REQUIRED_NOT_FOUND",
                    "IMPLEMENTED_PARTIAL",
                    "IMPLEMENTED_BROKEN",
                    "REQUIREMENT_AMBIGUOUS",
                    "NOT_VERIFIED",
                }:
                    gap_category = {
                        "REQUIRED_NOT_FOUND": "IMPLEMENTATION_MISSING",
                        "IMPLEMENTED_PARTIAL": "IMPLEMENTATION_PARTIAL",
                        "IMPLEMENTED_BROKEN": "FUNCTION_BROKEN",
                    }.get(status, status)
                    gaps.append(
                        self._gap(
                            gap_category,
                            requirement["id"],
                            requirement["feature"],
                            requirement.get("evidence_ids", []),
                            top_score,
                        )
                    )

            for feature in features:
                if feature.get("status") == "INFERRED":
                    feature["mapping_status"] = "NEEDS_REVIEW"
                    feature["test_case_ids"] = []
                    feature["automation"] = []
                    feature["coverage_status"] = "NOT_VERIFIED"
                    coverage.append(
                        {
                            "feature_id": feature["feature_id"],
                            "feature": feature["name"],
                            "requirement_ids": [],
                            "requirement_status": "NOT_VERIFIED",
                            "product_status": "INFERRED",
                            "test_status": "NOT_VERIFIED",
                            "automation_status": "NOT_VERIFIED",
                            "last_run_status": None,
                            "gap_categories": ["NOT_VERIFIED"],
                            "coverage_status": "NOT_VERIFIED",
                        }
                    )
                    gaps.append(
                        self._gap(
                            "NOT_VERIFIED", feature["feature_id"], feature["name"], [], feature.get("confidence", 0.0)
                        )
                    )
                    continue
                linked_reqs = [req for req in requirements if req["id"] in feature.get("requirement_ids", [])]
                feature_mapping_confidence = max(
                    (self._similarity(req.get("feature", ""), feature.get("name", "")) for req in linked_reqs),
                    default=0.0,
                )
                feature["mapping_confidence"] = round(feature_mapping_confidence, 2)
                if requirements and not linked_reqs:
                    feature["mapping_status"] = "UNDOCUMENTED_FEATURE"
                    gaps.append(
                        self._gap(
                            "UNDOCUMENTED_FEATURE",
                            feature["feature_id"],
                            feature["name"],
                            feature.get("evidence_ids", []),
                            0.0,
                        )
                    )
                elif linked_reqs:
                    feature["mapping_status"] = (
                        "MAPPED" if feature_mapping_confidence >= mapping_threshold else "NEEDS_REVIEW"
                    )
                case_matches = []
                case_review_matches = []
                for case in cases:
                    case_requirements = [
                        req
                        for req in linked_reqs
                        if req.get("source_id") == case.requirement_id and req.get("source_id") != "PASTED"
                    ]
                    case_requirement_confidence = min(
                        (
                            self._similarity(req.get("feature", ""), feature.get("name", ""))
                            for req in case_requirements
                        ),
                        default=0.0,
                    )
                    if case_requirements and case_requirement_confidence >= mapping_threshold:
                        case_matches.append((case, 1.0))
                    else:
                        score = self._similarity(feature["name"], " ".join([case.title, *case.tags]))
                        if case_requirements:
                            score = min(score, case_requirement_confidence)
                        if score >= 0.34:
                            confirmed = score >= mapping_threshold and row.mode != "EXPLORE"
                            (case_matches if confirmed else case_review_matches).append((case, score))
                case_ids = [case.id for case, _ in case_matches]
                feature["test_case_candidates"] = [
                    {
                        "test_case_id": case.id,
                        "title": case.title,
                        "mapping_confidence": round(score, 2),
                        "mapping_status": "NEEDS_REVIEW",
                    }
                    for case, score in case_review_matches
                ]
                feature["test_case_ids"] = case_ids
                automation = []
                for case, score in case_matches:
                    binding = case.binding
                    last_execution = (
                        self._latest_execution(binding.nodeid, runs, binding.workspace_id, row.start_url)
                        if binding and binding.status == "ACTIVE"
                        else None
                    )
                    explored_test = collected_by_nodeid.get(binding.nodeid) if binding else None
                    automation.append(
                        {
                            "test_case_id": case.id,
                            "test_case_title": case.title,
                            "mapping_confidence": round(score, 2),
                            "mapping_status": "MAPPED" if score >= mapping_threshold else "NEEDS_REVIEW",
                            "automation_binding_id": binding.id if binding else None,
                            "nodeid": binding.nodeid if binding else None,
                            "file_path": explored_test.file
                            if explored_test
                            else (binding.file_path if binding else None),
                            "test_name": explored_test.test_name
                            if explored_test
                            else (binding.nodeid.split("::")[-1] if binding else None),
                            "markers": explored_test.markers if explored_test else [],
                            "automation_status": binding.status if binding else "MISSING",
                            "last_run_id": last_execution[0].id if last_execution else None,
                            "last_run_status": last_execution[1].status if last_execution else None,
                            "last_run_at": last_execution[0].created_at.isoformat() if last_execution else None,
                            "failure_summary": self._safe_title(last_execution[1].error_message or "")
                            if last_execution and last_execution[1].error_message
                            else None,
                        }
                    )
                feature["automation"] = automation
                feature["automation_candidates"] = [
                    {
                        "nodeid": item.nodeid,
                        "file_path": item.file,
                        "test_name": item.test_name,
                        "markers": item.markers,
                        "linked_test_case_id": cases_by_nodeid[item.nodeid].id
                        if item.nodeid in cases_by_nodeid
                        else None,
                        "linked_requirement_id": cases_by_nodeid[item.nodeid].requirement_id
                        if item.nodeid in cases_by_nodeid
                        else None,
                        "mapping_confidence": round(
                            self._similarity(feature["name"], item.test_name.replace("_", " ")), 2
                        ),
                    }
                    for item in collected_tests
                    if item.nodeid not in {candidate.get("nodeid") for candidate in automation}
                    and self._similarity(feature["name"], item.test_name.replace("_", " ")) >= 0.34
                ][:20]
                active_automation = [
                    item for item in automation if item["automation_status"] == "ACTIVE" and item["nodeid"]
                ]
                has_binding = bool(active_automation)
                failing = any(item["last_run_status"] in {"FAILED", "ERROR"} for item in active_automation)
                passed = any(item["last_run_status"] == "PASSED" for item in active_automation)
                if case_review_matches:
                    gaps.append(
                        self._gap(
                            "TEST_INCOMPLETE",
                            feature["feature_id"],
                            feature["name"],
                            feature.get("evidence_ids", []),
                            max(score for _, score in case_review_matches),
                        )
                    )
                elif not case_matches:
                    coverage_status = "NOT_COVERED"
                    gaps.append(
                        self._gap(
                            "TEST_MISSING",
                            feature["feature_id"],
                            feature["name"],
                            feature.get("evidence_ids", []),
                            feature.get("mapping_confidence", 0),
                        )
                    )
                if not has_binding and workspace_test_scan_status != "UNAVAILABLE":
                    gaps.append(
                        self._gap(
                            "AUTOMATION_MISSING",
                            feature["feature_id"],
                            feature["name"],
                            feature.get("evidence_ids", []),
                            max((score for _, score in case_matches), default=0.0),
                        )
                    )
                if failing:
                    coverage_status = "AUTOMATION_FAILING"
                    gaps.append(
                        self._gap(
                            "AUTOMATION_FAILING",
                            feature["feature_id"],
                            feature["name"],
                            feature.get("evidence_ids", []),
                            1.0,
                        )
                    )
                elif passed:
                    coverage_status = "VERIFIED"
                elif has_binding:
                    coverage_status = "AUTOMATED"
                elif workspace_test_scan_status == "UNAVAILABLE":
                    coverage_status = "NOT_VERIFIED"
                elif case_matches:
                    coverage_status = (
                        "COVERED" if max(score for _, score in case_matches) >= mapping_threshold else "PARTIAL"
                    )
                elif case_review_matches:
                    coverage_status = "PARTIAL"
                else:
                    coverage_status = "NOT_COVERED"
                feature["coverage_status"] = coverage_status
                feature["automation_scan_status"] = workspace_test_scan_status
                requirement_statuses = [req.get("status", "NOT_VERIFIED") for req in linked_reqs]
                latest_run = self._latest_automation_run(automation)
                gap_categories = [
                    gap["category"]
                    for gap in gaps
                    if gap.get("item_id") == feature["feature_id"]
                    or gap.get("item_id") in feature.get("requirement_ids", [])
                ]
                coverage.append(
                    {
                        "feature_id": feature["feature_id"],
                        "feature": feature["name"],
                        "requirement_ids": feature.get("requirement_ids", []),
                        "requirement_status": "PASS"
                        if requirement_statuses and all(item == "PASS" for item in requirement_statuses)
                        else (
                            requirement_statuses[0]
                            if len(requirement_statuses) == 1
                            else "PARTIAL"
                            if requirement_statuses
                            else "UNDOCUMENTED"
                        ),
                        "product_status": feature.get("status", "OBSERVED"),
                        "test_status": "COVERED"
                        if case_matches
                        else "NEEDS_REVIEW"
                        if case_review_matches
                        else "MISSING",
                        "automation_status": coverage_status
                        if coverage_status in {"AUTOMATED", "AUTOMATION_FAILING", "VERIFIED"}
                        else "NOT_VERIFIED"
                        if coverage_status == "NOT_VERIFIED"
                        else "MISSING",
                        "automation_scan_status": workspace_test_scan_status,
                        "last_run_status": latest_run.get("last_run_status") if latest_run else None,
                        "last_run_id": latest_run.get("last_run_id") if latest_run else None,
                        "gap_categories": gap_categories,
                        "functional_status": feature.get("status", "OBSERVED"),
                        "test_case_ids": case_ids,
                        "test_case_candidates": feature["test_case_candidates"],
                        "automation_candidates": feature["automation_candidates"],
                        "automation": automation,
                        "coverage_status": coverage_status,
                    }
                )
            linked_requirement_ids = {item_id for feature in features for item_id in feature.get("requirement_ids", [])}
            for requirement in requirements:
                if requirement.get("id") in linked_requirement_ids:
                    continue
                coverage.append(
                    {
                        "feature_id": None,
                        "feature": requirement.get("feature", "Requirement"),
                        "requirement_ids": [requirement.get("id")],
                        "requirement_status": requirement.get("status", "NOT_VERIFIED"),
                        "product_status": "NOT_FOUND"
                        if requirement.get("status") == "REQUIRED_NOT_FOUND"
                        else "NOT_VERIFIED",
                        "test_status": "NOT_VERIFIED",
                        "automation_status": "NOT_VERIFIED",
                        "last_run_status": None,
                        "gap_categories": ["IMPLEMENTATION_MISSING"]
                        if requirement.get("status") == "REQUIRED_NOT_FOUND"
                        else ["NOT_VERIFIED"],
                        "functional_status": requirement.get("status", "NOT_VERIFIED"),
                        "test_case_ids": [],
                        "automation": [],
                        "coverage_status": "NOT_VERIFIED",
                    }
                )
            states = result.get("states", [])
            edges = result.get("edges", [])
            for frontier_item in result.get("frontier", []):
                if frontier_item.get("status") == "BLOCKED_BY_POLICY":
                    state = next(
                        (item for item in states if item.get("state_id") == frontier_item.get("state_id")), None
                    )
                    gaps.append(
                        self._gap(
                            "BLOCKED_BY_POLICY",
                            frontier_item.get("candidate_id", "blocked"),
                            str(frontier_item.get("target") or "受安全策略阻止的动作"),
                            [state["evidence_id"]] if state and state.get("evidence_id") else [],
                            1.0,
                        )
                    )
            gaps = list({item["id"]: item for item in gaps}.values())
            result["requirements"] = requirements
            result["features"] = features
            result["gaps"] = gaps
            self._enrich_gap_context(result, requirements=requirements, features=features, states=states)
            workspace_tests = [
                {
                    "nodeid": item.nodeid,
                    "test_name": item.test_name,
                    "file": item.file,
                    "class_name": item.class_name,
                    "markers": item.markers,
                    "line": item.line,
                    "test_case_id": cases_by_nodeid[item.nodeid].id if item.nodeid in cases_by_nodeid else None,
                    "requirement_id": cases_by_nodeid[item.nodeid].requirement_id
                    if item.nodeid in cases_by_nodeid
                    else None,
                }
                for item in collected_tests[:500]
            ]
            result["coverage"] = coverage
            result["workspace_tests"] = workspace_tests
            result["journeys"] = self._build_journeys(states, edges)
            result["quality_map"] = {
                "requirements": requirements,
                "features": features,
                "coverage": coverage,
                "gaps": gaps,
                "workspace_test_scan": result["workspace_test_scan"],
            }
            result["functional_spec"] = self._functional_specification(row, requirements, features, coverage, gaps)
            row.result = result
            row.updated_at = utc_now()
            await session.commit()

    @staticmethod
    def _build_journeys(states: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {item.get("state_id"): item for item in states if item.get("state_id")}
        outgoing: dict[str, list[dict[str, Any]]] = {}
        incoming: set[str] = set()
        for edge in edges:
            source, target = edge.get("from_state_id"), edge.get("to_state_id")
            if source in by_id and target in by_id:
                outgoing.setdefault(source, []).append(edge)
                incoming.add(target)
        roots = [item["state_id"] for item in states if item.get("state_id") not in incoming]
        if not roots and states:
            roots = [states[0].get("state_id")]
        journeys = []

        def step(state_id: str, edge: dict[str, Any] | None = None) -> dict[str, Any]:
            state = by_id[state_id]
            return {
                "state_id": state_id,
                "title": state.get("title") or state.get("page_type") or state.get("url"),
                "url": state.get("url"),
                "page_type": state.get("page_type", "unknown"),
                "action": edge.get("label") if edge else None,
                "evidence_ids": [state["evidence_id"]] if state.get("evidence_id") else [],
            }

        def visit(current: str, path: list[dict[str, Any]], seen: set[str]) -> None:
            if len(journeys) >= 30 or len(path) >= 16:
                return
            branches = [edge for edge in outgoing.get(current, []) if edge.get("to_state_id") not in seen]
            if not branches:
                if path:
                    journeys.append({"journey_id": f"journey-{len(journeys) + 1}", "steps": path})
                return
            for edge in branches:
                target = edge["to_state_id"]
                visit(target, [*path, step(target, edge)], {*seen, target})
                if len(journeys) >= 30:
                    return

        for root in roots:
            if root not in by_id:
                continue
            visit(root, [step(root)], {root})
            if len(journeys) >= 30:
                break
        if not journeys and states:
            journeys.append({"journey_id": "journey-1", "steps": [step(states[0]["state_id"])]})
        return journeys

    @staticmethod
    def _functional_specification(
        row: QualityDiscoveryRunORM,
        requirements: list[dict[str, Any]],
        features: list[dict[str, Any]],
        coverage: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        requirement_by_id = {item.get("id"): item for item in requirements}
        coverage_by_feature = {item.get("feature_id"): item for item in coverage if item.get("feature_id")}
        specs = []
        for feature in features:
            linked = [
                requirement_by_id[item] for item in feature.get("requirement_ids", []) if item in requirement_by_id
            ]
            feature_gap_items = [
                item
                for item in gaps
                if item.get("item_id") == feature.get("feature_id")
                or item.get("item_id") in feature.get("requirement_ids", [])
            ]
            row_coverage = coverage_by_feature.get(feature["feature_id"], {})
            automation = feature.get("automation", [])
            specs.append(
                {
                    "feature_id": feature["feature_id"],
                    "name": feature.get("name"),
                    "description": feature.get("description", ""),
                    "page_type": feature.get("page_type", "unknown"),
                    "trust": feature.get("trust", feature.get("status", "INFERRED")),
                    "observed": feature.get("status") in {"OBSERVED", "VERIFIED"},
                    "executed": bool(feature.get("verified_by_action_id")),
                    "verified": feature.get("status") == "VERIFIED",
                    "requirement_ids": feature.get("requirement_ids", []),
                    "expected_behavior": [
                        item.get("expected_behavior", "") for item in linked if item.get("expected_behavior")
                    ],
                    "requirement_status": row_coverage.get("requirement_status", "UNDOCUMENTED"),
                    "test_case_ids": feature.get("test_case_ids", []),
                    "test_coverage": row_coverage.get("test_status", "MISSING"),
                    "automation": automation,
                    "last_run_status": row_coverage.get("last_run_status"),
                    "gaps": [item["category"] for item in feature_gap_items],
                    "gap_ids": [item["id"] for item in feature_gap_items],
                    "evidence_ids": feature.get("evidence_ids", []),
                }
            )
        return {
            "title": "Functional Specification",
            "generated_at": utc_now().isoformat(),
            "run_id": row.id,
            "source_of_truth": "Quality Discovery run graph, structured requirements, and linked quality records",
            "disclaimer": "Generated from observed evidence. Inferred items are not verified product behavior.",
            "features": specs,
        }

    @classmethod
    def _evaluate_requirement_checks(
        cls,
        requirement: dict[str, Any],
        states: list[dict[str, Any]],
        edges: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        checks = requirement.get("checks") or []
        acceptance_criteria = requirement.get("acceptance_criteria", [])
        repeat_cart_criteria = [
            criterion
            for criterion in acceptance_criteria
            if cls._requirement_allows_repeat_cart_mutation(str(criterion))
        ]
        if not checks and not acceptance_criteria:
            return "NOT_RUN", []

        results = []
        all_passed = True
        expected_behavior = str(requirement.get("expected_behavior") or "")

        def normalize(value: Any) -> str:
            return re.sub(r"\s+", " ", str(value)).strip().casefold()

        normalized_criteria = {normalize(item) for item in acceptance_criteria}
        covered_criteria: set[str] = set()
        for check in checks:
            target = str(check.get("target") or "")
            attribute = check.get("attribute")
            expected = bool(check.get("expected"))
            condition = check.get("when", "always")
            criterion = str(check.get("criterion") or "")
            criterion_to_check = criterion or (expected_behavior if not acceptance_criteria else "")
            criterion_is_declared = (
                normalize(criterion) in normalized_criteria
                if acceptance_criteria
                else bool(expected_behavior) and (not criterion or normalize(criterion) == normalize(expected_behavior))
            )
            if not criterion_is_declared or not cls._check_supports_criterion(check, criterion_to_check):
                if not acceptance_criteria:
                    all_passed = False
                results.append(
                    {
                        "target": target,
                        "attribute": attribute,
                        "status": "NOT_VERIFIED",
                        "reason": "The rule does not directly prove its linked requirement criterion.",
                    }
                )
                continue
            observations = []
            for state in states:
                controls = state.get("controls") or []
                if condition == "after_action" and not any(
                    edge.get("to_state_id") == state.get("state_id")
                    and cls._criterion_action_matches_edge(criterion_to_check, target, edge)
                    for edge in edges or []
                ):
                    continue
                if condition in {"size_unselected", "size_selected"}:
                    size_controls = [
                        control for control in controls if re.search(r"size|尺码", str(control.get("name") or ""), re.I)
                    ]
                    if not size_controls:
                        continue
                    size_selected = any(cls._control_is_selected(control) for control in size_controls)
                    if size_selected != (condition == "size_selected"):
                        continue

                if attribute == "visible":
                    text = str(state.get("main_content") or "")
                    if not text:
                        continue
                    actual = target.casefold() in text.casefold()
                    if actual:
                        observations.append((state, True))
                    continue

                scored = [(cls._similarity(target, str(control.get("name") or "")), control) for control in controls]
                scored = [(score, control) for score, control in scored if score >= 0.45]
                if not scored:
                    continue
                best_score = max(score for score, _control in scored)
                best = [control for score, control in scored if score == best_score]
                observed_values = {
                    cls._control_is_selected(control) if attribute == "selected" else bool(control.get(attribute))
                    for control in best
                }
                if len(observed_values) == 1:
                    observations.append((state, observed_values.pop()))

            if not observations:
                if not acceptance_criteria:
                    all_passed = False
                results.append(
                    {
                        "target": target,
                        "attribute": attribute,
                        "expected": expected,
                        "status": "NOT_VERIFIED",
                    }
                )
                continue

            verified_observations = [(state, actual) for state, actual in observations if state.get("evidence_id")]
            if not verified_observations:
                if not acceptance_criteria:
                    all_passed = False
                results.append(
                    {
                        "target": target,
                        "attribute": attribute,
                        "expected": expected,
                        "status": "NOT_VERIFIED",
                        "reason": "The observation has no persisted evidence reference.",
                    }
                )
                continue

            mismatches = [(state, actual) for state, actual in verified_observations if actual != expected]
            state, actual = mismatches[0] if mismatches else verified_observations[0]
            passed = not mismatches
            results.append(
                {
                    "target": target,
                    "attribute": attribute,
                    "expected": expected,
                    "actual": actual,
                    "state_id": state.get("state_id"),
                    "evidence_id": state.get("evidence_id"),
                    "observations": [
                        {
                            "state_id": observed_state.get("state_id"),
                            "actual": value,
                            "evidence_id": observed_state.get("evidence_id"),
                        }
                        for observed_state, value in observations
                    ],
                    "status": "PASS" if passed else "FAIL",
                }
            )
            if not passed:
                return "FAIL", results
            if acceptance_criteria:
                covered_criteria.add(normalize(criterion))

        for criterion in repeat_cart_criteria:
            result = cls._evaluate_repeat_cart_merge_criterion(criterion, actions or [], states)
            results.append(result)
            if result["status"] == "PASS":
                covered_criteria.add(normalize(criterion))
            elif result["status"] == "FAIL":
                return "FAIL", results
            else:
                all_passed = False

        for criterion in acceptance_criteria:
            normalized = normalize(criterion)
            if normalized in covered_criteria:
                continue
            result = cls._evaluate_evidence_criterion(criterion, states, edges or [], actions or [])
            if result is None:
                continue
            results.append(result)
            if result["status"] == "PASS":
                covered_criteria.add(normalized)
            elif result["status"] == "FAIL":
                return "FAIL", results
            else:
                all_passed = False

        uncovered_criteria = [
            criterion for criterion in acceptance_criteria if normalize(criterion) not in covered_criteria
        ]
        if uncovered_criteria:
            results.append({"status": "NOT_VERIFIED", "uncovered_criteria": uncovered_criteria})
        return ("PASS" if all_passed and not uncovered_criteria else "NOT_VERIFIED"), results

    @classmethod
    def _evaluate_evidence_criterion(
        cls,
        criterion: str,
        states: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        text = criterion.casefold()
        is_empty_search = bool(
            re.search(r"no[- ]match|no results?|empty state|无匹配|无结果|空状态", text)
            and re.search(r"product cards?|商品卡片|商品卡", text)
        )
        is_matching_search = bool(
            not is_empty_search and re.search(r"search|搜索", text) and re.search(r"match|匹配", text)
        )
        is_product_detail = bool(
            re.search(r"product detail|商品详情", text)
            and re.search(r"price|价格", text)
            and re.search(r"add.{0,20}cart|加入购物车", text)
        )
        is_variant_retained = bool(
            re.search(r"color|colour|size|颜色|尺码", text)
            and re.search(r"cart|购物车", text)
            and re.search(r"retain|selected|保留|所选规格", text)
        )
        is_cart_arithmetic = bool(
            re.search(r"cart|购物车", text)
            and re.search(r"quantity|数量", text)
            and re.search(r"price|金额|价格", text)
            and re.search(r"\*|乘|multiply|calculated|符合", text)
        )
        if not any((is_empty_search, is_matching_search, is_product_detail, is_variant_retained, is_cart_arithmetic)):
            return None

        def result(check: str, status: str, state=None, expected=None, actual=None, reason=None):
            item = {
                "criterion": criterion,
                "check": check,
                "status": status,
                "state_id": (state or {}).get("state_id"),
                "evidence_id": (state or {}).get("evidence_id"),
            }
            if expected is not None:
                item["expected"] = expected
            if actual is not None:
                item["actual"] = actual
            if reason:
                item["reason"] = reason
            return item

        def after(action, *, include_later_states: bool = False):
            finished_at = action.get("finished_at")
            if not finished_at:
                return []
            edge_state_ids = {
                edge.get("to_state_id")
                for edge in edges
                if edge.get("candidate_id") == action.get("candidate_id")
                and edge.get("from_state_id") == action.get("from_state_id")
                and edge.get("to_state_id")
            }
            fingerprint = action.get("to_fingerprint")
            related = [
                state
                for state in states
                if state.get("state_id") in edge_state_ids or (fingerprint and state.get("fingerprint") == fingerprint)
            ]
            if include_later_states or not related:
                related_ids = {state.get("state_id") for state in related}
                related.extend(
                    state
                    for state in states
                    if state.get("state_id") not in related_ids
                    and cls._timestamp_after(state.get("observed_at"), finished_at)
                )
            return related

        executed_searches = [
            action
            for action in actions
            if action.get("status") == "EXECUTED"
            and action.get("action_type") == "search"
            and str(action.get("search_value") or "").strip()
        ]
        if is_empty_search or is_matching_search:
            searches = [
                action
                for action in executed_searches
                if (str(action.get("search_value") or "").casefold().startswith("zzqa-no-matching-item"))
                == is_empty_search
            ]
            if is_matching_search:
                searches = [
                    action
                    for action in searches
                    if not str(action.get("search_value") or "").casefold().startswith("zzqa-no-matching-item")
                ]
            if not searches:
                return result(
                    "empty_search_state" if is_empty_search else "case_insensitive_product_search",
                    "NOT_VERIFIED",
                    reason="No matching executed search action has persisted evidence yet.",
                )
            search = searches[-1]
            following_states = after(search)
            following_states.sort(
                key=lambda item: (
                    cls._parse_timestamp(item.get("observed_at")) or datetime.max.replace(tzinfo=timezone.utc)
                )
            )
            state = next((item for item in following_states if item.get("evidence_id")), None)
            if state is None:
                return result(
                    "empty_search_state" if is_empty_search else "case_insensitive_product_search",
                    "NOT_VERIFIED",
                    reason="The search result state has no persisted evidence reference.",
                )
            content = str(state.get("main_content") or "")
            product_names = [
                match.group(1).strip()
                for control in state.get("controls") or []
                if (match := re.match(r"view\s+(.+)", str(control.get("name") or ""), re.I))
            ]
            if is_empty_search:
                has_empty_message = bool(re.search(r"no products found|no results?|未找到商品|没有找到", content, re.I))
                passed = has_empty_message and not product_names
                failed = bool(product_names)
                return result(
                    "empty_search_state",
                    "PASS" if passed else "FAIL" if failed else "NOT_VERIFIED",
                    state,
                    {"empty_state": True, "product_cards": 0},
                    {"empty_state": has_empty_message, "product_cards": len(product_names)},
                )
            query = str(search.get("search_value") or "").strip()
            matched = [name for name in product_names if query.casefold() in name.casefold()]
            case_differs = any(
                name.casefold().find(query.casefold()) >= 0
                and name[name.casefold().find(query.casefold()) : name.casefold().find(query.casefold()) + len(query)]
                != query
                for name in matched
            )
            passed = bool(matched) and len(matched) == len(product_names) and case_differs
            failed = bool(product_names) and not passed
            return result(
                "case_insensitive_product_search",
                "PASS" if passed else "FAIL" if failed else "NOT_VERIFIED",
                state,
                {"all_visible_products_match_query": True, "case_insensitive_match": True},
                {"query": query, "visible_products": product_names, "matching_products": matched},
            )

        if is_product_detail:
            detail_states = [
                state
                for state in states
                if state.get("evidence_id")
                and any(
                    cls._is_cart_mutation_label(str(control.get("name") or ""))
                    for control in state.get("controls") or []
                )
                and re.search(r"\$\s*[0-9,]+(?:\.\d{1,2})?", str(state.get("main_content") or ""))
            ]
            if not detail_states:
                return result("product_detail_purchase_controls", "NOT_VERIFIED")
            state = detail_states[-1]
            content = str(state.get("main_content") or "")
            add_control = next(
                control
                for control in state.get("controls") or []
                if cls._is_cart_mutation_label(str(control.get("name") or ""))
            )
            has_name = bool(
                re.search(r"heading\s+\"[^\"]+\"\s+\[level=1\]", str(state.get("landmarks") or ""), re.I)
            ) or bool(re.search(r"[A-Z][A-Za-z0-9' -]{2,}", content))
            has_price = bool(re.search(r"\$\s*[0-9,]+(?:\.\d{1,2})?", content))
            enabled = bool(add_control.get("enabled", True))
            passed = has_name and has_price and enabled
            return result(
                "product_detail_purchase_controls",
                "PASS" if passed else "FAIL",
                state,
                {"product_name": True, "price": True, "add_to_cart_enabled": True},
                {"product_name": has_name, "price": has_price, "add_to_cart_enabled": enabled},
            )

        cart_adds = [
            action
            for action in actions
            if action.get("status") == "EXECUTED" and cls._is_cart_mutation_label(str(action.get("target") or ""))
        ]
        if is_variant_retained:
            state_by_id = {item.get("state_id"): item for item in states}
            selection_values = {}
            selection_scopes = {}
            for action in actions:
                if action.get("status") != "EXECUTED" or action.get("action_type") != "select":
                    continue
                source = state_by_id.get(action.get("from_state_id"), {})
                target = str(action.get("target") or "")
                if re.search(r"color|colour|颜色", target, re.I):
                    selection_values["color"] = str(action.get("selected_value") or "")
                    selection_scopes["color"] = cls._product_scope_key(source)
                elif re.search(r"size|尺码", target, re.I):
                    selection_values["size"] = str(action.get("selected_value") or "")
                    selection_scopes["size"] = cls._product_scope_key(source)
            selected = [value for value in selection_values.values() if value]
            if len(selected) < 2 or len(set(selection_scopes.values())) != 1 or not cart_adds:
                return result(
                    "selected_variant_retained_in_cart",
                    "NOT_VERIFIED",
                    actual={"selected_values": selection_values},
                )
            latest_add = cart_adds[-1]
            candidates = after(latest_add, include_later_states=True)
            candidates.sort(
                key=lambda item: (
                    cls._parse_timestamp(item.get("observed_at")) or datetime.max.replace(tzinfo=timezone.utc)
                )
            )
            state = next(
                (
                    item
                    for item in candidates
                    if item.get("evidence_id")
                    and re.search(
                        r"shopping cart|your selection|quantity\s*:|数量\s*[:：]?|total\s*:",
                        f"{item.get('title') or ''} {item.get('main_content') or ''}",
                        re.I,
                    )
                    and all(value.casefold() in str(item.get("main_content") or "").casefold() for value in selected)
                ),
                None,
            )
            if state is None:
                return result(
                    "selected_variant_retained_in_cart",
                    "NOT_VERIFIED",
                    actual={"selected_values": selection_values, "cart_after_add": False},
                )
            return result(
                "selected_variant_retained_in_cart",
                "PASS",
                state,
                {"selected_values": selected},
                {"selected_values": selected, "cart_content": str(state.get("main_content") or "")[:240]},
            )

        if not cart_adds:
            return result("cart_amount_matches_price_times_quantity", "NOT_VERIFIED")
        latest_add = cart_adds[-1]
        cart_states = [
            state
            for state in after(latest_add, include_later_states=True)
            if state.get("evidence_id")
            and re.search(
                r"(?:total|总计|合计)\s*[:：]?\s*\$\s*[0-9,]+(?:\.\d{1,2})?", str(state.get("main_content") or ""), re.I
            )
        ]
        if not cart_states:
            return result("cart_amount_matches_price_times_quantity", "NOT_VERIFIED")
        state = cart_states[-1]
        content = str(state.get("main_content") or "")
        quantity_matches = re.findall(r"(?:quantity|数量)\s*[:：]?\s*(\d+)", content, re.I)
        total_match = re.search(r"(?:total|总计|合计)\s*[:：]?\s*\$\s*([0-9,]+(?:\.\d{1,2})?)", content, re.I)
        product_state = next(
            (item for item in states if item.get("state_id") == latest_add.get("from_state_id")),
            {},
        )
        unit_match = re.search(r"\$\s*([0-9,]+(?:\.\d{1,2})?)", str(product_state.get("main_content") or ""))
        if len(quantity_matches) != 1 or not total_match or not unit_match:
            return result("cart_amount_matches_price_times_quantity", "NOT_VERIFIED", state)
        quantity = int(quantity_matches[0])
        unit_price = Decimal(unit_match.group(1).replace(",", ""))
        total = Decimal(total_match.group(1).replace(",", ""))
        expected_total = unit_price * quantity
        passed = total == expected_total
        return result(
            "cart_amount_matches_price_times_quantity",
            "PASS" if passed else "FAIL",
            state,
            {"unit_price_times_quantity": str(expected_total)},
            {"unit_price": str(unit_price), "quantity": quantity, "total": str(total)},
        )

    @classmethod
    def _all_acceptance_criteria_passed(
        cls,
        requirements: list[dict[str, Any]],
        states: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> bool:
        declared = [item for item in requirements if item.get("acceptance_criteria")]
        return bool(declared) and all(
            not item.get("ambiguous") and cls._evaluate_requirement_checks(item, states, edges, actions)[0] == "PASS"
            for item in declared
        )

    @classmethod
    def _evaluate_repeat_cart_merge_criterion(
        cls,
        criterion: str,
        actions: list[dict[str, Any]],
        states: list[dict[str, Any]],
    ) -> dict[str, Any]:
        additions = [
            action
            for action in actions
            if action.get("status") == "EXECUTED"
            and cls._is_cart_mutation_label(str(action.get("target") or ""))
            and action.get("cart_variant_key")
        ]
        by_variant: dict[str, list[dict[str, Any]]] = {}
        for action in additions:
            by_variant.setdefault(str(action["cart_variant_key"]), []).append(action)
        repeated_adds = max(by_variant.values(), key=len, default=[])
        if len(repeated_adds) < 2:
            return {
                "criterion": criterion,
                "check": "same_variant_quantity_merge",
                "expected": {"same_variant_adds": 2, "quantity": 2},
                "actual": {"same_variant_adds": len(repeated_adds)},
                "status": "NOT_VERIFIED",
            }

        latest_add = max(
            repeated_adds,
            key=lambda item: cls._parse_timestamp(item.get("finished_at")) or datetime.min.replace(tzinfo=timezone.utc),
        )
        cart_states = [
            state
            for state in states
            if (
                str(state.get("page_type") or "").casefold() in {"cart", "shopping_cart", "cart_populated"}
                or re.search(
                    r"shopping cart|购物车",
                    f"{state.get('title') or ''} {state.get('main_content') or ''}",
                    re.I,
                )
            )
            and state.get("observed_at")
            and latest_add.get("finished_at")
            and cls._timestamp_after(state["observed_at"], latest_add["finished_at"])
        ]
        if not cart_states:
            return {
                "criterion": criterion,
                "check": "same_variant_quantity_merge",
                "expected": {"same_variant_adds": 2, "quantity": 2},
                "actual": {"same_variant_adds": len(repeated_adds), "cart_after_last_add": False},
                "status": "NOT_VERIFIED",
            }

        cart_state = max(
            cart_states,
            key=lambda item: cls._parse_timestamp(item.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc),
        )
        if not cart_state.get("evidence_id"):
            return {
                "criterion": criterion,
                "check": "same_variant_quantity_merge",
                "expected": {"same_variant_adds": 2, "quantity": 2},
                "actual": {"same_variant_adds": len(repeated_adds), "cart_evidence": False},
                "state_id": cart_state.get("state_id"),
                "status": "NOT_VERIFIED",
            }
        content = str(cart_state.get("main_content") or "")
        quantity_match = re.search(r"(?:quantity|数量)\s*[:：]?\s*(\d+)", content, re.I)
        total_match = re.search(r"(?:total|总计|合计)\s*[:：]?\s*\$\s*([0-9,]+(?:\.\d{1,2})?)", content, re.I)
        state_by_id = {state.get("state_id"): state for state in states}
        product_state = state_by_id.get(repeated_adds[0].get("from_state_id"), {})
        unit_match = re.search(r"\$\s*([0-9,]+(?:\.\d{1,2})?)", str(product_state.get("main_content") or ""))
        if not quantity_match or not total_match or not unit_match:
            return {
                "criterion": criterion,
                "check": "same_variant_quantity_merge",
                "expected": {"same_variant_adds": 2, "quantity": 2},
                "actual": {"same_variant_adds": len(repeated_adds)},
                "state_id": cart_state.get("state_id"),
                "evidence_id": cart_state.get("evidence_id"),
                "status": "NOT_VERIFIED",
            }

        quantity = int(quantity_match.group(1))
        unit_price = Decimal(unit_match.group(1).replace(",", ""))
        total = Decimal(total_match.group(1).replace(",", ""))
        expected_total = unit_price * 2
        passed = quantity == 2 and total == expected_total
        return {
            "criterion": criterion,
            "check": "same_variant_quantity_merge",
            "expected": {"same_variant_adds": 2, "quantity": 2, "total": str(expected_total)},
            "actual": {
                "same_variant_adds": len(repeated_adds),
                "quantity": quantity,
                "unit_price": str(unit_price),
                "total": str(total),
            },
            "state_id": cart_state.get("state_id"),
            "evidence_id": cart_state.get("evidence_id"),
            "status": "PASS" if passed else "FAIL",
        }

    @classmethod
    def _timestamp_after(cls, left: Any, right: Any) -> bool:
        left_value = cls._parse_timestamp(left)
        right_value = cls._parse_timestamp(right)
        return left_value is not None and right_value is not None and left_value >= right_value

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _check_supports_criterion(cls, check: dict[str, Any], criterion: str) -> bool:
        target = str(check.get("target") or "")
        attribute = check.get("attribute")
        expected = bool(check.get("expected"))
        condition = check.get("when", "always")
        text = str(criterion or "").casefold()
        if not target or cls._similarity(target, text) < 0.45:
            return False
        if attribute == "visible" and not cls._criterion_quotes_target(target, criterion):
            return False
        if not cls._criterion_only_asserts_target_predicate(target, text, attribute):
            return False
        if cls._criterion_has_unverifiable_relation(text):
            return False

        if attribute == "visible":
            directly_visible = re.search(
                r"\b(displayed|visible|shown|appears?|display)\b|显示|展示|可见|出现|呈现", text
            )
            if not directly_visible or not expected:
                return False
            stop_words = {
                "a",
                "an",
                "the",
                "for",
                "when",
                "after",
                "with",
                "is",
                "are",
                "was",
                "were",
                "to",
                "by",
                "and",
                "or",
                "of",
                "in",
                "on",
                "at",
                "from",
            }
            target_terms = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", target.casefold())
            specific_terms = [term for term in target_terms if term not in stop_words]
            if (
                len(specific_terms) < 3
                and sum(len(term) for term in specific_terms if re.search(r"[\u4e00-\u9fff]", term)) < 6
            ):
                return False
            outcome = re.search(
                r"\b(after|once|when|submitted|returns?|updated|loaded)\b|之后|后|提交|返回|更新|加载", text
            )
            if outcome and condition != "after_action":
                return False
        elif attribute == "enabled":
            affirmative = re.search(r"\b(enabled|active|available|clickable|usable)\b|可用|启用|可点击|可操作", text)
            negative = re.search(
                r"\b(disabled|unavailable|not enabled|not clickable)\b|不可用|禁用|不可点击|无法点击", text
            )
            if expected and (not affirmative or negative) or not expected and not negative:
                return False
        elif attribute == "selected":
            affirmative = re.search(r"\b(selected|checked|chosen)\b|选中|已选|勾选", text)
            negative = re.search(
                r"\b(unselected|unchecked|not selected|not checked|not chosen)\b|未选|未选择|未勾选", text
            )
            if expected and (not affirmative or negative) or not expected and not negative:
                return False
        else:
            return False

        if condition == "size_unselected":
            return bool(
                re.search(r"size|尺码", text)
                and re.search(r"unselected|not selected|no size|until.{0,40}selected|未选|未选择", text)
            )
        if condition == "size_selected":
            return bool(
                re.search(r"size|尺码", text)
                and re.search(r"selected|chosen|已选|选中", text)
                and not re.search(r"unselected|not selected|未选", text)
            )
        if condition == "after_action":
            return attribute == "visible" and bool(
                re.search(r"\b(after|once|when|submit(?:ted|ting)?|loaded)\b|之后|后|提交|查询|搜索|加载", text)
            )
        return condition == "always"

    @staticmethod
    def _criterion_quotes_target(target: str, criterion: str) -> bool:
        text = str(criterion or "").casefold()
        literal = str(target or "").casefold()
        quote_pairs = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』"), ("`", "`"))
        return any(f"{opening}{literal}{closing}" in text for opening, closing in quote_pairs)

    @staticmethod
    def _criterion_only_asserts_target_predicate(target: str, criterion: str, attribute: str) -> bool:
        target_text = target.casefold()
        target_index = criterion.find(target_text)
        if target_index < 0:
            return False
        remainder = f"{criterion[:target_index]} {criterion[target_index + len(target_text) :]}"
        tokens = re.findall(r"[a-z]+(?:'[a-z]+)?|[\u4e00-\u9fff]+|\d+", remainder)
        common = {
            "a",
            "an",
            "the",
            "is",
            "are",
            "was",
            "were",
            "be",
            "being",
            "been",
            "to",
            "in",
            "on",
            "at",
            "by",
            "from",
            "when",
            "after",
            "once",
            "if",
            "until",
            "without",
            "no",
            "not",
            "should",
            "must",
            "can",
            "could",
            "only",
        }
        allowed = {
            "visible": common
            | {
                "displayed",
                "visible",
                "shown",
                "appears",
                "appear",
                "present",
                "returned",
                "returns",
                "result",
                "results",
                "search",
                "query",
                "submit",
                "submitted",
                "submitting",
                "loaded",
                "load",
                "page",
                "for",
                "with",
            },
            "enabled": common
            | {
                "button",
                "enabled",
                "active",
                "available",
                "clickable",
                "usable",
                "disabled",
                "unavailable",
                "size",
                "selected",
            },
            "selected": common
            | {
                "selected",
                "checked",
                "chosen",
                "unselected",
                "unchecked",
                "size",
            },
        }.get(attribute, set())
        english_tokens = [token for token in tokens if not re.search(r"[\u4e00-\u9fff]", token)]
        if not all(token in allowed for token in english_tokens):
            return False
        predicates = {
            "visible": {"displayed", "visible", "shown", "appears", "appear", "display"},
            "enabled": {"enabled", "active", "available", "clickable", "usable", "disabled", "unavailable"},
            "selected": {"selected", "checked", "chosen", "unselected", "unchecked"},
        }.get(attribute, set())
        cjk_tokens = [token for token in tokens if re.search(r"[\u4e00-\u9fff]", token)]
        cjk_remainder = "".join(cjk_tokens)
        cjk_predicates = {
            "visible": ("显示", "展示", "可见", "出现", "呈现"),
            "enabled": ("启用", "可用", "不可用", "禁用", "可点击", "不可点击"),
            "selected": ("选中", "未选中", "选择", "勾选", "未勾选"),
        }.get(attribute, ())
        if not predicates.intersection(english_tokens) and not any(item in cjk_remainder for item in cjk_predicates):
            return False
        if not cjk_tokens:
            return True
        allowed_cjk = {
            "visible": {
                "显示",
                "会显示",
                "将显示",
                "出现",
                "会出现",
                "呈现",
                "展示",
                "可见",
                "返回",
                "显示在页面上",
                "在页面上显示",
                "查询后显示",
                "搜索后显示",
                "提交后显示",
                "查询后出现",
                "搜索后出现",
            },
            "enabled": {
                "启用",
                "已启用",
                "可用",
                "不可用",
                "禁用",
                "不可点击",
                "可点击",
                "选中",
                "未选中",
                "尺码",
                "尺寸",
            },
            "selected": {"选中", "已选中", "未选中", "未选择", "勾选", "已勾选", "未勾选", "尺码", "尺寸"},
        }.get(attribute, set())
        return cjk_remainder in allowed_cjk

    @staticmethod
    def _criterion_has_unverifiable_relation(text: str) -> bool:
        comparative_or_state_change = re.search(
            r"\b(increas(?:e|es|ed|ing)|decreas(?:e|es|ed|ing)|chang(?:e|es|ed|ing)|"
            r"updat(?:e|es|ed|ing)|grow(?:s|n|ing)?|shrink(?:s|ing)?|more|fewer|less|"
            r"higher|lower|greater|smaller|larger|increment(?:s|ed|ing)?|decrement(?:s|ed|ing)?|"
            r"twice|double(?:s|d)?|half|halves|halved|previous|prior|before|compared|comparison|"
            r"same|equal|difference|versus|vs\.?|then|because|therefore|caus(?:e|es|ed|ing)|"
            r"accurate|accuracy|correct(?:ly)?|incorrect|valid|invalid|complete|completed|successful|successfully|"
            r"proper(?:ly)?|expected|intended|reliable|trust(?:worthy|ed|ing)?|credible|relevant|sufficient|"
            r"appropriate|meaningful|useful|effective|efficient|secure|safe|robust|resilient|optimized|"
            r"consistent|stable|supported|compliant|intuitive|accessible|healthy|works?|working|"
            r"exactly|minimum|maximum|min|max|threshold|limit|at least|at most|no more than|no less than|"
            r"no fewer than|fewer than|less than|more than|exceed(?:s|ed|ing)?|above|below|"
            r"\d+(?:\.\d+)?\s*(?:%|x|times?)?)\b"
            r"|增加|减少|变化|更新|增长|下降|更多|更少|变大|变小|提高|降低|翻倍|倍增|一半|之前|此前|原来|相比|比较|相同|一样|等于|差异|然后|导致|因此|至少|至多|恰好|正好|最少|最多|最低|最高|超过|不低于|不超过|少于|高于|低于|阈值|上限|下限|准确|正确|有效|无效|完整|成功|符合预期|正常工作|可信|值得信赖|可信赖|相关|充足|适当|有意义|有用|高效|安全|稳健|可靠|一致|稳定|合规|直观|可访问|易用",
            text,
        )
        compound_claim = re.search(
            r"\b(?:and|or|but|while|whereas|which|that)\b|以及|并且|但是|同时|而且",
            text,
        )
        return bool(comparative_or_state_change or compound_claim)

    @classmethod
    def _criterion_action_matches_edge(cls, criterion: str, target: str, edge: dict[str, Any]) -> bool:
        text = str(criterion or "").casefold()
        action = str(edge.get("action") or "").casefold()
        label = str(edge.get("label") or "")
        if re.search(r"search|query|submit|搜索|查询|提交", text):
            return action == "search"
        if re.search(r"filter|筛选", text):
            return action in {"filter", "select"}
        if re.search(r"sort|排序", text):
            return action in {"select", "filter"}
        if re.search(r"select|choose|selected|chosen|选择|选中", text):
            return action == "select"
        if re.search(r"cart|bag|add(?:ed|ing)? to|加入购物车|添加到购物车", text):
            return action == "click" and cls._similarity(target, label) >= 0.45
        if re.search(r"open(?:ed|ing)?|navigate|visit|打开|进入|导航", text):
            return action in {"click", "navigate"} and cls._similarity(target, label) >= 0.45
        return False

    @staticmethod
    def _control_is_selected(control: dict[str, Any]) -> bool:
        if control.get("selected") or control.get("checked"):
            return True
        if control.get("tag") != "select":
            return False
        value = str(control.get("value") or "").strip()
        return bool(value and not re.search(r"^(choose|select|pick|please select|--|none|尺码|请选择)", value, re.I))

    @staticmethod
    def _url_origin(url: str) -> tuple[str, str, int] | None:
        try:
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                return None
            port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
            return parts.scheme, parts.hostname, port
        except ValueError:
            return None

    @classmethod
    def _latest_execution(
        cls, nodeid: str | None, runs: list[Any], workspace_id: str, target_url: str
    ) -> tuple[Any, Any] | None:
        if not nodeid:
            return None
        origin = cls._url_origin(target_url)
        if origin is None:
            return None
        matching_runs = []
        for run in runs:
            if run.workspace_id != workspace_id:
                continue
            matching_execution_ids = {
                browser.case_execution_id
                for browser in run.browser_sessions
                if browser.nodeid == nodeid and cls._url_origin(browser.current_url) == origin
            }
            matching = [
                execution
                for execution in run.executions
                if execution.nodeid == nodeid and execution.id in matching_execution_ids
            ]
            for execution in matching:
                timestamp = execution.started_at or execution.finished_at or run.created_at
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                run_created_at = run.created_at
                if run_created_at.tzinfo is None:
                    run_created_at = run_created_at.replace(tzinfo=timezone.utc)
                matching_runs.append(
                    (
                        timestamp.astimezone(timezone.utc),
                        run_created_at.astimezone(timezone.utc),
                        str(getattr(run, "id", "")),
                        str(getattr(execution, "id", "")),
                        run,
                        execution,
                    )
                )
        if not matching_runs:
            return None
        _, _, _, _, run, execution = max(matching_runs, key=lambda item: item[:4])
        return run, execution

    @classmethod
    def _latest_execution_status(
        cls, nodeid: str | None, runs: list[Any], workspace_id: str, target_url: str
    ) -> str | None:
        latest = cls._latest_execution(nodeid, runs, workspace_id, target_url)
        return latest[1].status if latest else None

    @staticmethod
    def _latest_automation_run(automation: list[dict[str, Any]]) -> dict[str, Any] | None:
        def created_at(item: dict[str, Any]) -> datetime:
            value = item.get("last_run_at")
            if isinstance(value, datetime):
                parsed = value
            elif value:
                try:
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except ValueError:
                    return datetime.min.replace(tzinfo=timezone.utc)
            else:
                return datetime.min.replace(tzinfo=timezone.utc)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)

        return max(automation, key=created_at, default=None)

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        def tokenize(value: str) -> set[str]:
            return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", (value or "").casefold()))

        a, b = tokenize(left), tokenize(right)
        if not a or not b:
            return 1.0 if (left or "").strip().casefold() == (right or "").strip().casefold() else 0.0
        if (left or "").strip().casefold() in (right or "").strip().casefold() or (right or "").strip().casefold() in (
            left or ""
        ).strip().casefold():
            return 0.9
        return len(a & b) / len(a | b)

    @staticmethod
    def _enrich_gap_context(
        result: dict[str, Any],
        *,
        requirements: list[dict[str, Any]] | None = None,
        features: list[dict[str, Any]] | None = None,
        states: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        requirements = requirements if requirements is not None else result.get("requirements") or []
        features = features if features is not None else result.get("features") or []
        states = states if states is not None else result.get("states") or []
        requirements_by_id = {item.get("id"): item for item in requirements if item.get("id")}
        features_by_id = {item.get("feature_id"): item for item in features if item.get("feature_id")}
        states_by_id = {item.get("state_id"): item for item in states if item.get("state_id")}

        for gap in result.get("gaps", []):
            direct_requirement = requirements_by_id.get(gap.get("item_id"))
            feature = features_by_id.get(gap.get("item_id"))
            requirement_ids = (feature.get("requirement_ids") or []) if feature else []
            linked_requirements = [requirements_by_id[item] for item in requirement_ids if item in requirements_by_id]
            if direct_requirement:
                linked_requirements = [direct_requirement]
            labels = list(dict.fromkeys(str(item.get("feature") or "").strip() for item in linked_requirements))
            gap["requirement"] = "; ".join(item for item in labels if item) or None
            expected_items = []
            for item in linked_requirements:
                criteria = item.get("acceptance_criteria") or [item.get("expected_behavior", "")]
                if isinstance(criteria, str):
                    criteria = [criteria]
                expected_items.extend(str(criterion).strip() for criterion in criteria if str(criterion).strip())
            gap["expected"] = list(dict.fromkeys(expected_items))[:8]

            observations: list[str] = []
            if direct_requirement:
                for check in (direct_requirement.get("check_results") or [])[:5]:
                    target = str(check.get("target") or "").strip()
                    actual = check.get("actual")
                    status = str(check.get("status") or "NOT_VERIFIED")
                    if actual is not None:
                        observations.append(
                            f"{target}: observed {actual} ({status})" if target else f"Observed {actual} ({status})"
                        )
                    elif target:
                        observations.append(f"{target}: {status}")
                if not observations and direct_requirement.get("check_status"):
                    observations.append(f"Requirement checks: {direct_requirement['check_status']}")
            if feature:
                observed_states = [
                    states_by_id[item] for item in (feature.get("state_ids") or []) if item in states_by_id
                ]
                page_names = list(
                    dict.fromkeys(
                        str(state.get("title") or state.get("page_type") or "").strip()
                        for state in observed_states
                        if str(state.get("title") or state.get("page_type") or "").strip()
                    )
                )[:3]
                description = str(feature.get("description") or "").strip()
                observations.append(
                    f"Feature {feature.get('name', 'unknown')} is {feature.get('status', 'OBSERVED')}"
                    + (f" on {', '.join(page_names)}" if page_names else "")
                    + (f": {description[:240]}" if description else "")
                )
                if gap.get("category") == "AUTOMATION_MISSING":
                    observations.append(
                        f"Linked test cases: {len(feature.get('test_case_ids') or [])}; no active automation is mapped."
                    )
                elif gap.get("category") == "AUTOMATION_FAILING":
                    failing = [
                        item
                        for item in (feature.get("automation") or [])
                        if item.get("last_run_status") in {"FAILED", "ERROR"}
                    ]
                    if failing:
                        observations.append(
                            "Latest automation result: "
                            + "; ".join(
                                f"{item.get('test_case_title', 'test')}: {item.get('last_run_status')}"
                                for item in failing[:3]
                            )
                        )
            if not feature and not direct_requirement and gap.get("category") == "BLOCKED_BY_POLICY":
                frontier_item = next(
                    (item for item in result.get("frontier", []) if item.get("candidate_id") == gap.get("item_id")),
                    None,
                )
                if frontier_item:
                    observations.append(str(frontier_item.get("reason") or "Action was blocked by the safety policy."))
            gap["observed"] = "; ".join(observations)[:800] or None
        return result

    @staticmethod
    def _gap(category: str, item_id: str, title: str, evidence_ids: list[str], confidence: float) -> dict[str, Any]:
        risk = (
            "HIGH"
            if category in {"IMPLEMENTED_BROKEN", "REQUIRED_NOT_FOUND", "FUNCTION_BROKEN", "IMPLEMENTATION_MISSING"}
            else "MEDIUM"
        )
        return {
            "id": f"gap-{category.lower()}-{hashlib.sha256(item_id.encode()).hexdigest()[:10]}",
            "category": category,
            "item_id": item_id,
            "title": title,
            "risk": risk,
            "confidence": round(confidence, 2),
            "evidence_ids": evidence_ids,
            "suggested_action": {
                "TEST_MISSING": "Generate Tests",
                "AUTOMATION_MISSING": "Generate Automation",
                "AUTOMATION_FAILING": "Open Failure",
                "TEST_INCOMPLETE": "Review Test Mapping",
                "NOT_VERIFIED": "Review Evidence",
                "BLOCKED_BY_POLICY": "Review Safety Policy",
                "UNDOCUMENTED_FEATURE": "Create Requirement Draft",
                "REQUIRED_NOT_FOUND": "Review Evidence",
                "IMPLEMENTED_BROKEN": "Open Failure",
                "FUNCTION_BROKEN": "Open Failure",
                "IMPLEMENTATION_MISSING": "Review Evidence",
                "IMPLEMENTATION_PARTIAL": "Review Evidence",
                "REQUIREMENT_AMBIGUOUS": "Clarify Requirement",
            }.get(category, "Review Evidence"),
        }
