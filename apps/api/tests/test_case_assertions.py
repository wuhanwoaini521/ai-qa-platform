"""Case-level assertions: one expectation per criterion, bound to its own test function."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.container import get_requirement_lifecycle_service
from app.main import app
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.repositories.test_run_repo import TestRunRepository
from app.services.requirement_lifecycle_service import RequirementLifecycleService
from project_model.models import RunStatus, TestRunCreate
from qa_core.ai.models import AICompletionResponse

SCRIPT = """from playwright.sync_api import Page, expect


def test_total_is_discounted(page: Page):
    # criterion: AC-001
    page.goto("http://127.0.0.1:5183/")
    expect(page.locator("#total")).to_have_text("90.00")
"""


class Orchestrator:
    __test__ = False

    def __init__(self, payload: dict):
        self.payload = payload
        self.ai_provider = SimpleNamespace(provider_name="unit_fixture", model="assertion_fixture")

    async def complete(self, request):
        return AICompletionResponse(
            content="{}", structured_data=self.payload, provider="unit_fixture", model="assertion_fixture"
        )


async def _seed_requirement_with_assertion(client, test_db_session) -> dict:
    project = (
        await client.post("/api/projects", json={"name": "Case assertion probe", "bootstrap_workspace": True})
    ).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Checkout discount",
                "description": "A valid code reduces the total.",
                "acceptance_criteria": "Valid code reduces the total",
            },
        )
    ).json()
    app.dependency_overrides[get_requirement_lifecycle_service] = lambda: RequirementLifecycleService(
        TaskRepositoryScopeFactory(),
        Orchestrator(
            {
                "assertions": [
                    {
                        "criterion_id": "AC-001",
                        "statement": "Order total shows 90.00 after a 10% code",
                        "check": "read total",
                    }
                ]
            }
        ),
    )
    drafts = (await client.post(f"/api/requirements/{requirement['id']}/assertions/draft")).json()
    await client.post(
        f"/api/requirements/{requirement['id']}/assertions/{drafts[0]['id']}/adoption", json={"adopted": True}
    )
    app.dependency_overrides.pop(get_requirement_lifecycle_service, None)
    return {"project": project, "requirement": requirement, "assertion": drafts[0]}


@pytest.mark.asyncio
async def test_adopted_requirement_assertion_becomes_case_assertion(client, test_db_session):
    from app.persistence.models import RequirementORM, TestDesignORM

    seeded = await _seed_requirement_with_assertion(client, test_db_session)
    scenario = {
        "id": "SCN-001",
        "title": "Discount applied",
        "intent": "Apply a valid discount code and read the total",
        "coverage": {"criterion_ids": ["AC-001"]},
        "actions": ["open checkout", "apply code"],
        "expected_outcomes": ["total is 90.00"],
    }
    async with test_db_session() as session:
        requirement_row = await session.get(RequirementORM, seeded["requirement"]["id"])
        qa_model = dict(requirement_row.qa_model or {})
        analysis = dict(qa_model.get("analysis") or {})
        analysis.setdefault("summary", "Checkout discount analysis")
        analysis.setdefault("business_flow", [{"id": "FLOW-001", "title": "Checkout", "criterion_ids": ["AC-001"]}])
        analysis.setdefault(
            "risks",
            [
                {
                    "id": "RISK-001",
                    "title": "Discount applied twice",
                    "severity": "High",
                    "impact": "Total is wrong",
                    "criterion_ids": ["AC-001"],
                }
            ],
        )
        analysis.setdefault("scenarios", [])
        analysis["scenarios"] = [*analysis["scenarios"], scenario]
        qa_model["analysis"] = analysis
        requirement_row.qa_model = qa_model
        session.add(
            TestDesignORM(
                id="tds_fixture_1",
                requirement_id=seeded["requirement"]["id"],
                title="Discount applied",
                scenario_model=scenario,
            )
        )
        await session.commit()

    adopted = await client.post("/api/test-designs/tds_fixture_1/lifecycle/case")
    assert adopted.status_code == 200, adopted.text
    case = adopted.json()
    assertions = case["test_model"]["assertions"]
    assert len(assertions) == 1
    assert assertions[0]["criterion_id"] == "AC-001"
    assert assertions[0]["nodeid"] == ""

    # Saving a script binds the case assertion to its own test function.
    saved = await client.post(
        f"/api/requirements/{seeded['requirement']['id']}/assertions/script/save",
        json={"path": "tests/test_total.py", "code": SCRIPT, "assertion_ids": [seeded["assertion"]["id"]]},
    )
    assert saved.status_code == 200, saved.text

    from app.persistence.models import TestCaseORM

    async with test_db_session() as dbg:
        row = await dbg.get(TestCaseORM, case["id"])
        print("DEBUG db row", (row.test_model or {}).get("assertions"))
    body = (await client.get(f"/api/test-cases/{case['id']}/assertions")).json()
    assert len(body["assertions"]) == 1
    assert body["assertions"][0]["nodeid"] == "tests/test_total.py::test_total_is_discounted"
    assert body["assertions"][0]["state"] == "NEVER_RUN"

    nodeid = body["assertions"][0]["nodeid"]
    async with test_db_session() as session:
        repository = TestRunRepository(session)
        run = await repository.create_run(
            TestRunCreate(
                project_id=seeded["project"]["id"],
                workspace_id=seeded["project"]["id"],
                requirement_id=seeded["requirement"]["id"],
                case_id=case["id"],
                nodeids=[nodeid],
            )
        )
        await repository.add_execution(run.id, nodeid, RunStatus.PASSED, duration_ms=1200.0)
        await repository.update_run_status(run.id, RunStatus.PASSED, total=1, passed=1, failed=0)
        await session.commit()
        run_id = run.id

    body = (await client.get(f"/api/test-cases/{case['id']}/assertions")).json()
    assert body["assertions"][0]["state"] == "PASSED"
    assert body["assertions"][0]["run"]["run_id"] == run_id


@pytest.mark.asyncio
async def test_case_without_bound_function_reports_unbound(client, test_db_session):
    seeded = await _seed_requirement_with_assertion(client, test_db_session)
    project = seeded["project"]
    requirement = seeded["requirement"]
    case = await client.post(
        "/api/test-cases",
        json={
            "project_id": project["id"],
            "requirement_id": requirement["id"],
            "title": "Manual case",
            "steps": ["open page"],
            "test_model": {
                "intent": "manual",
                "coverage": {"criterion_ids": []},
                "assertions": [
                    {
                        "id": "TCA-manual-1",
                        "criterion_id": "AC-001",
                        "statement": "Manual expectation without a bound test function",
                        "check": "",
                    }
                ],
            },
        },
    )
    assert case.status_code in {200, 201}, case.text
    body = (await client.get(f"/api/test-cases/{case.json()['id']}/assertions")).json()
    assert body["assertions"][0]["state"] == "UNBOUND"
