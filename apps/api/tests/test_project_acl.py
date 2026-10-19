"""Project-scoped access control.

A role permission says which *features* a caller may use; it says nothing about which projects.
Before this guard any authenticated user who knew an id could read or mutate another team's runs,
failures, workspaces, requirements, cases, releases and discoveries. These tests pin the enforced
behaviour: owners and team members are scoped to their own projects, unrelated callers get 404
(never 403, so project existence cannot be probed), and administrators stay unrestricted so the
single-operator workflow is unchanged.
"""

from __future__ import annotations

import pytest
from app.persistence.models import FailureRecordORM as FailureRow
from app.persistence.models import ProjectORM, TeamMemberORM, TeamORM
from app.persistence.models import QualityDiscoveryRunORM as QualityDiscoveryRunRow
from app.persistence.models import TestExecutionORM as ExecutionRow
from app.persistence.models import TestRunORM as RunRow
from conftest import bearer_client, login_token
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PASSWORD = "pw-123456"


async def _create_user(admin: AsyncClient, email: str, role: str = "QA_ENGINEER") -> str:
    response = await admin.post(
        "/api/users",
        json={"email": email, "full_name": email.split("@")[0], "role": role, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_project(admin: AsyncClient, name: str) -> str:
    response = await admin.post("/api/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _as(admin: AsyncClient, email: str):
    return bearer_client(await login_token(admin, email, PASSWORD))


async def test_owner_sees_only_owned_projects(client: AsyncClient):
    owned = await _create_project(client, "ACL Owned")
    foreign = await _create_project(client, "ACL Foreign")
    email = "acl.owner@example.com"
    user_id = await _create_user(client, email)
    assert (await client.patch(f"/api/projects/{owned}", json={"owner_id": user_id})).status_code == 200

    async with await _as(client, email) as user:
        assert (await user.get(f"/api/projects/{owned}")).status_code == 200
        assert (await user.get(f"/api/projects/{foreign}")).status_code == 404
        listed = await user.get("/api/projects")
        assert listed.status_code == 200
        assert [p["id"] for p in listed.json()] == [owned]


async def test_team_membership_grants_access(client: AsyncClient, test_db_session):
    shared = await _create_project(client, "ACL Shared")
    email = "acl.member@example.com"
    user_id = await _create_user(client, email)
    async with test_db_session() as session:
        session.add(TeamORM(id="team_acl", name="ACL Team"))
        await session.flush()
        session.add(TeamMemberORM(id="tm_acl", team_id="team_acl", user_id=user_id))
        await session.commit()
    assert (await client.patch(f"/api/projects/{shared}", json={"team_id": "team_acl"})).status_code == 200

    async with await _as(client, email) as member:
        assert (await member.get(f"/api/projects/{shared}")).status_code == 200


async def test_foreign_project_resources_are_invisible(client: AsyncClient, test_db_session):
    foreign = await _create_project(client, "ACL Private")
    email = "acl.outsider@example.com"
    await _create_user(client, email)

    requirement = await client.post("/api/requirements", json={"project_id": foreign, "title": "secret requirement"})
    assert requirement.status_code == 201, requirement.text
    req_id = requirement.json()["id"]

    async with test_db_session() as session:
        session.add(RunRow(id="run_acl", project_id=foreign, workspace_id="ws_acl", status="PASSED"))
        await session.commit()

    # A failure needs a real failure id: asserting 404 for an id that does not exist at all would
    # pass whether or not the ACL guard is present.
    async with test_db_session() as session:
        session.add(ExecutionRow(id="exec_acl", run_id="run_acl", nodeid="tests/test_acl.py::test_secret"))
        session.add(
            FailureRow(
                id="fail_acl",
                run_id="run_acl",
                execution_id="exec_acl",
                test_nodeid="tests/test_acl.py::test_secret",
                test_name="test_secret",
            )
        )
        await session.commit()

    async with await _as(client, email) as outsider:
        assert (await outsider.get(f"/api/requirements/{req_id}")).status_code == 404
        assert (await outsider.get("/api/runs/run_acl")).status_code == 404
        assert (await outsider.post("/api/runs/run_acl/cancel")).status_code == 404
        assert (await outsider.get("/api/workspaces", params={"project_id": foreign})).status_code == 404
        assert (await outsider.get("/api/runs", params={"project_id": foreign})).status_code == 404
        assert (await outsider.get("/api/failures", params={"project_id": foreign})).status_code == 404
        assert (await outsider.get("/api/failures/fail_acl")).status_code == 404
        # Writes to a foreign project are refused as firmly as reads.
        assert (
            await outsider.post("/api/requirements", json={"project_id": foreign, "title": "injected"})
        ).status_code == 404
        assert (await outsider.get(f"/api/requirements/{req_id}")).status_code == 404


async def test_workspace_git_routes_are_project_scoped(client: AsyncClient, test_db_session):
    """The git/PR router shares the /workspaces/{id} prefix, so it needs the same guard.

    Without it any role holding AUTOMATION_EDIT (a plain QA_ENGINEER) could commit and push to a
    workspace belonging to another project.
    """
    foreign = await _create_project(client, "ACL Git Private")
    email = "acl.git.outsider@example.com"
    await _create_user(client, email)
    async with test_db_session() as session:
        session.add(RunRow(id="run_git", project_id=foreign, workspace_id="ws_git_acl", status="PASSED"))
        await session.commit()

    async with await _as(client, email) as outsider:
        assert (await outsider.get("/api/workspaces/ws_git_acl/git/status")).status_code == 404
        assert (await outsider.get("/api/workspaces/ws_git_acl/git/log")).status_code == 404
        assert (await outsider.post("/api/workspaces/ws_git_acl/git/push")).status_code == 404
        assert (
            await outsider.post("/api/workspaces/ws_git_acl/git/commit", json={"message": "injected"})
        ).status_code == 404
        # The owner of the project still reaches its own workspace routes.
    assert (await client.get("/api/workspaces/ws_git_acl/git/status")).status_code != 404


async def test_discovery_stream_ticket_is_project_scoped(client: AsyncClient, test_db_session):
    """A stream ticket must not become an existence oracle for other projects' discovery runs."""
    foreign = await _create_project(client, "ACL Discovery Private")
    email = "acl.ticket.outsider@example.com"
    await _create_user(client, email)
    async with test_db_session() as session:
        session.add(
            QualityDiscoveryRunRow(
                id="qd_acl",
                project_id=foreign,
                requested_by="acl_admin",
                mode="EXPLORE",
                start_url="https://example.test/",
                status="RUNNING",
            )
        )
        await session.commit()

    async with await _as(client, email) as outsider:
        denied = await outsider.post("/api/auth/stream-ticket", json={"kind": "discovery", "resource_id": "qd_acl"})
        assert denied.status_code == 404
    # The administrator (and any member) can still obtain the ticket.
    allowed = await client.post("/api/auth/stream-ticket", json={"kind": "discovery", "resource_id": "qd_acl"})
    assert allowed.status_code == 200


async def test_legacy_project_without_owner_is_admin_only(client: AsyncClient, test_db_session):
    legacy = await _create_project(client, "ACL Legacy")
    email = "acl.legacy@example.com"
    await _create_user(client, email)
    async with test_db_session() as session:
        orm = await session.get(ProjectORM, legacy)
        orm.owner_id = None
        orm.team_id = None
        await session.commit()

    async with await _as(client, email) as user:
        assert (await user.get(f"/api/projects/{legacy}")).status_code == 404
    assert (await client.get(f"/api/projects/{legacy}")).status_code == 200


async def test_non_admin_cannot_transfer_ownership(client: AsyncClient):
    project = await _create_project(client, "ACL No Transfer")
    owner_email = "acl.transfer.owner@example.com"
    owner_id = await _create_user(client, owner_email, role="QA_LEAD")
    victim_id = await _create_user(client, "acl.transfer.victim@example.com")
    assert (await client.patch(f"/api/projects/{project}", json={"owner_id": owner_id})).status_code == 200

    async with await _as(client, owner_email) as owner:
        renamed = await owner.patch(f"/api/projects/{project}", json={"name": "renamed by owner"})
        assert renamed.status_code == 200
        steal = await owner.patch(f"/api/projects/{project}", json={"owner_id": victim_id})
        assert steal.status_code == 403
        widen = await owner.patch(f"/api/projects/{project}", json={"team_id": "team_acl"})
        assert widen.status_code == 403


async def test_creator_becomes_owner(client: AsyncClient):
    project = await _create_project(client, "ACL Creator")
    body = (await client.get(f"/api/projects/{project}")).json()
    assert body["owner_id"], "a newly created project must record its creator so it is never orphaned"


async def test_artifact_access_is_project_scoped(client: AsyncClient):
    """An artifact has no project column before 0015, so any authenticated caller could fetch it."""
    from app.services.artifact_storage_service import ArtifactStorageService

    owned = await _create_project(client, "ACL Artifacts")
    foreign = await _create_project(client, "ACL Artifacts Foreign")
    email = "acl.artifact@example.com"
    user_id = await _create_user(client, email)
    assert (await client.patch(f"/api/projects/{owned}", json={"owner_id": user_id})).status_code == 200

    storage = ArtifactStorageService()
    owned_artifact = await storage.save_artifact(
        "owned.txt", b"evidence", "text/plain", project_id=owned, created_by=user_id
    )
    foreign_artifact = await storage.save_artifact(
        "foreign.txt", b"evidence", "text/plain", project_id=foreign, created_by=user_id
    )
    legacy_artifact = await storage.save_artifact("legacy.txt", b"evidence", "text/plain")

    async with await _as(client, email) as owner:
        assert (await owner.get(f"/api/artifacts/{owned_artifact.artifact_id}/info")).status_code == 200
        downloaded = await owner.get(f"/api/artifacts/{owned_artifact.artifact_id}/download")
        assert downloaded.status_code == 200 and downloaded.content == b"evidence"
        for artifact_id in (foreign_artifact.artifact_id, legacy_artifact.artifact_id):
            assert (await owner.get(f"/api/artifacts/{artifact_id}/info")).status_code == 404
            assert (await owner.get(f"/api/artifacts/{artifact_id}/download")).status_code == 404
        # Uploading into another project is refused, and an upload names its owner.
        assert (
            await owner.post(
                "/api/artifacts/upload",
                params={"project_id": foreign},
                files={"file": ("foreign.txt", b"x", "text/plain")},
            )
        ).status_code == 404
        uploaded = await owner.post(
            "/api/artifacts/upload",
            params={"project_id": owned},
            files={"file": ("owned.txt", b"y", "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        assert (await owner.get(f"/api/artifacts/{uploaded.json()['artifact_id']}/info")).status_code == 200

    # Administrators keep the unrestricted single-operator workflow, including legacy rows.
    for artifact in (owned_artifact, foreign_artifact, legacy_artifact):
        assert (await client.get(f"/api/artifacts/{artifact.artifact_id}/info")).status_code == 200
