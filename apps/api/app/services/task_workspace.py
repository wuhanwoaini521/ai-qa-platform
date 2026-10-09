from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from app.services.workspace_service import SecurityException, WorkspaceService


def workspace_source_snapshot(workspace_id: str | None) -> dict[str, str]:
    if not workspace_id:
        return {}
    workspace = WorkspaceService()
    root = workspace.get_workspace_dir(workspace_id)
    snapshot: dict[str, str] = {}
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = [
            name
            for name in names
            if name
            not in {
                ".git",
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
                ".mypy_cache",
                ".venv",
                "venv",
                "node_modules",
                "dist",
                "build",
                "coverage",
                ".cache",
                "runtime",
                "artifacts",
            }
            and not name.startswith(".tmp")
        ]
        for name in files:
            relative_path = (Path(directory) / name).relative_to(root).as_posix()
            try:
                path = workspace._resolve_safe_file_path(workspace_id, relative_path)
            except (FileNotFoundError, OSError, SecurityException, ValueError):
                continue
            digest = hashlib.sha256()
            try:
                with path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError:
                continue
            snapshot[relative_path] = digest.hexdigest()
    return snapshot


def workspace_source_digest(workspace_id: str | None) -> str:
    snapshot = workspace_source_snapshot(workspace_id)
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
