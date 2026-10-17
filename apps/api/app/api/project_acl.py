"""Project-level access control, layered on top of the role policy in ``authz.py``.

The role policy answers "may this role use this feature"; this module answers "may this caller
touch *this* project". Administrators keep unrestricted access, so the single-operator workflow is
unchanged. Every other role is limited to projects it owns or shares through one of its teams. A
project with neither owner nor team ("legacy") is admin-only until a security admin explicitly
claims it, which is why ownership is nullable and never back-filled silently.

Persistence lives in ``ProjectAccessService``/``ProjectAccessRepository``; this module only wires it
into FastAPI (routers must not own storage access, see tests/test_architecture_boundaries.py).

Enforcement happens in route dependencies, not in ``authorize_request``: that guard runs for every
request (health, metrics, workers) and has no database session.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from project_model.models import User

from app.api.authz import get_current_user
from app.container import open_project_access_service
from app.services.project_access_service import is_admin

__all__ = [
    "can_access_project",
    "case_access",
    "discovery_run_access",
    "enforce_project_access",
    "failure_access",
    "is_admin",
    "project_path_access",
    "project_query_access",
    "release_access",
    "requirement_access",
    "resource_path_access",
    "run_access",
    "visible_project_ids",
    "workspace_access",
]


def _not_found() -> HTTPException:
    # 404 rather than 403: a non-member must not be able to probe which project ids exist.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


async def visible_project_ids(user: User) -> set[str] | None:
    """Project ids this caller may access; ``None`` means every project (administrators)."""
    async with open_project_access_service() as service:
        return await service.visible_project_ids(user)


async def can_access_project(user: User, project_id: str | None) -> bool:
    async with open_project_access_service() as service:
        return await service.can_access(user, project_id)


async def enforce_project_access(user: User, project_id: str | None) -> None:
    if not await can_access_project(user, project_id):
        raise _not_found()


def project_path_access(param: str):
    """Guard for a route whose path parameter *is* a project id."""

    async def _guard(request: Request, user: User = Depends(get_current_user)):
        await enforce_project_access(user, request.path_params.get(param))

    return _guard


def project_query_access(param: str):
    """Guard for a route that scopes itself with a ``project_id`` query parameter.

    Absent parameter is allowed here; list endpoints that support an unscoped read filter their
    results through ``visible_project_ids`` instead.
    """

    async def _guard(request: Request, user: User = Depends(get_current_user)):
        project_id = request.query_params.get(param)
        if project_id:
            await enforce_project_access(user, project_id)

    return _guard


def resource_path_access(param: str, kind: str):
    """Guard for a route that addresses a resource by id; ``kind`` names the project resolver.

    Safe to attach to a whole router: routes that do not carry ``param`` are left alone, so a
    collection route must still scope itself (see the ``project_query_access`` guards).
    """

    async def _guard(request: Request, user: User = Depends(get_current_user)):
        resource_id = request.path_params.get(param)
        if not resource_id:
            return
        async with open_project_access_service() as service:
            project_id = await service.project_of(kind, resource_id)
        if project_id is None:
            if not is_admin(user):
                raise _not_found()
            return
        await enforce_project_access(user, project_id)

    return _guard


run_access = resource_path_access("run_id", "run")
failure_access = resource_path_access("failure_id", "failure")
workspace_access = resource_path_access("workspace_id", "workspace")
requirement_access = resource_path_access("req_id", "requirement")
case_access = resource_path_access("case_id", "case")
release_access = resource_path_access("release_id", "release")
discovery_run_access = resource_path_access("run_id", "discovery_run")
