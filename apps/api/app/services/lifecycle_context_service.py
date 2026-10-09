"""Bounded server-owned semantic context, derived from validated IDs rather than client prose."""

import json

from project_model.lifecycle import ModernTestModel, RequirementDocument
from qa_core.failure.redactor import SensitiveRedactor

from app.ports.repository_scope import RepositoryScopeFactory


async def lifecycle_context(repository_scope: RepositoryScopeFactory, project_id, case_id=None, requirement_id=None):
    if not case_id and not requirement_id:
        return ""
    async with repository_scope() as repositories:
        cases = repositories.test_cases
        requirements = repositories.requirements
        result = {"source": "persisted_qa_entities", "references": []}
        case = await cases.get_by_id(case_id) if case_id else None
        if case_id and (not case or case.project_id != project_id):
            raise ValueError("Test case does not belong to this project")
        if case:
            if requirement_id and requirement_id != case.requirement_id:
                raise ValueError("Requirement does not belong to the selected test case")
            requirement_id = case.requirement_id
            model = ModernTestModel.model_validate(case.test_model) if case.test_model else None
            result["case"] = {
                "id": case.id,
                "title": case.title,
                "intent": model.intent if model else case.title,
                "data": model.data if model else {},
                "coverage": model.coverage.model_dump() if model else {},
                "oracles": [item.model_dump() for item in model.oracles] if model else [case.expected_result],
                "missing": model.missing if model else [],
                "steps": case.steps[:20],
            }
            result["references"].append(case.id)
        requirement = await requirements.get_by_id(requirement_id) if requirement_id else None
        if requirement_id and (not requirement or requirement.project_id != project_id):
            raise ValueError("Requirement does not belong to this project")
        if requirement:
            doc = RequirementDocument.model_validate(requirement.qa_model) if requirement.qa_model else None
            refs = set(sum(model.coverage.model_dump().values(), [])) if case and model else set()
            result["requirement"] = {
                "id": requirement.id,
                "title": requirement.title,
                "description": requirement.description[:1500],
                "criteria": [item.model_dump() for item in doc.criteria if not refs or item.id in refs][:12]
                if doc
                else requirement.acceptance_criteria[:2000],
                "rules": [item.model_dump() for item in doc.rules if not refs or item.id in refs][:8] if doc else [],
                "risks": [item.model_dump() for item in doc.analysis.risks if not refs or item.id in refs][:6]
                if doc and doc.analysis
                else [],
            }
            result["references"].append(requirement.id)
        rendered = json.dumps(SensitiveRedactor.redact_value(result), ensure_ascii=False)
        if len(rendered) > 12000:
            # Keep valid JSON and identities; remove verbose fields before truncation.
            result["truncated"] = True
            if "case" in result:
                result["case"].pop("steps", None)
                result["case"]["data"] = {"notice": "Input data exceeds context budget; inspect the case directly"}
            if "requirement" in result:
                result["requirement"].pop("risks", None)
                result["requirement"].pop("description", None)
            rendered = json.dumps(SensitiveRedactor.redact_value(result), ensure_ascii=False)
        if len(rendered) > 12000:
            rendered = json.dumps(
                {"source": "persisted_qa_entities", "references": result["references"], "truncated": True},
                ensure_ascii=False,
            )
        return rendered
