"""Route authorization: authentication, role enforcement and denial paths.

Before Phase 13.5 only three routers resolved a caller, `AuthService.check_permission` was never
called, and a missing `Authorization` header silently authenticated the request as the seeded
administrator — so every write endpoint was open. These tests pin the enforced behaviour:

* the health probes and `/api/auth/login` stay public;
* every other route answers 401 without credentials, including with a malformed token;
* roles are enforced per resource (a VIEWER can read but can never mutate);
* a denied write does not mutate anything.
"""

from __future__ import annotations

import pytest
from app.api.authz import required_permission
from conftest import ROLE_CREDENTIALS, login_token
from httpx import AsyncClient
from project_model.models import ROLE_PERMISSIONS, Permission, UserRole

pytestmark = pytest.mark.integration

PUBLIC_PATHS = ("/api/health/live", "/api/health/ready", "/api/health", "/api/metrics")

#: (method, path) that must require credentials. Paths are illustrative: the guard runs before the
#: handler, so a non-existent id must still be rejected as unauthenticated/forbidden.
PROTECTED_ROUTES = (
    ("GET", "/api/projects"),
    ("POST", "/api/projects"),
    ("GET", "/api/requirements"),
    ("POST", "/api/requirements"),
    ("GET", "/api/test-cases"),
    ("POST", "/api/test-cases"),
    ("GET", "/api/workspaces/unknown/files"),
    ("PUT", "/api/workspaces/unknown/file"),
    ("GET", "/api/runs"),
    ("POST", "/api/runs"),
    ("POST", "/api/runs/unknown/cancel"),
    ("GET", "/api/failures"),
    ("POST", "/api/failures/unknown/apply-repair"),
    ("GET", "/api/flaky"),
    ("GET", "/api/quality/coverage"),
    ("POST", "/api/releases"),
    ("POST", "/api/releases/unknown/gate-evaluate"),
    ("GET", "/api/audit/security"),
    ("GET", "/api/workers"),
    ("POST", "/api/workers"),
    ("GET", "/api/jobs"),
    ("POST", "/api/jobs/claim"),
    ("POST", "/api/users"),
    ("GET", "/api/teams"),
    ("POST", "/api/auth/api-keys"),
)


@pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
async def test_route_without_credentials_is_rejected(anonymous_client: AsyncClient, method: str, path: str):
    response = await anonymous_client.request(method, path, json={})
    assert response.status_code == 401, f"{method} {path} -> {response.status_code} {response.text}"


@pytest.mark.parametrize("path", PUBLIC_PATHS)
async def test_public_probe_paths_stay_open(anonymous_client: AsyncClient, path: str):
    response = await anonymous_client.get(path)
    assert response.status_code == 200, f"{path} -> {response.status_code} {response.text}"


async def test_login_endpoint_is_public(anonymous_client: AsyncClient):
    response = await anonymous_client.post(
        "/api/auth/login", json={"email": "admin@ai-qa.local", "password": "adminpassword"}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_malformed_token_is_rejected(anonymous_client: AsyncClient):
    anonymous_client.headers["Authorization"] = "Bearer not-a-real-token"
    response = await anonymous_client.get("/api/projects")
    assert response.status_code == 401


VIEWER_CREDENTIALS = ("rbac.viewer@example.com", "viewer-password-123")


async def test_viewer_can_read_but_never_mutate(client: AsyncClient, credentials_client):
    created = await client.post("/api/projects", json={"name": "RBAC Viewer Target"})
    assert created.status_code == 201
    project_id = created.json()["id"]

    viewer_user = await client.post(
        "/api/users",
        json={
            "email": VIEWER_CREDENTIALS[0],
            "full_name": "RBAC Viewer",
            "role": "VIEWER",
            "password": VIEWER_CREDENTIALS[1],
        },
    )
    assert viewer_user.status_code == 201, viewer_user.text

    async with credentials_client(*VIEWER_CREDENTIALS) as viewer:
        assert (await viewer.get("/api/projects")).status_code == 200
        assert (await viewer.get(f"/api/projects/{project_id}")).status_code == 200

        denied = {
            "create project": await viewer.post("/api/projects", json={"name": "nope"}),
            "patch project": await viewer.patch(f"/api/projects/{project_id}", json={"name": "nope"}),
            "create test case": await viewer.post("/api/test-cases", json={"project_id": project_id, "title": "nope"}),
            "write workspace file": await viewer.put(
                f"/api/workspaces/{project_id}/file", json={"path": "a.py", "content": "x"}
            ),
            "trigger run": await viewer.post("/api/runs", json={"project_id": project_id}),
            "apply repair": await viewer.post("/api/failures/unknown/apply-repair", json={}),
            "evaluate gate": await viewer.post("/api/releases/unknown/gate-evaluate"),
            "import jira": await viewer.post("/api/jira/import", json={"issue_keys": []}),
            "list users": await viewer.get("/api/users"),
            "security audit": await viewer.get("/api/audit/security"),
        }
        for label, response in denied.items():
            assert response.status_code == 403, f"{label} -> {response.status_code} {response.text}"

    # A denied write must not have changed anything.
    listing = await client.get("/api/projects")
    assert [p["id"] for p in listing.json()] == [project_id]


async def test_engineer_may_author_but_not_gate_or_administer(client: AsyncClient, role_client):
    project = await client.post("/api/projects", json={"name": "RBAC Engineer Target"})
    project_id = project.json()["id"]

    async with role_client("QA_ENGINEER") as engineer:
        test_case = await engineer.post(
            "/api/test-cases", json={"project_id": project_id, "title": "Engineer authored"}
        )
        assert test_case.status_code == 201, test_case.text

        assert (
            await engineer.post("/api/releases", json={"project_id": project_id, "version": "1.0"})
        ).status_code == 403
        assert (await engineer.post("/api/users", json={"email": "x@y.z", "full_name": "X"})).status_code == 403
        assert (await engineer.get("/api/audit/security")).status_code == 403


async def test_lead_may_gate_but_not_administer(client: AsyncClient, role_client):
    project = await client.post("/api/projects", json={"name": "RBAC Lead Target"})
    project_id = project.json()["id"]

    async with role_client("QA_LEAD") as lead:
        created = await lead.post(
            "/api/releases", json={"project_id": project_id, "version": "1.0.0", "name": "Lead release"}
        )
        assert created.status_code == 201, created.text
        release_id = created.json()["id"]

        gate = await lead.post(f"/api/releases/{release_id}/gate-evaluate")
        assert gate.status_code == 200, gate.text

        assert (await lead.get("/api/users")).status_code == 403
        assert (await lead.post("/api/projects", json={"name": "lead project"})).status_code == 201


def test_policy_table_covers_every_privileged_route_family():
    """Guard against a route family being added without a policy entry (it would fall to the default)."""
    expectations = {
        ("POST", "/api/failures/x/apply-repair"): Permission.AUTOMATION_EDIT,
        ("POST", "/api/releases/x/gate-evaluate"): Permission.RELEASE_GATE,
        ("POST", "/api/runs"): Permission.RUN_EXECUTE,
        ("POST", "/api/workspaces/x/file"): Permission.AUTOMATION_EDIT,
        ("POST", "/api/jira/import"): Permission.INTEGRATION_MANAGE,
        ("POST", "/api/users"): Permission.SECURITY_ADMIN,
        ("GET", "/api/projects"): Permission.PROJECT_READ,
        ("POST", "/api/workers"): None,
        ("POST", "/api/jobs/claim"): None,
    }
    for (method, path), expected in expectations.items():
        assert required_permission(method, path) == expected, f"{method} {path}"

    # An unknown route falls back to the default rule rather than to "no authentication".
    assert required_permission("GET", "/api/unknown-resource") == Permission.PROJECT_READ
    assert required_permission("POST", "/api/unknown-resource") == Permission.PROJECT_WRITE

    # Roles must not accidentally widen: only ADMIN may administer security.
    admin_permissions = {p.value for p in ROLE_PERMISSIONS[UserRole.ADMIN]}
    for role in (UserRole.QA_LEAD, UserRole.QA_ENGINEER, UserRole.VIEWER):
        role_permissions = {p.value for p in ROLE_PERMISSIONS[role]}
        assert Permission.SECURITY_ADMIN.value not in role_permissions, role
        assert role_permissions < admin_permissions, role
    assert Permission.RELEASE_GATE not in ROLE_PERMISSIONS[UserRole.QA_ENGINEER]
    assert Permission.RELEASE_GATE not in ROLE_PERMISSIONS[UserRole.VIEWER]
    assert Permission.AUTOMATION_EDIT not in ROLE_PERMISSIONS[UserRole.VIEWER]


async def test_run_event_stream_accepts_the_token_as_a_query_parameter(
    client: AsyncClient, anonymous_client: AsyncClient
):
    """The browser's EventSource cannot send headers, so this one route reads the token from the URL."""
    project = await client.post("/api/projects", json={"name": "SSE Authorization"})
    run = await client.post(
        "/api/runs", json={"project_id": project.json()["id"], "workspace_id": project.json()["id"]}
    )
    run_id = run.json()["id"]

    # No credential at all is still rejected.
    denied = await anonymous_client.get(f"/api/runs/{run_id}/events")
    assert denied.status_code == 401

    # A query token on any other route is not accepted.
    other = await anonymous_client.get(f"/api/runs/{run_id}?access_token={'x' * 10}")
    assert other.status_code == 401

    # With a valid query token the stream opens and delivers its first event.
    token = await login_token(client, *ROLE_CREDENTIALS["ADMIN"])
    async with client.stream("GET", f"/api/runs/{run_id}/events?access_token={token}") as stream:
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        first_line = ""
        async for line in stream.aiter_lines():
            if line.startswith("data:"):
                first_line = line
                break
    assert '"type": "CONNECTED"' in first_line
