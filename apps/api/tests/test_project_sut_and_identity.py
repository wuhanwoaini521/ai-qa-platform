"""Project SUT address, overview visibility, and requirement/case identity on runs."""

from __future__ import annotations

import pytest
from app.repositories.test_run_repo import TestRunRepository
from project_model.models import RunStatus, TestRunCreate


@pytest.mark.asyncio
async def test_project_records_sut_address_and_overview_visibility(client):
    created = await client.post(
        "/api/projects",
        json={
            "name": "SUT probe",
            "bootstrap_workspace": False,
            "sut_base_url": "https://shop.example.test",
            "hidden_from_overview": True,
        },
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["sut_base_url"] == "https://shop.example.test"
    assert project["hidden_from_overview"] is True

    updated = await client.patch(f"/api/projects/{project['id']}", json={"hidden_from_overview": False})
    assert updated.status_code == 200, updated.text
    assert updated.json()["hidden_from_overview"] is False

    invalid = await client.post(
        "/api/projects",
        json={"name": "Bad SUT", "bootstrap_workspace": False, "sut_base_url": "javascript:alert(1)"},
    )
    assert invalid.status_code == 422

    credentials = await client.post(
        "/api/projects",
        json={"name": "Bad SUT 2", "bootstrap_workspace": False, "sut_base_url": "https://user:pass@x.test"},
    )
    assert credentials.status_code == 422


@pytest.mark.asyncio
async def test_hidden_projects_leave_overview_statistics(client):
    project = (
        await client.post(
            "/api/projects",
            json={"name": "Hidden probe", "bootstrap_workspace": False, "hidden_from_overview": True},
        )
    ).json()
    stats = (await client.get("/api/dashboard/stats")).json()
    # Hidden projects are not counted and not listed in the overview.
    listed = {item["id"] for item in stats.get("recent_projects", [])}
    assert project["id"] not in listed
    management = (await client.get("/api/projects")).json()
    assert project["id"] in {item["id"] for item in management}


@pytest.mark.asyncio
async def test_run_records_requirement_and_case_identity(client, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Identity probe", "bootstrap_workspace": True})).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Identity requirement",
                "description": "desc",
                "acceptance_criteria": "One criterion",
            },
        )
    ).json()
    nodeid = "tests/test_identity.py::test_identity"
    async with test_db_session() as session:
        repository = TestRunRepository(session)
        run = await repository.create_run(
            TestRunCreate(
                project_id=project["id"],
                workspace_id=project["id"],
                requirement_id=requirement["id"],
                nodeids=[nodeid],
            )
        )
        await session.commit()
        run_id = run.id

    fetched = await client.get(f"/api/runs/{run_id}")
    assert fetched.status_code == 200, fetched.text
    body = fetched.json()
    assert body["requirement_id"] == requirement["id"]
    assert body["case_id"] is None


@pytest.mark.asyncio
async def test_failure_records_inherit_run_identity(client, test_db_session):
    project = (
        await client.post("/api/projects", json={"name": "Failure identity", "bootstrap_workspace": True})
    ).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Failure identity requirement",
                "description": "desc",
                "acceptance_criteria": "One criterion",
            },
        )
    ).json()
    async with test_db_session() as session:
        repository = TestRunRepository(session)
        run = await repository.create_run(
            TestRunCreate(
                project_id=project["id"],
                workspace_id=project["id"],
                requirement_id=requirement["id"],
            )
        )
        execution = await repository.add_execution(run.id, "tests/test_x.py::test_x", RunStatus.FAILED)
        failure = await repository.create_failure_record(
            run_id=run.id,
            execution_id=execution.id,
            test_nodeid="tests/test_x.py::test_x",
            test_name="test_x",
            classification="LOCATOR_CHANGED",
            exception_type="TimeoutError",
            error_message="locator missing",
            stack_trace="trace",
            requirement_id=run.requirement_id,
        )
        await session.commit()
        failure_id = failure.id

    stored = (await client.get(f"/api/failures/{failure_id}")).json()
    assert stored["requirement_id"] == requirement["id"]
    assert stored["case_id"] is None
