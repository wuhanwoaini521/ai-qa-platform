"""The workflow canvas only shows records that exist, and it never writes.

The canvas is the read model behind the workspace canvas: every node must be
traceable to a row, and a request must not create a task or a run.
"""

from __future__ import annotations

import pytest
from app.persistence.models import FailureAnalysisORM, QualityDiscoveryRunORM, TaskORM, TaskStepORM
from app.services.quality_discovery_models import DiscoveryStatus

pytestmark = pytest.mark.integration


async def _project(client) -> str:
    response = await client.post("/api/projects", json={"name": "Canvas project", "bootstrap_workspace": True})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _canvas(client, project_id: str) -> dict:
    response = await client.get(f"/api/projects/{project_id}/workflow-canvas")
    assert response.status_code == 200, response.text
    return response.json()


async def test_an_empty_project_returns_the_stages_and_no_invented_nodes(client):
    project_id = await _project(client)

    canvas = await _canvas(client, project_id)

    assert [stage["key"] for stage in canvas["stages"]] == [
        "discovery",
        "recorder",
        "studio",
        "run",
        "failure",
        "analysis",
        "approval",
        "verification",
    ]
    assert canvas["nodes"] == []
    assert canvas["edges"] == []
    assert set(canvas["counts"].values()) == {0}


async def test_a_discovery_run_becomes_one_node_with_its_real_counts_and_evidence(client, test_db_session):
    project_id = await _project(client)
    async with test_db_session() as session:
        session.add(
            QualityDiscoveryRunORM(
                id="qd_canvas",
                project_id=project_id,
                requested_by="tester",
                mode="VALIDATE",
                start_url="http://127.0.0.1:8000/api/demo-shop/index.html",
                status=DiscoveryStatus.STOPPED.value,
                result={
                    "states": [
                        {
                            "state_id": "state_a",
                            "url": "http://shop/",
                            "page_type": "home",
                            "evidence_id": "art_state_a",
                            "screenshot_evidence_id": "art_shot_a",
                            "controls": [{}, {}],
                            "network": {"responses": {"2xx": 3}},
                        }
                    ],
                    "actions": [{"candidate_id": "cand_1", "action_type": "click", "status": "APPLIED"}],
                    "features": [{"id": "f1"}, {"id": "f2"}],
                    "requirements": [{"id": "r1"}],
                    "gaps": [{"id": "gap-1"}, {"id": "gap-2"}, {"id": "gap-3"}],
                    "coverage": [
                        {"coverage_status": "COVERED", "test_case_ids": ["tc_1"]},
                        {"coverage_status": "NOT_COVERED", "test_case_ids": []},
                    ],
                },
            )
        )
        await session.commit()

    canvas = await _canvas(client, project_id)

    assert len(canvas["nodes"]) == 1
    node = canvas["nodes"][0]
    assert node["kind"] == "DISCOVERY"
    assert node["entity_type"] == "discovery_run"
    assert node["entity_id"] == "qd_canvas"
    assert node["status"] == "STOPPED"
    assert node["metrics"] == {
        "states": 1,
        "actions": 1,
        "features": 2,
        "requirements": 1,
        "gaps": 3,
        "covered": 1,
        "partial": 0,
        "not_covered": 1,
        "test_cases": 1,
        # No evidence rows exist for this run, and the canvas says so rather than inventing numbers.
        "evidence": {
            "dom_elements": 0,
            "dom_elements_deduped": 0,
            "page_states": 0,
            "locators": 0,
            "locators_ambiguous": 0,
            "requests": 0,
            "requests_associated": 0,
            "actions": 0,
            "state_changes": 0,
            "scenarios": 0,
            "covered": 0,
            "candidate_gaps": 0,
            "undetermined": 0,
            "captured": False,
        },
        # No readings exist either, so nothing is attributed to the model layer.
        "intelligence": None,
    }
    collections = {item["collection"] for item in node["evidence_index"]}
    assert collections == {"page_state", "screenshot", "network", "action"}
    page_state = next(item for item in node["evidence_index"] if item["collection"] == "page_state")
    assert page_state["artifact_ref"] == "art_state_a"
    assert page_state["page_url"] == "http://shop/"
    assert page_state["collection_method"] == "browser_runtime"


async def test_requirement_filter_is_applied_before_discovery_limit(client, test_db_session):
    project_id = await _project(client)
    first = await client.post(
        "/api/requirements",
        json={"project_id": project_id, "title": "Target requirement", "description": "", "acceptance_criteria": ""},
    )
    other = await client.post(
        "/api/requirements",
        json={"project_id": project_id, "title": "Other requirement", "description": "", "acceptance_criteria": ""},
    )
    target_id, other_id = first.json()["id"], other.json()["id"]
    async with test_db_session() as session:
        for index in range(8):
            session.add(
                QualityDiscoveryRunORM(
                    id=f"qd_filter_{index}",
                    project_id=project_id,
                    requested_by="tester",
                    mode="VALIDATE",
                    start_url="http://example.test/",
                    requirement_id=target_id if index == 0 else other_id,
                    status=DiscoveryStatus.STOPPED.value,
                    result={"states": []},
                )
            )
        await session.commit()

    response = await client.get(f"/api/projects/{project_id}/workflow-canvas", params={"requirement_id": target_id})
    assert response.status_code == 200, response.text
    canvas = response.json()
    assert [node["entity_id"] for node in canvas["nodes"] if node["kind"] == "DISCOVERY"] == ["qd_filter_0"]
    assert canvas["discovery_match_count"] == 1
    assert canvas["discovery_truncated"] is False

    all_runs = await client.get(f"/api/projects/{project_id}/workflow-canvas")
    all_canvas = all_runs.json()
    assert len([node for node in all_canvas["nodes"] if node["kind"] == "DISCOVERY"]) == 3
    assert all_canvas["discovery_match_count"] == 8
    assert all_canvas["discovery_truncated"] is True


async def test_a_failure_brings_its_repair_chain_and_the_links_that_join_them(client, test_db_session):
    project_id = await _project(client)
    file_path = "tests/test_canvas.py"
    written = await client.put(
        f"/api/workspaces/{project_id}/file",
        json={"path": file_path, "content": "def test_canvas():\n    assert True\n"},
    )
    assert written.status_code == 200, written.text

    from app.repositories.test_run_repo import TestRunRepository
    from project_model.models import RunStatus, TestRunCreate

    owner_id = (await client.get("/api/auth/me")).json()["user"]["id"]
    async with test_db_session() as session:
        run_repo = TestRunRepository(session)
        run = await run_repo.create_run(TestRunCreate(project_id=project_id, workspace_id=project_id))
        execution = await run_repo.add_execution(
            run_id=run.id, nodeid=f"{file_path}::test_canvas", status=RunStatus.FAILED
        )
        failure = await run_repo.create_failure_record(
            run_id=run.id,
            execution_id=execution.id,
            test_nodeid=f"{file_path}::test_canvas",
            test_name="test_canvas",
            classification="LOCATOR_CHANGED",
            exception_type="TimeoutError",
            error_message="locator not found",
            stack_trace="",
            failing_locator="[data-testid=old]",
            source_file="pages/canvas.py",
            source_line=12,
        )
        session.add(
            FailureAnalysisORM(
                id="analysis_canvas",
                failure_id=failure.id,
                status="COMPLETED",
                result={
                    "diagnosis": {"root_cause": "the button locator changed"},
                    "repair_state": "PATCH_READY",
                },
            )
        )
        session.add(
            TaskORM(
                id="task_canvas",
                type="FIX_FAILURE",
                goal="Fix the failing locator",
                status="WAITING",
                owner_id=owner_id,
                project_id=project_id,
                inputs={"failure_id": failure.id},
            )
        )
        session.add(
            TaskStepORM(
                id="step_approval",
                task_id="task_canvas",
                position=0,
                key="approval",
                name="Approve the source change",
                tool="task.request_approval",
                status="WAITING_FOR_APPROVAL",
            )
        )
        session.add(
            TaskStepORM(
                id="step_verify",
                task_id="task_canvas",
                position=1,
                key="verify",
                name="Verify the target test",
                tool="tests.verify",
                status="PENDING",
            )
        )
        await session.commit()
        run_id = run.id
        failure_id = failure.id

    canvas = await _canvas(client, project_id)

    by_kind = {node["kind"]: node for node in canvas["nodes"]}
    assert {"RUN", "FAILURE", "FAILURE_ANALYSIS", "HUMAN_APPROVAL", "EXACT_VERIFICATION"} <= set(by_kind)
    assert by_kind["FAILURE"]["entity_id"] == failure_id
    assert by_kind["FAILURE"]["subtitle"] == "pages/canvas.py:12"
    assert by_kind["FAILURE"]["parent_id"] == f"run:{run_id}"
    assert by_kind["FAILURE_ANALYSIS"]["entity_id"] == "analysis_canvas"
    assert by_kind["HUMAN_APPROVAL"]["status"] == "WAITING_FOR_APPROVAL"
    assert by_kind["HUMAN_APPROVAL"]["task_id"] == "task_canvas"

    kinds = {(edge["source"].split(":")[0], edge["target"].split(":")[0], edge["kind"]) for edge in canvas["edges"]}
    assert ("run", "failure", "FAILED_AS") in kinds
    assert ("failure", "analysis", "ANALYZED_BY") in kinds
    assert ("analysis", "approval", "PENDING_APPROVAL") in kinds
    assert ("approval", "verification", "VERIFIED_BY") in kinds


async def test_reading_the_canvas_creates_no_task_and_no_run(client, test_db_session):
    project_id = await _project(client)
    before = (await client.get(f"/api/tasks?project_id={project_id}")).json()
    runs_before = (await client.get(f"/api/runs?project_id={project_id}")).json()

    await _canvas(client, project_id)
    await _canvas(client, project_id)

    assert (await client.get(f"/api/tasks?project_id={project_id}")).json() == before
    assert (await client.get(f"/api/runs?project_id={project_id}")).json() == runs_before


async def test_a_project_outside_the_users_scope_is_not_projected(client, role_client):
    project_id = await _project(client)

    async with role_client("QA_ENGINEER") as engineer:
        response = await engineer.get(f"/api/projects/{project_id}/workflow-canvas")

    assert response.status_code in {403, 404}, response.text


async def test_the_discovery_node_shows_the_evidence_counts_the_evidence_api_reports(client, test_db_session):
    from app.repositories.discovery_evidence_repo import DiscoveryEvidenceRepository
    from app.services.discovery_evidence_capture import CaptureStats, build_action_records, build_state_records

    project_id = await _project(client)
    async with test_db_session() as session:
        session.add(
            QualityDiscoveryRunORM(
                id="qd_evidence",
                project_id=project_id,
                requested_by="tester",
                mode="VALIDATE",
                start_url="http://127.0.0.1:8000/api/demo-shop/index.html",
                status=DiscoveryStatus.COMPLETED.value,
                result={"states": [{"state_id": "state_a", "url": "http://shop/", "fingerprint": "fp_a"}]},
            )
        )
        await session.commit()
    control = {
        "index": 0,
        "tag": "button",
        "role": "button",
        "name": "Add to cart",
        "test_id": "",
        "id": "",
        "href": "",
        "visible": True,
        "enabled": True,
        "in_viewport": True,
        "value": "",
    }
    state = {"state_id": "state_a", "fingerprint": "fp_a", "url": "http://shop/", "title": "Shop", "depth": 0}
    action = {
        "from_state_id": "state_a",
        "action_type": "click",
        "target": "Add to cart",
        "status": "EXECUTED",
        "state_changed": True,
        "to_fingerprint": "fp_b",
    }
    async with test_db_session() as session:
        repository = DiscoveryEvidenceRepository(session)
        await repository.record(
            "qd_evidence",
            project_id,
            build_state_records(state, [control, dict(control, index=1)], CaptureStats(), url="http://shop/"),
            max_records=6000,
        )
        await repository.record(
            "qd_evidence",
            project_id,
            build_action_records(
                action,
                {"kind": "role", "value": "button", "name": "Add to cart"},
                {"match_count": 2, "unique": False, "visible": True, "verified": True},
                CaptureStats(),
                url="http://shop/",
                requests=[{"method": "POST", "url": "http://shop/api/cart", "status": 201}],
                association="prefix",
            ),
            max_records=6000,
        )
        await session.commit()

    node = (await _canvas(client, project_id))["nodes"][0]
    evidence = node["metrics"]["evidence"]

    assert evidence["captured"] is True
    assert evidence["dom_elements_deduped"] == 1
    assert evidence["locators"] == 1
    assert evidence["locators_ambiguous"] == 1
    assert evidence["requests"] == 1
    assert evidence["requests_associated"] == 1
    assert evidence["state_changes"] == 1
    assert {link for link in node["links"]} >= {"evidence", "scenarios", "diff"}
    summary = await client.get("/api/discovery/runs/qd_evidence/evidence/summary")
    assert summary.json()["analysis"]["dom_element"]["deduped"] == evidence["dom_elements_deduped"]
    assert (
        node["metrics"]["evidence"]["requests_associated"]
        == summary.json()["analysis"]["network_request"]["associated"]
    )


async def test_the_discovery_node_counts_the_readings_the_suggestion_api_reports(client, test_db_session):
    from app.repositories.discovery_suggestion_repo import DiscoverySuggestionRepository

    project_id = await _project(client)
    async with test_db_session() as session:
        session.add(
            QualityDiscoveryRunORM(
                id="qd_readings",
                project_id=project_id,
                requested_by="tester",
                mode="VALIDATE",
                start_url="http://127.0.0.1:8000/api/demo-shop/index.html",
                status=DiscoveryStatus.COMPLETED.value,
                result={"states": []},
            )
        )
        await session.commit()
    async with test_db_session() as session:
        await DiscoverySuggestionRepository(session).upsert_many(
            "qd_readings",
            project_id,
            [
                {
                    "suggestion_id": "sugg_a",
                    "scenario_id": "scen_a",
                    "analysis_status": "COMPLETED",
                    "input_hash": "hash_a",
                    "evidence_ids": ["dom_a"],
                    "jev": {"status": "JEV_GRADED", "source": "jev", "grade": "sufficient"},
                },
                {
                    "suggestion_id": "sugg_b",
                    "scenario_id": "scen_b",
                    "analysis_status": "INSUFFICIENT_EVIDENCE",
                    "input_hash": "hash_b",
                    "evidence_ids": [],
                    "jev": {"status": "JEV_FALLBACK", "source": "rules", "grade": "thin"},
                },
            ],
        )
        await session.commit()

    node = (await _canvas(client, project_id))["nodes"][0]
    intelligence = node["metrics"]["intelligence"]
    summary = (await client.get("/api/discovery/runs/qd_readings/suggestions/summary")).json()

    assert intelligence["suggestions"] == summary["total"] == 2
    assert intelligence["pending_review"] == summary["pending_review"] == 2
    assert intelligence["insufficient"] == 1
    assert intelligence["jev_graded"] == 1
    assert intelligence["jev_fallback"] == 1
