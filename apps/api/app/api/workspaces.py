from fastapi import APIRouter, Depends, HTTPException, Query
from project_model.models import (
    FileContentPayload,
    FileNode,
    GitDiffResult,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.project_repo import ProjectRepository
from app.services.workspace_service import SecurityException, WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


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


@router.get("/{workspace_id}/diff", response_model=GitDiffResult)
async def get_workspace_diff(
    workspace_id: str,
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        return await service.get_diff(workspace_id)
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
