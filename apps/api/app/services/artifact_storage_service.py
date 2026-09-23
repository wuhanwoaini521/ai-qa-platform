from __future__ import annotations

import os
from pathlib import Path

from project_model.models import ArtifactDownloadInfo, ArtifactUploadResponse

from app.repositories.artifact_repo import ArtifactRepository
from app.settings import settings


class ArtifactStorageService:
    """Local-filesystem artifact storage service.

    The ``storage_type`` value is persisted on the row, but only ``LOCAL`` is implemented:
    there is no S3/MinIO client in this codebase.
    """

    def __init__(
        self,
        artifact_repo: ArtifactRepository | None = None,
        base_dir: str | Path | None = None,
    ) -> None:
        self.artifact_repo = artifact_repo or ArtifactRepository()
        # Default to the configured artifact directory: the health probe checks that directory, so
        # writing anywhere else would let /health report writable for a location the API never uses.
        self.base_dir = Path(base_dir or settings.artifact_storage_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_artifact(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        storage_type: str = "LOCAL",
    ) -> ArtifactUploadResponse:
        file_path = self.base_dir / filename
        file_path.write_bytes(content)

        orm = await self.artifact_repo.create(
            filename=filename,
            size_bytes=len(content),
            content_type=content_type,
            storage_type=storage_type,
            storage_path=str(file_path),
        )

        return ArtifactUploadResponse(
            artifact_id=orm.id,
            filename=orm.filename,
            size_bytes=orm.size_bytes,
            content_type=orm.content_type,
            storage_type=orm.storage_type,
            storage_url=f"/api/artifacts/{orm.id}/download",
        )

    async def get_download_info(self, artifact_id: str) -> ArtifactDownloadInfo | None:
        orm = await self.artifact_repo.get_by_id(artifact_id)
        if not orm:
            return None

        return ArtifactDownloadInfo(
            artifact_id=orm.id,
            filename=orm.filename,
            download_url=f"/api/artifacts/{orm.id}/download",
            expires_in_seconds=3600,
        )

    async def read_artifact_bytes(self, artifact_id: str) -> tuple[bytes, str, str] | None:
        orm = await self.artifact_repo.get_by_id(artifact_id)
        if not orm:
            return None
        if os.path.exists(orm.storage_path):
            content = Path(orm.storage_path).read_bytes()
            return content, orm.filename, orm.content_type
        return None
