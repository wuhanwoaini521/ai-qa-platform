"""Rebuild project knowledge and coverage from existing QA entities and actual executions."""

from __future__ import annotations

from collections import Counter

from project_model.lifecycle import CoverageMetric, KnowledgeEdge, KnowledgeNode, ProjectKnowledge, RequirementDocument
from qa_core.failure.redactor import SensitiveRedactor
from sqlalchemy import select

from app.persistence.models import (
    AutomationBindingORM,
    ExternalArtifactReferenceORM,
    FailureAnalysisORM,
    FailureRecordORM,
    ProjectORM,
    RequirementORM,
    TestCaseORM,
    TestDesignORM,
    TestExecutionORM,
    TestRunORM,
)


class ProjectKnowledgeService:
    def __init__(self, session):
        self.session = session

    async def build(
        self, project_id: str, *, focus: str | None = None, hops: int = 2, requirement_id: str | None = None
    ) -> ProjectKnowledge:
        project = await self.session.get(ProjectORM, project_id)
        if not project:
            raise ValueError("Project does not exist")
        requirements = list(
            (
                await self.session.scalars(
                    select(RequirementORM).where(RequirementORM.project_id == project_id).limit(501)
                )
            ).all()
        )
        cases = list(
            (
                await self.session.scalars(select(TestCaseORM).where(TestCaseORM.project_id == project_id).limit(1001))
            ).all()
        )
        complete = len(requirements) <= 500 and len(cases) <= 1000
        requirements, cases = requirements[:500], cases[:1000]
        if requirement_id:
            if requirement_id not in {item.id for item in requirements}:
                raise ValueError("Requirement does not belong to this project")
            requirements = [item for item in requirements if item.id == requirement_id]
            cases = [item for item in cases if item.requirement_id == requirement_id]
        requirement_ids = {item.id for item in requirements}
        case_ids = {item.id for item in cases}
        designs = list(
            (
                await self.session.scalars(
                    select(TestDesignORM).where(TestDesignORM.requirement_id.in_(requirement_ids)).limit(1001)
                )
            ).all()
        )
        bindings = list(
            (
                await self.session.scalars(
                    select(AutomationBindingORM).where(AutomationBindingORM.test_case_id.in_(case_ids))
                )
            ).all()
        )
        executions = list(
            (
                await self.session.execute(
                    select(TestExecutionORM, TestRunORM)
                    .join(TestRunORM, TestExecutionORM.run_id == TestRunORM.id)
                    .where(TestRunORM.project_id == project_id)
                    .order_by(TestRunORM.created_at.desc(), TestExecutionORM.id)
                    .limit(2001)
                )
            ).all()
        )
        complete = complete and len(designs) <= 1000 and len(executions) <= 2000
        designs, executions = designs[:1000], executions[:2000]
        binding_by_case = {item.test_case_id: item for item in bindings}
        bindings_by_target = {}
        for binding in bindings:
            bindings_by_target.setdefault((binding.nodeid, binding.workspace_id), []).append(binding)
        latest_execution = {}
        for execution, run in executions:
            if execution.status not in {"PASSED", "FAILED", "ERROR"}:
                continue
            for binding in bindings_by_target.get((execution.nodeid, run.workspace_id), []):
                latest_execution.setdefault(binding.test_case_id, (execution, run))

        nodes: dict[str, KnowledgeNode] = {}
        edges: set[tuple[str, str, str]] = set()

        def node(id, kind, label, summary="", href="", status="", metadata=None):
            nodes[id] = KnowledgeNode(
                id=id,
                kind=kind,
                label=label,
                summary=SensitiveRedactor.redact_text(summary)[:2000],
                href=href,
                status=status,
                metadata=SensitiveRedactor.redact_value(metadata or {}),
            )

        def edge(source, target, relation):
            edges.add((source, target, relation))

        root = f"/projects/{project_id}"
        node(project_id, "project", project.name, project.description, root)
        targets: dict[str, list[tuple[str, str]]] = {
            kind: [] for kind in ("criteria", "rules", "risks", "flow", "negative")
        }
        links: dict[str, set[str]] = {}
        for requirement in requirements:
            document = (
                RequirementDocument.model_validate(requirement.qa_model)
                if requirement.qa_model
                else RequirementDocument()
            )
            href = f"{root}/requirements/{requirement.id}"
            node(
                requirement.id,
                "requirement",
                document.display_id or f"REQ-{requirement.id[-6:]}",
                requirement.title,
                href,
                requirement.status,
            )
            edge(project_id, requirement.id, "contains")
            groups = [("criteria", document.criteria), ("rules", document.rules)]
            if document.analysis:
                groups += [
                    ("risks", document.analysis.risks),
                    ("flow", document.analysis.business_flow),
                    ("scenarios", document.analysis.scenarios),
                ]
            for kind, items in groups:
                for item in items:
                    key = f"{requirement.id}:{item.id}"
                    title = getattr(item, "title", None) or getattr(item, "description", "")
                    node(
                        key,
                        kind,
                        item.id,
                        title,
                        href + f"?node={item.id}",
                        getattr(item, "severity", ""),
                        {
                            "requirement_id": requirement.id,
                            "entity_id": item.id,
                            "document": item.model_dump(mode="json"),
                        },
                    )
                    edge(requirement.id, key, "contains")
                    if kind in targets:
                        targets[kind].append((key, title))
                    if kind == "criteria" and item.negative_required:
                        targets["negative"].append((key, title))
                    for criterion in getattr(item, "criterion_ids", []):
                        edge(key, f"{requirement.id}:{criterion}", "references")
                    for following in getattr(item, "next_ids", []):
                        edge(key, f"{requirement.id}:{following}", "next")
                    coverage = getattr(item, "coverage", None)
                    if coverage:
                        for refs in coverage.model_dump().values():
                            for ref in refs:
                                edge(key, f"{requirement.id}:{ref}", "covers")
        for design in designs:
            model = design.scenario_model or {}
            node(
                design.id,
                "design",
                model.get("id") or f"SCN-{design.id[-6:]}",
                design.title,
                f"{root}/requirements/{design.requirement_id}?tab=design&design={design.id}",
                design.status,
                {"requirement_id": design.requirement_id, "scenario": model},
            )
            edge(design.requirement_id, design.id, "designed_as")
            if model.get("id"):
                edge(f"{design.requirement_id}:{model['id']}", design.id, "adopted_as")
        for case in cases:
            model = case.test_model or {}
            href = f"{root}/test-cases/{case.id}"
            binding = binding_by_case.get(case.id)
            actual = latest_execution.get(case.id)
            node(
                case.id,
                "case",
                model.get("display_id") or f"TC-{case.id[-6:]}",
                case.title,
                href,
                actual[0].status if actual else case.automation_status,
                {
                    "requirement_id": case.requirement_id,
                    "priority": case.priority,
                    "title": case.title,
                    "test_model": model,
                    "binding_id": binding.id if binding else None,
                },
            )
            if case.requirement_id:
                edge(case.requirement_id, case.id, "covered_by")
            if case.test_design_id:
                edge(case.test_design_id, case.id, "implemented_by")
            for refs in model.get("coverage", {}).values():
                for ref in refs:
                    key = f"{case.requirement_id}:{ref}"
                    if key in nodes:
                        links.setdefault(key, set()).add(case.id)
                        edge(key, case.id, "covered_by")
            if binding:
                node(
                    binding.id,
                    "automation",
                    binding.nodeid,
                    binding.file_path,
                    f"{root}/studio/file/{binding.file_path}?caseId={case.id}&target={binding.nodeid}",
                    binding.status,
                    {"nodeid": binding.nodeid, "case_id": case.id, "file_path": binding.file_path},
                )
                edge(case.id, binding.id, "automated_by")

        run_ids = set()
        for execution, run in executions:
            matching = bindings_by_target.get((execution.nodeid, run.workspace_id), [])
            if not matching:
                continue
            run_ids.add(run.id)
            node(
                run.id, "run", f"RUN-{run.id[-6:]}", f"{run.status} · {execution.nodeid}", f"/runs/{run.id}", run.status
            )
            for binding in matching:
                edge(
                    binding.id,
                    run.id,
                    "executed_by" if execution.status in {"PASSED", "FAILED", "ERROR"} else "attempted_by",
                )
        if run_ids:
            artifacts = (
                await self.session.scalars(
                    select(ExternalArtifactReferenceORM)
                    .where(ExternalArtifactReferenceORM.run_id.in_(run_ids))
                    .limit(501)
                )
            ).all()
            failures = (
                await self.session.scalars(
                    select(FailureRecordORM).where(FailureRecordORM.run_id.in_(run_ids)).limit(501)
                )
            ).all()
            analyses_by_failure = {}
            for analysis in (
                await self.session.scalars(
                    select(FailureAnalysisORM)
                    .where(FailureAnalysisORM.failure_id.in_([item.id for item in failures[:500]]))
                    .limit(2000)
                )
            ).all():
                analyses_by_failure.setdefault(analysis.failure_id, []).append(analysis)
            for artifact in artifacts[:500]:
                node(
                    artifact.id,
                    "evidence",
                    artifact.name,
                    artifact.type,
                    f"/runs/{artifact.run_id}?tab=artifacts",
                    metadata={"artifact_id": (artifact.metadata_json or {}).get("artifact_id")},
                )
                edge(artifact.run_id, artifact.id, "evidenced_by")
            for failure in failures[:500]:
                node(
                    failure.id,
                    "failure",
                    failure.classification,
                    failure.error_message,
                    f"/failures/{failure.id}",
                    "FAILED",
                )
                edge(failure.run_id, failure.id, "failed_with")
                proposal = failure.repair_proposal or {}
                if proposal.get("applied"):
                    patch_id = f"{failure.id}:patch"
                    node(
                        patch_id,
                        "patch",
                        "PATCH",
                        proposal.get("proposed_locator", "Reviewed patch"),
                        f"/failures/{failure.id}",
                        "APPLIED",
                    )
                    edge(failure.id, patch_id, "fixed_by")
                    for analysis in analyses_by_failure.get(failure.id, []):
                        result = analysis.result or {}
                        verification_id = result.get("verification_run_id")
                        if result.get("verified") and verification_id in run_ids:
                            edge(patch_id, verification_id, "validated_by")

        automated = {
            case_id for case_id, binding in binding_by_case.items() if binding.status in {"ACTIVE", "VALIDATED"}
        }
        executed = set(latest_execution) & automated
        passed = {case_id for case_id in executed if latest_execution[case_id][0].status == "PASSED"}
        metrics = []
        gaps = []

        def metric(key, label, items):
            covered = sum(bool(item["covered"]) for item in items)
            metrics.append(
                CoverageMetric(
                    key=key,
                    label=label,
                    covered=covered,
                    total=len(items),
                    percentage=round(covered * 100 / len(items), 1) if items and complete else None,
                    items=items,
                )
            )

        for kind, items in targets.items():
            details = []
            for key, title in items:
                covering = sorted(links.get(key, set()))
                if kind == "negative":
                    covering = [
                        case_id
                        for case_id in covering
                        if nodes[case_id].metadata["test_model"].get("path_type") == "negative"
                    ]
                details.append(
                    {
                        "id": key,
                        "label": key.split(":")[-1],
                        "summary": title,
                        "covered": bool(covering),
                        "case_ids": covering,
                        "automated_case_ids": sorted(set(covering) & automated),
                        "executed_case_ids": sorted(set(covering) & executed),
                        "passed_case_ids": sorted(set(covering) & passed),
                    }
                )
                if not covering or not (set(covering) & automated):
                    gaps.append(
                        {
                            "id": key,
                            "kind": kind,
                            "label": key.split(":")[-1],
                            "summary": title,
                            "reason": "no_test" if not covering else "no_automation",
                            "requirement_id": key.split(":")[0],
                        }
                    )
            metric(kind, kind, details)
        metric(
            "automation",
            "automation",
            [{"id": item.id, "label": nodes[item.id].label, "covered": item.id in automated} for item in cases],
        )
        metric(
            "execution",
            "execution",
            [{"id": key, "label": nodes[key].label, "covered": key in executed} for key in sorted(automated)],
        )
        metric(
            "passed",
            "passed",
            [
                {"id": key, "label": nodes[key].label, "covered": key in passed, "run_id": latest_execution[key][1].id}
                for key in sorted(executed)
            ],
        )

        counts = dict(Counter(item.kind for item in nodes.values()))
        counts["automated"] = len(automated)
        counts["executed"] = len(executed)
        counts["passed"] = len(passed)
        if focus:
            if focus not in nodes:
                raise ValueError("Knowledge focus does not belong to this project")
            selected = {focus}
            for _ in range(min(max(hops, 0), 2)):
                selected |= {target for source, target, _ in edges if source in selected} | {
                    source for source, target, _ in edges if target in selected
                }
            nodes = {key: value for key, value in nodes.items() if key in selected}
        truncated = not complete or len(nodes) > 300
        nodes = dict(list(nodes.items())[:300])
        return ProjectKnowledge(
            project_id=project_id,
            nodes=list(nodes.values()),
            edges=[
                KnowledgeEdge(source=source, target=target, relation=relation)
                for source, target, relation in sorted(edges)
                if source in nodes and target in nodes
            ],
            coverage=metrics,
            gaps=gaps,
            counts=counts,
            truncated=truncated,
        )

    async def explain(self, project_id: str, entity_id: str) -> dict:
        """Grounded relationship answer; no model is needed to enumerate actual links."""
        graph = await self.build(project_id, focus=entity_id, hops=2)
        current = next(item for item in graph.nodes if item.id == entity_id)
        return {
            "entity": current.model_dump(),
            "source": "persisted_relationships",
            "answer": current.summary,
            "relations": [item.model_dump() for item in graph.edges],
            "references": [item.model_dump() for item in graph.nodes if item.id != entity_id],
        }
