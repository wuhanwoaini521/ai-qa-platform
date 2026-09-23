"""Onboarding a real pytest project end to end: preview, import, collect, pilot-run, Allure import.

Uses a self-contained fixture repository on disk (no network, no browser) so the whole flow is
deterministic. The browser-driving test in the fixture exists to prove the safety policy refuses to
execute it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def build_reference_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        """
[project]
name = "sample-qa"
requires-python = ">=3.11"
dependencies = ["pytest>=8.0", "pytest-xdist>=3.5", "allure-pytest>=2.13"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["smoke: fast subset", "slow: external"]
""".lstrip(),
        encoding="utf-8",
    )
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "test_sample.py").write_text(
        """
import pytest


@pytest.mark.smoke
@pytest.mark.testrail("C1001")
def test_offline_math():
    assert 2 + 2 == 4


def test_offline_regression():
    assert 1 == 2


@pytest.mark.smoke
def test_c2002_marked_smoke():
    assert True


@pytest.mark.smoke
def test_requires_a_browser(page):
    page.goto("https://example.com")
""".lstrip(),
        encoding="utf-8",
    )
    (root / "pages").mkdir(exist_ok=True)
    (root / "pages" / "login_page.py").write_text("class LoginPage:\n    pass\n", encoding="utf-8")
    (root / ".git").mkdir(exist_ok=True)
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (root / "allure-results").mkdir(exist_ok=True)
    (root / "allure-results" / "sample-result.json").write_text(
        json.dumps(
            {
                "uuid": "sample",
                "historyId": "h1",
                "fullName": "tests.test_sample.test_offline_math",
                "name": "test_offline_math",
                "status": "passed",
                "start": 10,
                "stop": 30,
                "labels": [{"name": "suite", "value": "sample"}],
            }
        ),
        encoding="utf-8",
    )
    return root


async def test_onboarding_flow_from_preview_to_pilot_run(client: AsyncClient, tmp_path: Path):
    source = build_reference_repo(tmp_path / "reference-repo")
    untouched = {path: path.stat().st_mtime_ns for path in source.rglob("*") if path.is_file()}

    preview = await client.post("/api/onboarding/preview", json={"source_path": str(source)})
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["detection"]["contract"]["framework"] == "pytest"
    assert preview_body["detection"]["contract"]["test_roots"] == ["tests"]
    assert preview_body["detection"]["contract"]["pages_dir"] == "pages"
    assert ".git" in preview_body["plan"]["excluded_dirs"]
    assert preview_body["plan"]["included_files"] >= 3

    imported = await client.post(
        "/api/onboarding/import", json={"source_path": str(source), "project_name": "Sample QA"}
    )
    assert imported.status_code == 201, imported.text
    imported_body = imported.json()
    project_id = imported_body["project_id"]
    workspace_path = Path(imported_body["workspace_path"])
    assert workspace_path.is_dir()
    assert (workspace_path / "tests" / "test_sample.py").exists()
    assert not (workspace_path / ".git").exists()
    assert (workspace_path / ".qa-platform.yaml").exists()

    # The reference repository is read-only throughout.
    assert {path: path.stat().st_mtime_ns for path in source.rglob("*") if path.is_file()} == untouched

    collected = await client.post(f"/api/onboarding/{project_id}/collect")
    assert collected.status_code == 200, collected.text
    collected_body = collected.json()
    assert collected_body["outcome"]["status"] == "COLLECTED"
    nodeids = [test["nodeid"] for test in collected_body["outcome"]["tests"]]
    assert "tests/test_sample.py::test_offline_math" in nodeids
    assert collected_body["identity_summary"]["logical_tests"] == 4

    run = await client.post(
        f"/api/onboarding/{project_id}/run",
        json={
            "nodeids": [
                "tests/test_sample.py::test_offline_math",
                "tests/test_sample.py::test_offline_regression",
                "tests/test_sample.py::test_requires_a_browser",
            ]
        },
    )
    assert run.status_code == 200, run.text
    run_body = run.json()

    # The browser test is refused by the safety policy, the two offline tests execute.
    assert run_body["executed_nodeids"] == [
        "tests/test_sample.py::test_offline_math",
        "tests/test_sample.py::test_offline_regression",
    ]
    rejected = {verdict["nodeid"]: verdict for verdict in run_body["rejected"]}
    assert "tests/test_sample.py::test_requires_a_browser" in rejected
    assert any("page" in reason for reason in rejected["tests/test_sample.py::test_requires_a_browser"]["reasons"])

    statuses = {test["nodeid"]: test["status"] for test in run_body["outcome"]["logical_tests"]}
    assert statuses == {
        "tests/test_sample.py::test_offline_math": "PASSED",
        "tests/test_sample.py::test_offline_regression": "FAILED",
    }
    assert run_body["run_id"]

    # The failing test becomes a platform failure record with a real classification.
    failures = await client.get(f"/api/failures?project_id={project_id}")
    assert failures.status_code == 200
    failure_records = failures.json()
    assert len(failure_records) == 1
    assert failure_records[0]["test_nodeid"] == "tests/test_sample.py::test_offline_regression"
    assert failure_records[0]["classification"] in {"ASSERTION_FAILURE", "LOGIC_ERROR", "UNKNOWN"}

    # No Allure results exist yet: the import says so instead of pretending there is nothing to do.
    allure = await client.post(f"/api/onboarding/{project_id}/allure")
    assert allure.status_code == 400
    assert "No Allure results directory" in allure.json()["detail"]

    # Once the run has produced results, they are imported with their identity intact.
    results_dir = workspace_path / "allure-results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "run-result.json").write_text(
        json.dumps(
            {
                "uuid": "run-1",
                "historyId": "h-run",
                "fullName": "tests.test_sample.test_offline_math",
                "name": "test_offline_math",
                "status": "passed",
                "start": 100,
                "stop": 160,
                "labels": [{"name": "suite", "value": "smoke"}],
            }
        ),
        encoding="utf-8",
    )
    allure = await client.post(f"/api/onboarding/{project_id}/allure")
    assert allure.status_code == 200, allure.text
    allure_body = allure.json()
    assert allure_body["total"] == 1
    assert allure_body["by_status"] == {"PASSED": 1}
    assert allure_body["results"][0]["duration_ms"] == 60


async def test_allow_unsafe_execution_is_explicit_and_recorded(client: AsyncClient, tmp_path: Path):
    source = build_reference_repo(tmp_path / "reference-repo")
    imported = await client.post("/api/onboarding/import", json={"source_path": str(source)})
    project_id = imported.json()["project_id"]

    refused = await client.post(
        f"/api/onboarding/{project_id}/run",
        json={"nodeids": ["tests/test_sample.py::test_requires_a_browser"]},
    )
    assert refused.json()["executed_nodeids"] == []
    assert refused.json()["rejected"]


async def test_marker_selection_collects_first_and_still_applies_the_safety_policy(client: AsyncClient, tmp_path: Path):
    source = build_reference_repo(tmp_path / "reference-repo")
    imported = await client.post("/api/onboarding/import", json={"source_path": str(source)})
    project_id = imported.json()["project_id"]

    run = await client.post(f"/api/onboarding/{project_id}/run", json={"markers": ["smoke"]})
    assert run.status_code == 200, run.text
    body = run.json()

    assert set(body["executed_nodeids"]) == {
        "tests/test_sample.py::test_offline_math",
        "tests/test_sample.py::test_c2002_marked_smoke",
    }
    assert [verdict["nodeid"] for verdict in body["rejected"]] == ["tests/test_sample.py::test_requires_a_browser"]


async def test_importing_a_host_path_requires_the_security_permission(client: AsyncClient, role_client, tmp_path: Path):
    source = build_reference_repo(tmp_path / "reference-repo")

    async with role_client("QA_ENGINEER") as engineer:
        denied = await engineer.post("/api/onboarding/preview", json={"source_path": str(source)})
        assert denied.status_code == 403, denied.text


async def test_importing_a_missing_path_is_a_clear_client_error(client: AsyncClient, tmp_path: Path):
    response = await client.post("/api/onboarding/preview", json={"source_path": str(tmp_path / "nope")})

    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


@pytest.mark.security
@pytest.mark.parametrize(
    "malicious_nodeid",
    [
        "--pyargs=os",
        "-p evil_plugin",
        "--collect-only",
        "tests/test_sample.py::test_offline_math; rm -rf /tmp/x",
        "--rootdir=/",
        "tests/../../etc/passwd.py::test_x",
    ],
)
async def test_test_selection_cannot_inject_pytest_flags_or_shell(
    client: AsyncClient, tmp_path: Path, malicious_nodeid: str
):
    """node ids and markers reach the pytest command line, so they are validated, never trusted."""
    source = build_reference_repo(tmp_path / "reference-repo")
    imported = await client.post("/api/onboarding/import", json={"source_path": str(source)})
    project_id = imported.json()["project_id"]

    response = await client.post(f"/api/onboarding/{project_id}/run", json={"nodeids": [malicious_nodeid]})

    assert response.status_code == 400
    assert "invalid test selection" in response.json()["detail"]


@pytest.mark.security
async def test_marker_expression_cannot_inject_flags(client: AsyncClient, tmp_path: Path):
    source = build_reference_repo(tmp_path / "reference-repo")
    imported = await client.post("/api/onboarding/import", json={"source_path": str(source)})
    project_id = imported.json()["project_id"]

    response = await client.post(f"/api/onboarding/{project_id}/run", json={"markers": ["smoke --alluredir=/tmp/evil"]})

    assert response.status_code == 400
    assert "invalid marker expression" in response.json()["detail"]


@pytest.mark.security
@pytest.mark.parametrize(
    "absolute_nodeid_tail",
    ["/tmp/test_outside.py::test_outside", "/etc/test_probe.py::test_probe"],
)
async def test_absolute_node_ids_cannot_reach_host_files(
    client: AsyncClient, tmp_path: Path, absolute_nodeid_tail: str
):
    """A selection must stay inside the imported workspace, whatever path shape it uses."""
    source = build_reference_repo(tmp_path / "reference-repo")
    imported = await client.post("/api/onboarding/import", json={"source_path": str(source)})
    project_id = imported.json()["project_id"]

    response = await client.post(f"/api/onboarding/{project_id}/run", json={"nodeids": [absolute_nodeid_tail]})

    assert response.status_code == 400
    assert "invalid test selection" in response.json()["detail"]


@pytest.mark.security
async def test_runner_options_are_named_not_raw_flags(client: AsyncClient, tmp_path: Path):
    """The operator selects workers/retries by name; arbitrary pytest flags are not accepted."""
    source = build_reference_repo(tmp_path / "reference-repo")
    imported = await client.post("/api/onboarding/import", json={"source_path": str(source)})
    project_id = imported.json()["project_id"]

    rejected = await client.post(
        f"/api/onboarding/{project_id}/run",
        json={
            "nodeids": ["tests/test_sample.py::test_offline_math"],
            "extra_args": ["--junitxml=/tmp/qa_probe.xml"],
        },
    )
    # The field no longer exists, and an unknown field must not silently reach the command line.
    assert rejected.status_code == 200, rejected.text
    assert "--junitxml" not in rejected.json()["outcome"]["command"]

    accepted = await client.post(
        f"/api/onboarding/{project_id}/run",
        json={"nodeids": ["tests/test_sample.py::test_offline_math"], "n_workers": 2, "reruns": 1},
    )
    command = accepted.json()["outcome"]["command"]
    assert "-n" in command and "2" in command
    assert "--reruns" in command
