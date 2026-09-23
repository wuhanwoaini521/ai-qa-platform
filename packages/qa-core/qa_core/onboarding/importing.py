"""Copying an existing QA repository into an isolated platform workspace.

The source repository is treated as strictly read-only: the platform only reads it, and every
mutation (runtime provisioning, generated files, test artifacts) happens inside the copy. The copy
excludes version-control metadata, caches, virtualenvs and previous artifact directories, so an
import is reproducible and does not drag machine-specific state along.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from qa_core.onboarding.contract import QAProjectContract
from qa_core.onboarding.detector import QAProjectDetector
from qa_core.onboarding.runtime import RUNTIME_DIR_NAME

#: Directories that never belong in an imported workspace.
EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".tox",
        ".idea",
        ".vscode",
        ".venv",
        "venv",
        "env",
        "allure-report",
        "allure-results",
        "htmlcov",
        RUNTIME_DIR_NAME,
    }
)

#: Files that are regenerated or machine-specific.
EXCLUDED_FILES = frozenset({".DS_Store", ".coverage", "tsconfig.tsbuildinfo"})


class ImportConflict(RuntimeError):
    """Raised when an import would overwrite an existing workspace or point at itself."""


class ImportPlan(BaseModel):
    """What an import would do, without doing it."""

    source: str
    destination: str
    included_files: int = 0
    excluded_dirs: list[str] = Field(default_factory=list)
    copied_bytes: int = 0
    contract: QAProjectContract | None = None
    warnings: list[str] = Field(default_factory=list)


class ImportResult(BaseModel):
    destination: str
    copied_files: int = 0
    copied_bytes: int = 0
    excluded_dirs: list[str] = Field(default_factory=list)
    contract: QAProjectContract


class QAProjectImporter:
    """Plans and executes an isolated copy of a QA repository."""

    def __init__(self, detector: QAProjectDetector | None = None) -> None:
        self.detector = detector or QAProjectDetector()

    def plan(self, source: Path | str, destination: Path | str) -> ImportPlan:
        source_root = Path(source).expanduser().resolve()
        destination_root = Path(destination).expanduser().resolve()

        if not source_root.is_dir():
            raise NotADirectoryError(f"Source repository not found: {source_root}")
        if destination_root == source_root or destination_root in source_root.parents:
            raise ImportConflict("Destination must not be inside the source repository")
        if source_root in destination_root.parents:
            raise ImportConflict("Source must not be inside the destination workspace")

        files, total_bytes, excluded = self._scan(source_root)
        detection = self.detector.detect(source_root)
        warnings = list(detection.warnings)
        if destination_root.exists():
            warnings.append("destination already exists; executing this plan would replace it")

        return ImportPlan(
            source=str(source_root),
            destination=str(destination_root),
            included_files=files,
            excluded_dirs=sorted(excluded),
            copied_bytes=total_bytes,
            contract=detection.contract,
            warnings=warnings,
        )

    def execute(self, plan: ImportPlan, overwrite: bool = False) -> ImportResult:
        source_root = Path(plan.source)
        destination_root = Path(plan.destination)

        if destination_root.exists():
            if not overwrite:
                raise ImportConflict(f"Workspace already exists: {destination_root}")
            shutil.rmtree(destination_root)
        destination_root.parent.mkdir(parents=True, exist_ok=True)

        shutil.copytree(
            source_root,
            destination_root,
            symlinks=False,
            ignore=self._ignore,
        )
        # Re-detect inside the copy: the contract must describe the imported workspace, not the source.
        detection = self.detector.detect(destination_root)
        copied_files, copied_bytes, excluded = self._scan(destination_root)

        return ImportResult(
            destination=str(destination_root),
            copied_files=copied_files,
            copied_bytes=copied_bytes,
            excluded_dirs=sorted(excluded),
            contract=detection.contract,
        )

    def _ignore(self, directory: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name in EXCLUDED_DIRS or name in EXCLUDED_FILES}
        ignored |= {name for name in names if name.endswith((".pyc", ".pyo"))}
        return ignored

    def _scan(self, root: Path) -> tuple[int, int, set[str]]:
        files = 0
        total = 0
        excluded: set[str] = set()
        for path in root.rglob("*"):
            relative_parts = path.relative_to(root).parts
            if any(part in EXCLUDED_DIRS for part in relative_parts):
                excluded |= {part for part in relative_parts if part in EXCLUDED_DIRS}
                continue
            if path.is_file():
                if path.name in EXCLUDED_FILES or path.suffix in (".pyc", ".pyo"):
                    continue
                files += 1
                total += path.stat().st_size
        return files, total, excluded
