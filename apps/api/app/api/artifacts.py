from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from project_model.models import ArtifactDownloadInfo, ArtifactUploadResponse, User

from app.api.authz import get_current_user
from app.api.project_acl import enforce_project_access, enforce_resource_access
from app.services.artifact_storage_service import ArtifactStorageService

router = APIRouter(prefix="/artifacts", tags=["artifacts"])
artifact_service = ArtifactStorageService()


@router.post("/upload", response_model=ArtifactUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_artifact(
    file: UploadFile = File(...),
    project_id: str | None = Query(default=None, max_length=36),
    user: User = Depends(get_current_user),
) -> ArtifactUploadResponse:
    if project_id:
        await enforce_project_access(user, project_id)
    content = await file.read()
    filename = file.filename or "artifact.bin"
    content_type = file.content_type or "application/octet-stream"
    return await artifact_service.save_artifact(
        filename=filename,
        content=content,
        content_type=content_type,
        project_id=project_id,
        created_by=str(user.id),
    )


@router.get("/{artifact_id}/info", response_model=ArtifactDownloadInfo)
async def get_artifact_info(artifact_id: str, user: User = Depends(get_current_user)) -> ArtifactDownloadInfo:
    # Project-scoped like every other resource: an artifact without a project (a manual upload or a
    # row predating the ownership column) stays admin-only rather than being world-readable.
    await enforce_resource_access(user, "artifact", artifact_id)
    info = await artifact_service.get_download_info(artifact_id)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return info


@router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str, user: User = Depends(get_current_user)):
    await enforce_resource_access(user, "artifact", artifact_id)
    res = await artifact_service.read_artifact_bytes(artifact_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    content, filename, content_type = res
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
