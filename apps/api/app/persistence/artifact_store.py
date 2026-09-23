from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import aiofiles
import aiofiles.os
from app.settings import settings


@runtime_checkable
class ArtifactStore(Protocol):
    async def put_artifact(self, path: str, content: bytes) -> str: ...

    async def get_artifact(self, path: str) -> bytes | None: ...

    async def exists(self, path: str) -> bool: ...


class LocalArtifactStore(ArtifactStore):
    """Local file-system based artifact store."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = (base_dir or settings.artifact_storage_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, relative_path: str) -> Path:
        target = (self.base_dir / relative_path.lstrip("/")).resolve()
        if not str(target).startswith(str(self.base_dir)):
            raise ValueError("Artifact path traversal attempt detected.")
        return target

    async def put_artifact(self, path: str, content: bytes) -> str:
        target = self._resolve_safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "wb") as f:
            await f.write(content)
        return str(target)

    async def get_artifact(self, path: str) -> bytes | None:
        target = self._resolve_safe_path(path)
        if not target.is_file():
            return None
        async with aiofiles.open(target, "rb") as f:
            return await f.read()

    async def exists(self, path: str) -> bool:
        target = self._resolve_safe_path(path)
        return target.is_file()
