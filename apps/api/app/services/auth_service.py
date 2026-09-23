from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from project_model.models import (
    ROLE_PERMISSIONS,
    ApiKey,
    LoginResponse,
    Permission,
    User,
    UserCreate,
    UserRole,
)

from app.repositories.api_key_repo import ApiKeyRepository
from app.repositories.security_audit_repo import SecurityAuditRepository
from app.repositories.user_repo import UserRepository
from app.settings import TOKEN_TTL_SECONDS, settings


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository | None = None,
        api_key_repo: ApiKeyRepository | None = None,
        audit_repo: SecurityAuditRepository | None = None,
    ) -> None:
        self.user_repo = user_repo or UserRepository()
        self.api_key_repo = api_key_repo or ApiKeyRepository()
        self.audit_repo = audit_repo or SecurityAuditRepository()

    async def ensure_default_users(self) -> None:
        """Seed default admin, lead and engineer if they do not exist."""
        # Seed default Admin
        if not await self.user_repo.get_by_email("admin@ai-qa.local"):
            await self.user_repo.create(
                UserCreate(
                    email="admin@ai-qa.local",
                    full_name="Enterprise Admin",
                    role=UserRole.ADMIN,
                    password="adminpassword",
                )
            )
        # Seed default Lead
        if not await self.user_repo.get_by_email("lead@ai-qa.local"):
            await self.user_repo.create(
                UserCreate(
                    email="lead@ai-qa.local",
                    full_name="QA Lead",
                    role=UserRole.QA_LEAD,
                    password="password123",
                )
            )
        # Seed default Engineer
        if not await self.user_repo.get_by_email("engineer@ai-qa.local"):
            await self.user_repo.create(
                UserCreate(
                    email="engineer@ai-qa.local",
                    full_name="QA Engineer",
                    role=UserRole.QA_ENGINEER,
                    password="password123",
                )
            )

    async def login(self, email: str, password: str, ip_address: str = "127.0.0.1") -> LoginResponse | None:
        user = await self.user_repo.verify_password(email, password)
        if not user or not user.is_active:
            await self.audit_repo.log(
                action="LOGIN",
                actor_id=user.id if user else "anonymous",
                actor_email=email,
                target_resource="auth",
                status="DENIED",
                ip_address=ip_address,
                details={"reason": "Invalid credentials or inactive user"},
            )
            return None

        perms = [p.value for p in ROLE_PERMISSIONS.get(user.role, set())]
        token_str = self._issue_token(
            {
                "sub": user.id,
                "email": user.email,
                "role": user.role.value,
                "exp": int(time.time()) + TOKEN_TTL_SECONDS,
            }
        )

        await self.audit_repo.log(
            action="LOGIN",
            actor_id=user.id,
            actor_email=user.email,
            target_resource="auth",
            status="SUCCESS",
            ip_address=ip_address,
            details={"role": user.role.value},
        )

        return LoginResponse(
            access_token=token_str,
            token_type="bearer",
            user=user,
            permissions=sorted(perms),
        )

    def _issue_token(self, payload: dict) -> str:
        """Sign the session token: the payload is base64url-encoded and HMAC-SHA256 signed."""
        body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
        signature = hmac.new(settings.app_secret_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
        return f"{body}.{base64.urlsafe_b64encode(signature).decode('utf-8')}"

    def _decode_token(self, token: str) -> dict | None:
        """Verify signature and expiry. Returns the payload, or None if the token is not usable."""
        body, _, signature = token.partition(".")
        if not body or not signature:
            return None
        expected = hmac.new(settings.app_secret_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
        try:
            provided = base64.urlsafe_b64decode(signature.encode("utf-8"))
        except Exception:
            return None
        if not hmac.compare_digest(expected, provided):
            return None
        try:
            payload = json.loads(base64.urlsafe_b64decode(body.encode("utf-8")).decode("utf-8"))
        except Exception:
            return None
        expires_at = payload.get("exp")
        if isinstance(expires_at, int) and expires_at < int(time.time()):
            return None
        return payload

    async def authenticate_token_or_key(self, auth_header: str | None) -> tuple[User | None, list[str]]:
        if not auth_header:
            # Only reachable when AUTH_REQUIRED=false: development mode impersonates the seeded
            # administrator so a local run works without a login round-trip. In every other
            # configuration a missing header is an unauthenticated request.
            if settings.auth_required:
                return None, []
            admin = await self.user_repo.get_by_email("admin@ai-qa.local")
            if admin:
                perms = [p.value for p in ROLE_PERMISSIONS.get(admin.role, set())]
                return admin, sorted(perms)
            return None, []

        parts = auth_header.strip().split(" ")
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
            # 1. Check if token is raw API Key ("aqp_live_...")
            if token.startswith("aqp_live_"):
                api_key: ApiKey | None = await self.api_key_repo.get_by_raw_key(token)
                if api_key:
                    user = await self.user_repo.get_by_id(api_key.user_id)
                    if user and user.is_active:
                        perms = [p.value for p in ROLE_PERMISSIONS.get(user.role, set())]
                        return user, sorted(perms)
                return None, []

            # 2. Verify and decode the signed session token
            payload = self._decode_token(token)
            if payload:
                user_id = payload.get("sub")
                if user_id:
                    user = await self.user_repo.get_by_id(user_id)
                    if user and user.is_active:
                        perms = [p.value for p in ROLE_PERMISSIONS.get(user.role, set())]
                        return user, sorted(perms)

        # Check if direct email lookup or default user fallback
        return None, []

    def check_permission(self, user: User, permission: Permission) -> bool:
        allowed = ROLE_PERMISSIONS.get(user.role, set())
        return permission in allowed
