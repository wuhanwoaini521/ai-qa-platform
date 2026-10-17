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

from app.api.project_acl import project_query_access, workspace_access
from app.api.workspace_dependencies import get_workspace_catalog_service
from app.services.workspace_catalog_service import WorkspaceCatalogService
from app.services.workspace_service import SecurityException, WorkspaceService

router = APIRouter(
    prefix="/workspaces",
    tags=["Workspaces"],
    dependencies=[Depends(workspace_access), Depends(project_query_access("project_id"))],
)


@router.get("", response_model=list[Workspace])
async def list_workspaces(
    project_id: str = Query(...),
    catalog: WorkspaceCatalogService = Depends(get_workspace_catalog_service),
) -> list[Workspace]:
    return await catalog.list_workspaces(project_id)


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
    catalog: WorkspaceCatalogService = Depends(get_workspace_catalog_service),
) -> list[Breakpoint]:
    return await catalog.list_breakpoints(workspace_id)


@router.put("/{workspace_id}/breakpoints", response_model=Breakpoint)
async def upsert_breakpoint(
    workspace_id: str,
    payload: BreakpointUpsert,
    catalog: WorkspaceCatalogService = Depends(get_workspace_catalog_service),
) -> Breakpoint:
    try:
        return await catalog.upsert_manual_breakpoint(workspace_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/{workspace_id}/breakpoints/{breakpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_breakpoint(
    workspace_id: str,
    breakpoint_id: str,
    catalog: WorkspaceCatalogService = Depends(get_workspace_catalog_service),
) -> Response:
    if not await catalog.delete_breakpoint(workspace_id, breakpoint_id):
        raise HTTPException(status_code=404, detail="Breakpoint not found")
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
    catalog: WorkspaceCatalogService = Depends(get_workspace_catalog_service),
    service: WorkspaceService = Depends(get_workspace_service),
):
    proj_name = await catalog.project_name_for_workspace(workspace_id)

    try:
        await service.initialize_workspace(workspace_id, proj_name)
        return {"status": "initialized", "workspace_id": workspace_id}
    except SecurityException as e:
        raise HTTPException(status_code=400, detail=str(e))
