"""Validate modern coverage references against existing project entities."""

import hashlib
import json

from project_model.lifecycle import ModernTestModel, RequirementDocument, TestScenario
from sqlalchemy import select

from app.persistence.models import RequirementORM, TestCaseORM, TestDesignORM


def input_hash(title, description, acceptance_criteria, document):
    data = [title, description, acceptance_criteria, document.model_dump(exclude={"analysis", "history"}, mode="json")]
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def validate_case_model(session, data):
    design = await session.get(TestDesignORM, data.test_design_id) if data.test_design_id else None
    if data.test_design_id and not design:
        raise ValueError("Test design does not exist")
    requirement_id = data.requirement_id or (design.requirement_id if design else None)
    requirement = await session.get(RequirementORM, requirement_id) if requirement_id else None
    if requirement_id and (not requirement or requirement.project_id != data.project_id):
        raise ValueError("Test case requirement belongs to a different project or does not exist")
    if design and design.requirement_id != requirement_id:
        raise ValueError("Test design and test case refer to different requirements")
    if data.test_model:
        if not requirement or not requirement.qa_model:
            raise ValueError("Modern coverage requires a structured requirement")
        document = RequirementDocument.model_validate(requirement.qa_model)
        document.validate_coverage(data.test_model.coverage)
        for oracle in data.test_model.oracles:
            if not set(oracle.criterion_ids) <= {item.id for item in document.criteria}:
                raise ValueError("Oracle refers to an unknown acceptance criterion")
        known = {item.id for item in document.analysis.scenarios} if document.analysis else set()
        if design and design.scenario_model:
            known.add(design.scenario_model["id"])
        if data.test_model.scenario_id and data.test_model.scenario_id not in known:
            raise ValueError("Test case refers to an unknown scenario")
    return data.model_copy(update={"requirement_id": requirement_id})


async def validate_design_model(session, data):
    requirement = await session.get(RequirementORM, data.requirement_id)
    if not requirement:
        raise ValueError("Requirement does not exist")
    if data.scenario_model:
        if not requirement.qa_model:
            raise ValueError("Scenario coverage requires a structured requirement")
        RequirementDocument.model_validate(requirement.qa_model).validate_coverage(data.scenario_model.coverage)


async def validate_requirement_replacement(session, requirement_id, document):
    """A changed model cannot silently orphan already adopted designs or cases."""
    cases = (await session.execute(select(TestCaseORM).where(TestCaseORM.requirement_id == requirement_id))).scalars()
    for case in cases:
        if case.test_model:
            if not document:
                raise ValueError("Cannot remove a requirement model used by test cases")
            model = ModernTestModel.model_validate(case.test_model)
            document.validate_coverage(model.coverage)
            known = {item.id for item in document.criteria}
            if any(not set(oracle.criterion_ids) <= known for oracle in model.oracles):
                raise ValueError("Cannot remove acceptance criteria used by test oracles")
            if model.scenario_id and (
                not document.analysis or model.scenario_id not in {item.id for item in document.analysis.scenarios}
            ):
                raise ValueError("Cannot remove scenarios used by test cases")
    designs = (
        await session.execute(select(TestDesignORM).where(TestDesignORM.requirement_id == requirement_id))
    ).scalars()
    for design in designs:
        if design.scenario_model:
            if not document:
                raise ValueError("Cannot remove a requirement model used by test designs")
            document.validate_coverage(TestScenario.model_validate(design.scenario_model).coverage)
