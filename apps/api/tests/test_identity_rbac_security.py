from __future__ import annotations

import uuid

import pytest
from app.main import app
from app.persistence.database import init_db
from app.repositories.api_key_repo import ApiKeyRepository
from app.repositories.team_repo import TeamRepository
from app.services.auth_service import AuthService
from app.services.secret_store import SecretStore
from httpx import ASGITransport, AsyncClient
from project_model.models import (
    ApiKeyCreate,
    Permission,
    TeamCreate,
    UserRole,
)


@pytest.mark.asyncio
async def test_identity_and_rbac_flow():
    await init_db()
    team_repo = TeamRepository()
    auth_service = AuthService()

    # Seed default users
    await auth_service.ensure_default_users()

    # 1. Verify default admin login
    login_res = await auth_service.login("admin@ai-qa.local", "adminpassword")
    assert login_res is not None
    assert login_res.user.role == UserRole.ADMIN
    assert Permission.SECURITY_ADMIN.value in login_res.permissions
    assert Permission.RELEASE_GATE.value in login_res.permissions

    # 2. Verify invalid login
    invalid_login = await auth_service.login("admin@ai-qa.local", "wrongpassword")
    assert invalid_login is None

    # 3. Create a team and add members
    team_name = f"Core QA Team {uuid.uuid4().hex[:6]}"
    team = await team_repo.create(TeamCreate(name=team_name, description="Core QA engineers"))
    assert team.name == team_name

    member = await team_repo.add_member(team.id, login_res.user.id, role="LEAD")
    assert member.role == "LEAD"
    assert member.team_id == team.id

    # 4. Create API Key
    api_key_repo = ApiKeyRepository()
    key_res = await api_key_repo.create(ApiKeyCreate(name="CI Bot Key", user_id=login_res.user.id, expires_at=None))
    assert key_res.raw_api_key.startswith("aqp_live_")
    assert key_res.key_prefix == key_res.raw_api_key[:12]

    # Authenticate via raw API key
    authed_user, perms = await auth_service.authenticate_token_or_key(f"Bearer {key_res.raw_api_key}")
    assert authed_user is not None
    assert authed_user.id == login_res.user.id
    assert Permission.SECURITY_ADMIN.value in perms


@pytest.mark.asyncio
async def test_secret_store():
    store = SecretStore(master_key="test-master-key-12345")
    secret = "ghp_secure_github_personal_token_987654321"

    encrypted = store.encrypt_secret(secret)
    assert encrypted.startswith("enc_")
    assert encrypted != secret

    decrypted = store.decrypt_secret(encrypted)
    assert decrypted == secret

    masked = store.mask_secret(secret)
    assert masked.startswith("ghp")
    assert masked.endswith("321")
    assert "***" in masked


@pytest.mark.asyncio
async def test_identity_and_audit_endpoints():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Login endpoint
        resp = await client.post(
            "/api/auth/login",
            json={"email": "admin@ai-qa.local", "password": "adminpassword"},
        )
        assert resp.status_code == 200
        data = resp.json()
        token = data["access_token"]
        assert token != ""
        assert data["user"]["email"] == "admin@ai-qa.local"

        headers = {"Authorization": f"Bearer {token}"}

        # 2. Get current profile
        me_resp = await client.get("/api/auth/me", headers=headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["user"]["role"] == "ADMIN"

        # 3. Create API Key via endpoint
        key_resp = await client.post(
            "/api/auth/api-keys",
            json={"name": "Test Key", "user_id": data["user"]["id"]},
            headers=headers,
        )
        assert key_resp.status_code == 200
        raw_key = key_resp.json()["raw_api_key"]
        assert raw_key.startswith("aqp_live_")

        # 4. List users
        users_resp = await client.get("/api/users", headers=headers)
        assert users_resp.status_code == 200
        assert len(users_resp.json()) >= 1

        # 5. Create new user with unique email
        unique_email = f"sarah_{uuid.uuid4().hex[:6]}@company.com"
        new_user_resp = await client.post(
            "/api/users",
            json={
                "email": unique_email,
                "full_name": "Sarah Connor",
                "role": "QA_ENGINEER",
                "password": "pass",
            },
            headers=headers,
        )
        assert new_user_resp.status_code == 201
        new_user_id = new_user_resp.json()["id"]

        # 6. Create team with unique name
        unique_team = f"Frontend QA Squad {uuid.uuid4().hex[:6]}"
        team_resp = await client.post(
            "/api/teams",
            json={"name": unique_team, "description": "UI test owners"},
            headers=headers,
        )
        assert team_resp.status_code == 201
        team_id = team_resp.json()["id"]

        # Add member to team
        add_m_resp = await client.post(
            f"/api/teams/{team_id}/members",
            json={"user_id": new_user_id, "role": "MEMBER"},
            headers=headers,
        )
        assert add_m_resp.status_code == 201

        # 7. Check Security Audit Logs
        audit_resp = await client.get("/api/audit/security", headers=headers)
        assert audit_resp.status_code == 200
        logs = audit_resp.json()
        assert len(logs) > 0
        actions = [log["action"] for log in logs]
        assert "LOGIN" in actions
        assert "USER_CREATE" in actions
