"""Discovery evidence through the API: real rows in, traceable facts, no invented numbers.

The capture rules are pinned by unit tests; these exercise the derived view a user sees — counts
with their arithmetic, locator uniqueness, request/action association, candidate scenarios matched
to existing cases, and a run-to-run diff that reports missing evidence as missing.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import pytest
from app.persistence.models import QualityDiscoveryRunORM
from app.repositories.discovery_evidence_repo import DiscoveryEvidenceRepository
from app.services.discovery_evidence_capture import (
    DOM_ELEMENT,
    USER_ACTION,
    CaptureStats,
    build_action_records,
    build_state_records,
)
from app.services.quality_discovery_execution import _stamp_state_capture

pytestmark = pytest.mark.integration

START_URL = "http://127.0.0.1:8000/api/demo-shop/index.html"


def _control(name: str, **overrides):
    control = {
        "index": 0,
        "tag": "button",
        "role": "button",
        "name": name,
        "type": "",
        "href": "",
        "has_query": False,
        "has_credentials": False,
        "test_id": "",
        "id": "",
        "visible": True,
        "enabled": True,
        "in_viewport": True,
        "checked": False,
        "selected": False,
        "value": "",
        "bounding_box": {"x": 0, "y": 0, "width": 10, "height": 10},
    }
    control.update(overrides)
    return control


def _state(state_id: str, fingerprint: str) -> dict:
    return {
        "state_id": state_id,
        "fingerprint": fingerprint,
        "url": f"{START_URL}?state={state_id}",
        "title": "Demo shop",
        "depth": 0,
        "visible_controls": 4,
    }


async def _project(client) -> str:
    response = await client.post("/api/projects", json={"name": "Evidence project", "bootstrap_workspace": True})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _run(test_db_session, project_id: str, run_id: str, *, created_at=None, states=None) -> None:
    async with test_db_session() as session:
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="tester",
                mode="VALIDATE",
                start_url=START_URL,
                status="STOPPED",
                result={"states": states if states is not None else [_state("state_a", "fp_a")]},
                **({"created_at": created_at} if created_at else {}),
            )
        )
        await session.commit()


async def _capture_state(
    test_db_session, run_id: str, project_id: str, *, controls, requests=None, stamp_state: bool = False
) -> None:
    """Store exactly what the capture service would store for one observed state."""
    state = _state("state_a", "fp_a")
    stats = CaptureStats()
    records = build_state_records(state, controls, stats, url=state["url"], requests=requests or [])
    async with test_db_session() as session:
        await DiscoveryEvidenceRepository(session).record(run_id, project_id, records, max_records=6000)
        if stamp_state:
            # The run row keeps the per-state counters the raw numbers are summed from. A JSON column
            # is not change-tracked through in-place mutation, so assign a fresh structure.
            run = await session.get(QualityDiscoveryRunORM, run_id)
            result = copy.deepcopy(run.result)
            _stamp_state_capture(result, "state_a", stats.as_dict())
            run.result = result
            session.add(run)
        await session.commit()


async def _capture_action(test_db_session, run_id: str, project_id: str, *, target: str, requests=None) -> None:
    action = {
        "from_state_id": "state_a",
        "action_type": "click",
        "target": target,
        "status": "EXECUTED",
        "state_changed": True,
        "to_fingerprint": "fp_b",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:02+00:00",
    }
    candidate = {"kind": "role", "value": "button", "name": target, "exact": True, "nth": 0}
    records = build_action_records(
        action,
        candidate,
        {"match_count": 1, "unique": True, "visible": True, "verified": True},
        CaptureStats(),
        url=START_URL,
        requests=requests or [],
        association="prefix" if requests else "none",
    )
    async with test_db_session() as session:
        await DiscoveryEvidenceRepository(session).record(run_id, project_id, records, max_records=6000)
        await session.commit()


async def test_the_summary_explains_every_count_with_the_rule_that_produced_it(client, test_db_session):
    project_id = await _project(client)
    await _run(test_db_session, project_id, "qd_summary")
    await _capture_state(
        test_db_session,
        "qd_summary",
        project_id,
        controls=[
            _control("Add to cart"),
            _control("Add to cart", index=1),
            _control("Add to cart", index=2),
            _control("Checkout", index=3),
        ],
        stamp_state=True,
    )

    response = await client.get("/api/discovery/runs/qd_summary/evidence/summary")

    assert response.status_code == 200, response.text
    analysis = response.json()["analysis"]
    assert analysis["dom_element"]["raw"] == 4
    assert analysis["dom_element"]["deduped"] == 2
    # Three identical buttons collapse into one fact: nothing was thrown away, so filtered stays 0.
    assert analysis["dom_element"]["filtered"] == 0
    assert analysis["dom_element"]["raw"] - analysis["dom_element"]["deduped"] == 2
    assert analysis["page_state"]["total"] == 1
    # Every count names the rule that produced it; the consumer never has to guess.
    assert analysis["measures"]["dom_element.deduped"]
    assert analysis["measures"]["network_request.unassociated"]
    assert response.json()["counts"][DOM_ELEMENT] == 2


async def test_a_locator_report_carries_the_real_match_count_and_says_which_ones_are_ambiguous(client, test_db_session):
    project_id = await _project(client)
    await _run(test_db_session, project_id, "qd_locator")
    await _capture_action(test_db_session, "qd_locator", project_id, target="Add to cart")

    response = await client.get("/api/discovery/runs/qd_locator/evidence/summary")

    locators = response.json()["analysis"]["locator_candidate"]
    assert locators["total"] == 1
    assert locators["unique"] == 1
    assert locators["verified"] == 1
    assert locators["ambiguous"] == 0


async def test_a_request_is_tied_to_the_action_that_caused_it(client, test_db_session):
    project_id = await _project(client)
    await _run(test_db_session, project_id, "qd_assoc")
    await _capture_action(
        test_db_session,
        "qd_assoc",
        project_id,
        target="Add to cart",
        requests=[{"method": "POST", "url": f"{START_URL}/api/cart", "status": 201}],
    )

    response = await client.get("/api/discovery/runs/qd_assoc/evidence/summary")

    network = response.json()["analysis"]["network_request"]
    assert network["stored"] == 1
    assert network["associated"] == 1
    assert network["unassociated"] == 0
    assert network["association_methods"] == {"prefix": 1}
    assert network["by_resource"]["api"] == 1

    rows = (await client.get("/api/discovery/runs/qd_assoc/evidence?kind=network_request")).json()
    assert rows[0]["payload"]["action_evidence_id"]
    detail = await client.get(f"/api/discovery/runs/qd_assoc/evidence/{rows[0]['evidence_id']}")
    assert detail.status_code == 200
    assert detail.json()["payload"]["url_template"].endswith("/api/cart")


async def test_evidence_is_filterable_and_an_unknown_id_is_404(client, test_db_session):
    project_id = await _project(client)
    await _run(test_db_session, project_id, "qd_filter")
    await _capture_state(test_db_session, "qd_filter", project_id, controls=[_control("Add to cart")])
    await _capture_action(test_db_session, "qd_filter", project_id, target="Checkout")

    elements = (await client.get("/api/discovery/runs/qd_filter/evidence?kind=dom_element")).json()
    actions = (await client.get("/api/discovery/runs/qd_filter/evidence?kind=user_action")).json()

    assert [row["kind"] for row in elements] == [DOM_ELEMENT]
    assert [row["kind"] for row in actions] == [USER_ACTION]
    assert (await client.get("/api/discovery/runs/qd_filter/evidence/nope")).status_code == 404
    assert (await client.get("/api/discovery/runs/qd_unknown/evidence")).status_code == 404


async def test_a_candidate_scenario_matches_an_existing_case_and_the_rest_stay_candidates(client, test_db_session):
    project_id = await _project(client)
    await _run(test_db_session, project_id, "qd_scenarios")
    await _capture_action(
        test_db_session,
        "qd_scenarios",
        project_id,
        target="Add to cart",
        requests=[{"method": "POST", "url": f"{START_URL}/api/cart", "status": 201}],
    )
    await _capture_action(test_db_session, "qd_scenarios", project_id, target="Checkout now")
    covered = await client.post(
        "/api/test-cases",
        json={
            "project_id": project_id,
            "title": "Add to cart from the product page",
            "priority": "P1",
            "automation_status": "MANUAL",
            "steps": ["Open the product", "Add to cart"],
        },
    )
    assert covered.status_code == 201, covered.text
    await client.post(
        "/api/test-cases",
        json={"project_id": project_id, "title": "Search filters narrow results", "priority": "P2"},
    )

    refreshed = await client.post("/api/discovery/runs/qd_scenarios/scenarios/refresh")

    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()
    by_title = {item["title"]: item for item in body["scenarios"]}
    matched = next(item for item in body["scenarios"] if "Add to cart" in item["title"])
    assert matched["coverage_status"] == "COVERED"
    assert matched["test_case_ids"] == [covered.json()["id"]]
    assert matched["match_method"] in {"locator_value", "target_wording"}
    # The unmatched behaviour is a candidate gap the user still has to confirm — never a verdict.
    assert any(item["coverage_status"] == "CANDIDATE_GAP" for item in body["scenarios"])
    assert body["summary"]["measures"]
    assert by_title

    # Refreshing twice is idempotent: the same facts produce the same scenarios, not new rows.
    again = (await client.post("/api/discovery/runs/qd_scenarios/scenarios/refresh")).json()
    assert [item["scenario_id"] for item in again["scenarios"]] == sorted(
        item["scenario_id"] for item in body["scenarios"]
    )
    assert len(again["scenarios"]) == len(body["scenarios"])


async def test_the_diff_reports_real_changes_and_never_turns_missing_evidence_into_a_disappearance(
    client, test_db_session
):
    project_id = await _project(client)
    earlier = datetime(2026, 1, 1, tzinfo=UTC)
    await _run(test_db_session, project_id, "qd_old", created_at=earlier)
    await _capture_state(test_db_session, "qd_old", project_id, controls=[_control("Add to cart"), _control("Search")])
    await _run(test_db_session, project_id, "qd_new", created_at=earlier + timedelta(hours=1))
    await _capture_state(
        test_db_session, "qd_new", project_id, controls=[_control("Add to cart"), _control("Checkout")]
    )

    response = await client.get("/api/discovery/runs/qd_new/evidence/diff")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["previous_run_id"] == "qd_old"
    assert body["comparable"] is True
    assert body["scope"]["same_start_url"] is True
    elements = body["kinds"][DOM_ELEMENT]
    assert elements["added"] == 1
    assert elements["removed"] == 1
    assert "Checkout" in str(elements["added_keys"])
    assert "Search" in str(elements["removed_keys"])


async def test_a_run_whose_previous_run_captured_nothing_is_not_comparable(client, test_db_session):
    project_id = await _project(client)
    earlier = datetime(2026, 1, 1, tzinfo=UTC)
    await _run(test_db_session, project_id, "qd_blank", created_at=earlier)
    await _run(test_db_session, project_id, "qd_after", created_at=earlier + timedelta(hours=1))
    await _capture_state(test_db_session, "qd_after", project_id, controls=[_control("Add to cart")])

    body = (await client.get("/api/discovery/runs/qd_after/evidence/diff")).json()

    assert body["previous_run_id"] == "qd_blank"
    assert body["comparable"] is False
    assert body["reason"] == "previous_run_has_no_captured_evidence"
    assert body["kinds"] == {}


async def test_a_run_with_no_earlier_scope_says_so_instead_of_diffing_against_nothing(client, test_db_session):
    project_id = await _project(client)
    await _run(test_db_session, project_id, "qd_only")

    body = (await client.get("/api/discovery/runs/qd_only/evidence/diff")).json()

    assert body["comparable"] is False
    assert body["previous_run_id"] is None
    assert body["reason"] == "no_earlier_run_with_the_same_start_url"


async def test_another_projects_evidence_is_not_readable(client, role_client):
    await _project(client)

    async with role_client("QA_ENGINEER") as engineer:
        response = await engineer.get("/api/discovery/runs/qd_other/evidence")

    assert response.status_code in {403, 404}, response.text
