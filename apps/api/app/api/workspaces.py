import re
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from project_model.models import (
    Breakpoint,
    BreakpointUpsert,
    CollectionReport,
    CreateFilePayload,
    FileContentPayload,
    FileNode,
    GitDiffResult,
    RenameFilePayload,
    ValidationReport,
    Workspace,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.persistence.models import BreakpointORM, WorkspaceORM
from app.repositories.project_repo import ProjectRepository
from app.services.workspace_service import SecurityException, WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.get("", response_model=list[Workspace])
async def list_workspaces(
    project_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
) -> list[Workspace]:
    result = await session.execute(
        select(WorkspaceORM).where(WorkspaceORM.project_id == project_id).order_by(WorkspaceORM.created_at.desc())
    )
    # The existing workspace/file/run APIs use project_id as their workspace key. Return that
    # canonical key instead of exposing the unused internal WorkspaceORM row ID.
    return [
        Workspace(
            id=row.project_id,
            project_id=row.project_id,
            path=row.path,
            branch=row.branch,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in result.scalars().all()
    ]


def get_workspace_service() -> WorkspaceService:
    return WorkspaceService()


@router.get("/{workspace_id}/files", response_model=list[FileNode])
async def get_workspace_files(
    workspace_id: str,
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        return await service.get_file_tree(workspace_id)
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workspace_id}/breakpoints", response_model=list[Breakpoint])
async def list_breakpoints(
    workspace_id: str,
    session: AsyncSession = Depends(get_db),
) -> list[BreakpointORM]:
    result = await session.execute(
        select(BreakpointORM)
        .where(BreakpointORM.workspace_id == workspace_id)
        .order_by(BreakpointORM.file_path, BreakpointORM.line_number, BreakpointORM.source)
    )
    return list(result.scalars().all())


@router.put("/{workspace_id}/breakpoints", response_model=Breakpoint)
async def upsert_breakpoint(
    workspace_id: str,
    payload: BreakpointUpsert,
    session: AsyncSession = Depends(get_db),
) -> BreakpointORM:
    if payload.source != "manual":
        raise HTTPException(status_code=400, detail="Only auto failure analysis can create auto_failure breakpoints")
    file_path = payload.file_path.replace("\\", "/")
    path = PurePosixPath(file_path)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", file_path) or any(part in ("", ".", "..") for part in path.parts):
        raise HTTPException(status_code=400, detail="Breakpoint file_path must be a safe workspace-relative path")

    result = await session.execute(
        select(BreakpointORM).where(
            BreakpointORM.workspace_id == workspace_id,
            BreakpointORM.file_path == path.as_posix(),
            BreakpointORM.line_number == payload.line_number,
            BreakpointORM.source == "manual",
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = BreakpointORM(
            workspace_id=workspace_id,
            file_path=path.as_posix(),
            line_number=payload.line_number,
            enabled=payload.enabled,
            source="manual",
        )
        session.add(row)
    else:
        row.enabled = payload.enabled
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{workspace_id}/breakpoints/{breakpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_breakpoint(
    workspace_id: str,
    breakpoint_id: str,
    session: AsyncSession = Depends(get_db),
) -> Response:
    result = await session.execute(
        select(BreakpointORM).where(
            BreakpointORM.workspace_id == workspace_id,
            BreakpointORM.id == breakpoint_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Breakpoint not found")
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{workspace_id}/file")
async def read_workspace_file(
    workspace_id: str,
    path: str = Query(..., description="Relative file path"),
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        content = await service.read_file(workspace_id, path)
        return {"path": path, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{workspace_id}/file")
async def write_workspace_file(
    workspace_id: str,
    payload: FileContentPayload,
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        await service.write_file(workspace_id, payload.path, payload.content)
        return {"status": "saved", "path": payload.path}
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workspace_id}/files/create", status_code=status.HTTP_201_CREATED)
async def create_file_or_dir(
    workspace_id: str,
    payload: CreateFilePayload,
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        created_path = await service.create_file_or_dir(
            workspace_id, payload.path, is_directory=payload.is_directory, content=payload.content
        )
        return {"status": "created", "path": created_path}
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{workspace_id}/files/rename")
async def rename_file_or_dir(
    workspace_id: str,
    payload: RenameFilePayload,
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        await service.rename_path(workspace_id, payload.old_path, payload.new_path)
        return {"status": "renamed", "old_path": payload.old_path, "new_path": payload.new_path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{workspace_id}/files/delete")
async def delete_file_or_dir(
    workspace_id: str,
    path: str = Query(..., description="Relative path to delete"),
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        await service.delete_path(workspace_id, path)
        return {"status": "deleted", "path": path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workspace_id}/diff", response_model=GitDiffResult)
async def get_workspace_diff(
    workspace_id: str,
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        return await service.get_diff(workspace_id)
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workspace_id}/commit")
async def commit_workspace_changes(
    workspace_id: str,
    message: str = Query(..., min_length=1, description="Commit message"),
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        out = await service.commit_changes(workspace_id, message)
        return {"status": "committed", "output": out}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workspace_id}/validate", response_model=ValidationReport)
async def validate_workspace(
    workspace_id: str,
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        return await service.validate_workspace(workspace_id)
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workspace_id}/collect", response_model=CollectionReport)
async def collect_workspace_tests(
    workspace_id: str,
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        return await service.collect_tests(workspace_id)
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workspace_id}/bootstrap")
async def bootstrap_workspace(
    workspace_id: str,
    session: AsyncSession = Depends(get_db),
    service: WorkspaceService = Depends(get_workspace_service),
):
    proj_repo = ProjectRepository(session)
    project = await proj_repo.get_by_id(workspace_id)
    proj_name = project.name if project else "Automation Project"

    try:
        await service.initialize_workspace(workspace_id, proj_name)
        return {"status": "initialized", "workspace_id": workspace_id}
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))
