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

import asyncio
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode

from fastapi import Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, WebSocketException, status
from project_model.models import ROLE_PERMISSIONS, Permission, User
from starlette.requests import HTTPConnection

from app.services.auth_service import AuthService

auth_service = AuthService()

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: Paths that must stay reachable without credentials: container probes, the metrics scrape target,
#: the login endpoint itself, and the interactive API docs.
PUBLIC_PATHS = (
    "/api/demo-shop/index.html",
    "/api/demo-shop/catalog.json",
    "/api/health",
    "/api/metrics",
    "/api/auth/login",
    "/docs",
    "/redoc",
    "/openapi.json",
)

#: Public prefixes that also match sub-paths (``/api/health/live``, ``/api/health/ready``).
PUBLIC_PREFIXES = ("/api/health",)

#: Stream routes protected by resource-scoped tickets or an ordinary Authorization header.
STREAM_ROUTE_SUFFIXES = ("/events", "/stream")


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
    Rule("/api/auth/stream-ticket", Permission.PROJECT_READ, Permission.PROJECT_READ),
    Rule("/api/users", Permission.SECURITY_ADMIN, Permission.SECURITY_ADMIN),
    Rule("/api/teams", Permission.SECURITY_ADMIN, Permission.SECURITY_ADMIN),
    Rule("/api/audit", Permission.SECURITY_ADMIN, Permission.SECURITY_ADMIN),
    # Workers can submit authoritative test results; their credentials are infrastructure secrets.
    Rule("/api/workers", Permission.PROJECT_READ, Permission.SECURITY_ADMIN),
    Rule("/api/jobs", Permission.PROJECT_READ, Permission.SECURITY_ADMIN),
    Rule("/api/artifacts", Permission.PROJECT_READ, Permission.AUTOMATION_EDIT),
    Rule("/api/projects", Permission.PROJECT_READ, Permission.PROJECT_WRITE),
    Rule("/api/requirements", Permission.PROJECT_READ, Permission.REQUIREMENT_WRITE),
    Rule("/api/test-designs", Permission.PROJECT_READ, Permission.REQUIREMENT_WRITE),
    Rule("/api/test-cases", Permission.PROJECT_READ, Permission.TEST_CASE_WRITE),
    Rule("/api/workspaces", Permission.PROJECT_READ, Permission.AUTOMATION_EDIT),
    Rule("/api/recorder", Permission.AUTOMATION_EDIT, Permission.AUTOMATION_EDIT),
    Rule("/api/debug", Permission.RUN_EXECUTE, Permission.RUN_EXECUTE),
    Rule("/api/decision", Permission.PROJECT_READ, Permission.SECURITY_ADMIN),
    Rule("/api/runs", Permission.PROJECT_READ, Permission.RUN_EXECUTE),
    # Agent tasks may propose and, after explicit approval, write workspace source.
    Rule("/api/tasks", Permission.PROJECT_READ, Permission.AUTOMATION_EDIT),
    Rule("/api/runners", Permission.PROJECT_READ, Permission.RUN_EXECUTE),
    # Repair flows mutate workspace code, so they require the automation-edit permission:
    # a VIEWER can read failures and proposals but can never apply one.
    Rule("/api/failures", Permission.PROJECT_READ, Permission.AUTOMATION_EDIT),
    Rule("/api/flaky", Permission.PROJECT_READ, Permission.PROJECT_READ),
    Rule("/api/quality", Permission.PROJECT_READ, Permission.PROJECT_READ),
    Rule("/api/discovery", Permission.PROJECT_READ, Permission.RUN_EXECUTE),
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


def is_stream_route(path: str) -> bool:
    """True only for routes whose short-lived stream credentials are accepted in headers/frames."""
    return (
        path.startswith("/api/runs/")
        or path.startswith("/api/recorder/")
        or path.startswith("/api/tasks/")
        or path.startswith("/api/debug/")
        or path.startswith("/api/workspaces/")
        and "/lsp/" in path
    ) and path.endswith(STREAM_ROUTE_SUFFIXES)


def stream_ticket_scope(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if not parts or parts[0] != "api":
        return None
    if len(parts) == 4 and parts[1] in {"runs", "tasks"}:
        family, resource_id, suffix = parts[1:]
        kind = {("runs", "events"): "run", ("tasks", "events"): "task"}.get((family, suffix))
    elif len(parts) == 5 and parts[1] in {"recorder", "debug"} and parts[2] == "sessions":
        family, resource_id, suffix = parts[1], parts[3], parts[4]
        kind = {("recorder", "stream"): "recorder", ("debug", "stream"): "debug"}.get((family, suffix))
    elif len(parts) == 5 and parts[1] == "workspaces" and parts[3:] == ["lsp", "stream"]:
        resource_id, kind = parts[2], "lsp"
    else:
        return None
    return f"{kind}:{resource_id}" if kind and resource_id else None


class StreamTicketQuerySanitizer:
    """Strip legacy query credentials before application and ASGI access logging."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] in {"http", "websocket"} and is_stream_route(scope.get("path", "")):
            query = scope.get("query_string", b"").decode("latin-1")
            items = parse_qsl(query, keep_blank_values=True)
            scope["query_string"] = urlencode(
                [(key, value) for key, value in items if key not in {"access_token", "stream_ticket"}]
            ).encode("latin-1")
        await self.app(scope, receive, send)


async def authenticate_stream_request(request: Request) -> User | None:
    """Authenticate a short-lived ticket from an Authorization header, never from the URL."""
    authorization = request.headers.get("authorization", "")
    parts = authorization.strip().split(" ")
    ticket = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else None
    return await auth_service.authenticate_stream_ticket(ticket, stream_ticket_scope(request.url.path))


async def authenticate_websocket_stream(websocket: WebSocket, expected_scope: str) -> User | None:
    """Authenticate a WebSocket using its first frame so credentials stay out of handshake URLs."""
    await websocket.accept()
    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
        await websocket.close(code=4401, reason="Stream authentication required")
        return None
    ticket = message.get("stream_ticket") if isinstance(message, dict) and message.get("type") == "auth" else None
    user = await auth_service.authenticate_stream_ticket(ticket, expected_scope)
    if user is None:
        await websocket.close(code=4401, reason="Invalid stream ticket")
    return user


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
    if is_stream_route(request.url.path):
        user = await authenticate_stream_request(request)
        if user is None:
            user, _ = await auth_service.authenticate_token_or_key(authorization)
    else:
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
    if is_stream_route(path):
        if request.scope["type"] == "websocket" and not authorization:
            # The route accepts the handshake, then authenticates its first frame before sending data.
            return
        user = await authenticate_stream_request(request)
        if user is None:
            user, _ = await auth_service.authenticate_token_or_key(authorization)
    else:
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
