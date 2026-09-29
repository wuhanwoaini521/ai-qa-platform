"""Central authorization policy for the API surface.

Before this module existed, only three routers (`auth`, `users`, `teams`) resolved a caller at all
and `AuthService.check_permission` was never called, so every other route — including writes such as
`POST /api/failures/{id}/apply-repair` — was reachable without credentials. The policy is declared
here as one auditable table and enforced by a single application-level dependency, so adding a route
without a matching rule cannot silently create an open endpoint: the default rule requires
`project:read`/`project:write`, and ruleless prefixes fall back to authentication only.

The table is intentionally *resource*-scoped rather than per-endpoint. When a route needs finer
granularity (for example a future read-only share token), add an explicit `require_permission(...)`
dependency to that route instead of widening the table.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, WebSocketException, status
from project_model.models import ROLE_PERMISSIONS, Permission, User
from starlette.requests import HTTPConnection

from app.services.auth_service import AuthService

auth_service = AuthService()

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: Paths that must stay reachable without credentials: container probes, the metrics scrape target,
#: the login endpoint itself, and the interactive API docs.
PUBLIC_PATHS = (
    "/api/health",
    "/api/metrics",
    "/api/auth/login",
    "/docs",
    "/redoc",
    "/openapi.json",
)

#: Public prefixes that also match sub-paths (``/api/health/live``, ``/api/health/ready``).
PUBLIC_PREFIXES = ("/api/health",)

#: Routes whose client cannot send an Authorization header. The browser's EventSource API has no
#: header option, so the run-event stream accepts the same bearer token as an `access_token` query
#: parameter. Only the SSE and authenticated WebSocket endpoints use this mechanism.
QUERY_TOKEN_SUFFIXES = ("/events", "/stream")


@dataclass(frozen=True)
class Rule:
    """Permission required for `read` methods and for everything else (`write`) under `prefix`."""

    prefix: str
    read: Permission | None
    write: Permission | None


ANY_AUTHENTICATED: None = None

#: Most specific prefixes first; the first match wins.
RULES: tuple[Rule, ...] = (
    Rule("/api/auth/api-keys", Permission.SECURITY_ADMIN, Permission.SECURITY_ADMIN),
    Rule("/api/users", Permission.SECURITY_ADMIN, Permission.SECURITY_ADMIN),
    Rule("/api/teams", Permission.SECURITY_ADMIN, Permission.SECURITY_ADMIN),
    Rule("/api/audit", Permission.SECURITY_ADMIN, Permission.SECURITY_ADMIN),
    # Cluster infrastructure: any authenticated principal may register/heartbeat or work the queue.
    Rule("/api/workers", ANY_AUTHENTICATED, ANY_AUTHENTICATED),
    Rule("/api/jobs", ANY_AUTHENTICATED, ANY_AUTHENTICATED),
    Rule("/api/artifacts", Permission.PROJECT_READ, Permission.AUTOMATION_EDIT),
    Rule("/api/projects", Permission.PROJECT_READ, Permission.PROJECT_WRITE),
    Rule("/api/requirements", Permission.PROJECT_READ, Permission.REQUIREMENT_WRITE),
    Rule("/api/test-designs", Permission.PROJECT_READ, Permission.REQUIREMENT_WRITE),
    Rule("/api/test-cases", Permission.PROJECT_READ, Permission.TEST_CASE_WRITE),
    Rule("/api/workspaces", Permission.PROJECT_READ, Permission.AUTOMATION_EDIT),
    Rule("/api/recorder", Permission.AUTOMATION_EDIT, Permission.AUTOMATION_EDIT),
    Rule("/api/runs", Permission.PROJECT_READ, Permission.RUN_EXECUTE),
    Rule("/api/runners", Permission.PROJECT_READ, Permission.RUN_EXECUTE),
    # Repair flows mutate workspace code, so they require the automation-edit permission:
    # a VIEWER can read failures and proposals but can never apply one.
    Rule("/api/failures", Permission.PROJECT_READ, Permission.AUTOMATION_EDIT),
    Rule("/api/flaky", Permission.PROJECT_READ, Permission.PROJECT_READ),
    Rule("/api/quality", Permission.PROJECT_READ, Permission.PROJECT_READ),
    Rule("/api/releases", Permission.PROJECT_READ, Permission.RELEASE_GATE),
    Rule("/api/jira", Permission.PROJECT_READ, Permission.INTEGRATION_MANAGE),
    Rule("/api/testrail", Permission.PROJECT_READ, Permission.INTEGRATION_MANAGE),
    Rule("/api/ai", Permission.PROJECT_READ, Permission.PROJECT_READ),
    Rule("/api/qa-assistant", Permission.PROJECT_READ, Permission.PROJECT_READ),
    Rule("/api/dashboard", Permission.PROJECT_READ, Permission.PROJECT_READ),
    # Onboarding reads host paths outside the workspace; the two host-filesystem routes additionally
    # carry an explicit `require_permission(SECURITY_ADMIN)` guard (see api/onboarding.py).
    Rule("/api/onboarding", Permission.PROJECT_READ, Permission.AUTOMATION_EDIT),
)

#: Applied when no rule matches: reads stay open to authenticated users, writes are not.
DEFAULT_RULE = Rule("", Permission.PROJECT_READ, Permission.PROJECT_WRITE)


def allows_query_token(path: str) -> bool:
    """True for the small set of routes where a bearer token may arrive as a query parameter."""
    return (path.startswith("/api/runs/") or path.startswith("/api/recorder/")) and path.endswith(QUERY_TOKEN_SUFFIXES)


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix + "/") for prefix in PUBLIC_PREFIXES)


def required_permission(method: str, path: str) -> Permission | None:
    rule = next((r for r in RULES if path.startswith(r.prefix)), DEFAULT_RULE)
    return rule.read if method in READ_METHODS else rule.write


def has_permission(user: User, permission: Permission | None) -> bool:
    if permission is None:
        return True
    return permission in ROLE_PERMISSIONS.get(user.role, set())


async def get_current_user(request: Request) -> User:
    """Resolve the caller for the current request, reusing the identity resolved by `authorize_request`."""
    cached: User | None = getattr(request.state, "current_user", None)
    if cached is not None:
        return cached

    authorization = request.headers.get("authorization")
    if not authorization and allows_query_token(request.url.path):
        query_token = request.query_params.get("access_token")
        if query_token:
            authorization = f"Bearer {query_token}"

    user, _ = await auth_service.authenticate_token_or_key(authorization)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.current_user = user
    return user


async def authorize_request(request: HTTPConnection) -> None:
    """Application-level guard: authenticate every non-public request and enforce the policy table."""
    path = request.url.path
    if is_public_path(path):
        return

    authorization = request.headers.get("authorization")
    if not authorization and allows_query_token(path):
        query_token = request.query_params.get("access_token")
        if query_token:
            authorization = f"Bearer {query_token}"
    user, _ = await auth_service.authenticate_token_or_key(authorization)
    if not user:
        if request.scope["type"] == "websocket":
            raise WebSocketException(code=4401, reason="Invalid or missing authentication credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.current_user = user
    method = "GET" if request.scope["type"] == "websocket" else request.method
    permission = required_permission(method, path)
    if not has_permission(user, permission):
        if request.scope["type"] == "websocket":
            raise WebSocketException(code=4403, reason="Insufficient permission")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role {user.role.value} lacks permission {permission.value if permission else 'unknown'}",
        )


def require_permission(permission: Permission):
    """Per-route guard for endpoints that need finer granularity than the central policy table."""

    async def _guard(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {user.role.value} lacks permission {permission.value}",
            )
        return user

    return _guard
