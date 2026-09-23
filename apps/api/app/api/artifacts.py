from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from project_model.models import ArtifactDownloadInfo, ArtifactUploadResponse

from app.services.artifact_storage_service import ArtifactStorageService

router = APIRouter(prefix="/artifacts", tags=["artifacts"])
artifact_service = ArtifactStorageService()


@router.post("/upload", response_model=ArtifactUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_artifact(file: UploadFile = File(...)) -> ArtifactUploadResponse:
    content = await file.read()
    filename = file.filename or "artifact.bin"
    content_type = file.content_type or "application/octet-stream"
    return await artifact_service.save_artifact(
        filename=filename,
        content=content,
        content_type=content_type,
    )


@router.get("/{artifact_id}/info", response_model=ArtifactDownloadInfo)
async def get_artifact_info(artifact_id: str) -> ArtifactDownloadInfo:
    info = await artifact_service.get_download_info(artifact_id)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return info


@router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str):
    res = await artifact_service.read_artifact_bytes(artifact_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    content, filename, content_type = res
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
