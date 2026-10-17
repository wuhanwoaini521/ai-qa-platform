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
from app.persistence.models import ProjectORM, TeamMemberORM, TeamORM
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

    requirement = await client.post(
        "/api/requirements", json={"project_id": foreign, "title": "secret requirement"}
    )
    assert requirement.status_code == 201, requirement.text
    req_id = requirement.json()["id"]

    async with test_db_session() as session:
        session.add(RunRow(id="run_acl", project_id=foreign, workspace_id="ws_acl", status="PASSED"))
        await session.commit()

    async with await _as(client, email) as outsider:
        assert (await outsider.get(f"/api/requirements/{req_id}")).status_code == 404
        assert (await outsider.get("/api/runs/run_acl")).status_code == 404
        assert (await outsider.post("/api/runs/run_acl/cancel")).status_code == 404
        assert (await outsider.get("/api/workspaces", params={"project_id": foreign})).status_code == 404
        assert (await outsider.get("/api/runs", params={"project_id": foreign})).status_code == 404
        assert (await outsider.get("/api/failures", params={"project_id": foreign})).status_code == 404
        assert (await outsider.get(f"/api/failures/{req_id}")).status_code == 404
        # Writes to a foreign project are refused as firmly as reads.
        assert (
            await outsider.post("/api/requirements", json={"project_id": foreign, "title": "injected"})
        ).status_code == 404
        assert (await outsider.get(f"/api/requirements/{req_id}")).status_code == 404


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
