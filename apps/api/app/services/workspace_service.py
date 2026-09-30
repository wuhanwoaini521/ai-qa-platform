from __future__ import annotations

import ast
import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import aiofiles
import aiofiles.os
from integrations.git_repository import GitRepository
from project_model.models import (
    BranchInfo,
    CollectedTest,
    CollectionReport,
    FileNode,
    FileNodeType,
    GitChangedFile,
    GitCommitInfo,
    GitDiffResult,
    GitPushResult,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)

from app.settings import settings

EXAMPLE_DIR = Path(__file__).resolve().parents[4] / "examples" / "quickstart"
EXAMPLE_FILES = (
    ".gitignore",
    "README.md",
    "pytest.ini",
    "components/__init__.py",
    "components/cart.py",
    "flows/__init__.py",
    "flows/login_flow.py",
    "knowledge/example_rules.md",
    "pages/README.md",
    "tests/test_cart.py",
    "tests/test_login.py",
)


class SecurityException(Exception):
    pass


class WorkspaceService:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = (base_dir or settings.workspace_storage_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.git_repo = GitRepository()

    def get_workspace_dir(self, workspace_id: str) -> Path:
        # Prevent traversal in workspace_id
        clean_id = Path(workspace_id).name
        target = (self.base_dir / clean_id).resolve()
        if not target.is_relative_to(self.base_dir):
            raise SecurityException("Invalid workspace ID or path traversal attempt.")
        return target

    def _resolve_safe_file_path(self, workspace_id: str, relative_path: str) -> Path:
        ws_dir = self.get_workspace_dir(workspace_id)
        # Normalize relative path
        cleaned = relative_path.lstrip("/\\")
        target = (ws_dir / cleaned).resolve()
        if not target.is_relative_to(ws_dir):
            raise SecurityException(f"Path traversal detected: {relative_path}")
        return target

    async def initialize_workspace(self, workspace_id: str, project_name: str) -> Path:
        ws_dir = self.get_workspace_dir(workspace_id)
        ws_dir.mkdir(parents=True, exist_ok=True)

        # Create starter framework folders
        (ws_dir / "tests").mkdir(parents=True, exist_ok=True)
        (ws_dir / "pages").mkdir(parents=True, exist_ok=True)
        (ws_dir / "flows").mkdir(parents=True, exist_ok=True)
        (ws_dir / "components").mkdir(parents=True, exist_ok=True)
        (ws_dir / "knowledge").mkdir(parents=True, exist_ok=True)

        # The repository example is the single source for both the checked-in sample and new
        # workspaces. Re-running bootstrap must preserve edits made in Automation Studio.
        for relative_path in EXAMPLE_FILES:
            destination = self._resolve_safe_file_path(workspace_id, relative_path)
            if destination.exists():
                continue
            content = (EXAMPLE_DIR / relative_path).read_text(encoding="utf-8")
            if relative_path == "README.md":
                content = content.replace(
                    "# Automation Workspace Quickstart", f"# {project_name} Automation Workspace", 1
                )
            await self.write_file(workspace_id, relative_path, content)

        # Existing workspaces may contain edits. Bootstrap must not stage or commit them.
        if (ws_dir / ".git").exists():
            return ws_dir

        # Python's Windows selector event loop does not support asyncio subprocess transports.
        # Run the short local Git bootstrap in a worker thread so project creation also works
        # when Uvicorn is running with its Windows-compatible event loop.
        await asyncio.to_thread(self._initialize_git_repo, ws_dir)

        return ws_dir

    @staticmethod
    def _initialize_git_repo(workspace_dir: Path) -> None:
        """Initialize version history without making Git availability block workspace creation."""
        commands = (
            ["git", "init", "-b", "main"],
            ["git", "add", "."],
            [
                "git",
                "-c",
                "user.name=AI QA Platform",
                "-c",
                "user.email=agent@ai-qa.local",
                "commit",
                "-m",
                "chore: initialize runnable qa example workspace",
            ],
        )
        for command in commands:
            result = subprocess.run(
                command,
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                # Keep the usable source workspace even if Git is missing or misconfigured.
                return

    async def get_file_tree(self, workspace_id: str) -> list[FileNode]:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not ws_dir.exists():
            return []

        def build_tree(current: Path, rel: str = "") -> list[FileNode]:
            nodes: list[FileNode] = []
            try:
                entries = sorted(list(current.iterdir()), key=lambda e: (e.is_file(), e.name.lower()))
            except Exception:
                return []

            for entry in entries:
                if entry.name in (".git", "__pycache__", ".pytest_cache", ".ruff_cache"):
                    continue
                node_rel = f"{rel}/{entry.name}" if rel else entry.name
                if entry.is_dir():
                    children = build_tree(entry, node_rel)
                    nodes.append(
                        FileNode(
                            name=entry.name,
                            path=node_rel,
                            type=FileNodeType.DIRECTORY,
                            children=children,
                        )
                    )
                else:
                    nodes.append(
                        FileNode(
                            name=entry.name,
                            path=node_rel,
                            type=FileNodeType.FILE,
                            size=entry.stat().st_size,
                        )
                    )
            return nodes

        return build_tree(ws_dir)

    async def read_file(self, workspace_id: str, relative_path: str) -> str:
        target = self._resolve_safe_file_path(workspace_id, relative_path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")
        async with aiofiles.open(target, "r", encoding="utf-8", errors="replace") as f:
            return await f.read()

    async def write_file(self, workspace_id: str, relative_path: str, content: str) -> None:
        target = self._resolve_safe_file_path(workspace_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, "w", encoding="utf-8") as f:
            await f.write(content)

    async def create_file_or_dir(
        self, workspace_id: str, relative_path: str, is_directory: bool = False, content: str = ""
    ) -> str:
        target = self._resolve_safe_file_path(workspace_id, relative_path)
        if target.exists():
            raise FileExistsError(f"Path already exists: {relative_path}")

        if is_directory:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(target, "w", encoding="utf-8") as f:
                await f.write(content)
        return relative_path

    async def rename_path(self, workspace_id: str, old_path: str, new_path: str) -> None:
        old_target = self._resolve_safe_file_path(workspace_id, old_path)
        new_target = self._resolve_safe_file_path(workspace_id, new_path)

        if not old_target.exists():
            raise FileNotFoundError(f"Source path not found: {old_path}")
        if new_target.exists():
            raise FileExistsError(f"Target path already exists: {new_path}")

        new_target.parent.mkdir(parents=True, exist_ok=True)
        old_target.rename(new_target)

    async def delete_path(self, workspace_id: str, relative_path: str) -> None:
        target = self._resolve_safe_file_path(workspace_id, relative_path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {relative_path}")

        ws_dir = self.get_workspace_dir(workspace_id)
        if target == ws_dir:
            raise SecurityException("Cannot delete entire root workspace directory.")

        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    async def get_current_branch(self, workspace_id: str) -> str:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            return "main"
        return await self.git_repo.get_current_branch(ws_dir)

    async def get_branches(self, workspace_id: str) -> list[BranchInfo]:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            return [BranchInfo(name="main", is_current=True)]
        return await self.git_repo.get_branches(ws_dir)

    async def create_branch(self, workspace_id: str, branch_name: str, checkout: bool = True) -> str:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            raise RuntimeError("Workspace is not a Git repository.")
        return await self.git_repo.create_branch(ws_dir, branch_name, checkout=checkout)

    async def switch_branch(self, workspace_id: str, branch_name: str) -> str:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            raise RuntimeError("Workspace is not a Git repository.")
        return await self.git_repo.switch_branch(ws_dir, branch_name)

    async def commit_changes(
        self,
        workspace_id: str,
        message: str,
        author_name: str = "AI QA Platform",
        author_email: str = "agent@ai-qa.local",
    ) -> str:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            raise RuntimeError("Workspace is not a Git repository.")
        return await self.git_repo.commit(ws_dir, message=message, author_name=author_name, author_email=author_email)

    async def push_branch(self, workspace_id: str, branch: str | None = None, remote: str = "origin") -> GitPushResult:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            raise RuntimeError("Workspace is not a Git repository.")
        return await self.git_repo.push(ws_dir, branch=branch, remote=remote)

    async def get_git_log(self, workspace_id: str, limit: int = 15) -> list[GitCommitInfo]:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            return []
        return await self.git_repo.get_log(ws_dir, limit=limit)

    async def get_git_status(self, workspace_id: str) -> list[GitChangedFile]:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            return []
        return await self.git_repo.get_status(ws_dir)

    async def get_diff(self, workspace_id: str, staged: bool = False) -> GitDiffResult:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            return GitDiffResult(diff="", changed_files=[])
        return await self.git_repo.get_diff(ws_dir, staged=staged)

    async def validate_workspace(self, workspace_id: str) -> ValidationReport:
        """Checks for Python syntax errors and basic lint diagnostics."""
        ws_dir = self.get_workspace_dir(workspace_id)
        if not ws_dir.exists():
            return ValidationReport(workspace_id=workspace_id, valid=False, issues=[])

        issues: list[ValidationIssue] = []

        # 1. AST Syntax validation on all .py files
        for root, _, files in os.walk(ws_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(ws_dir).as_posix()
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        ast.parse(content, filename=rel_path)
                    except SyntaxError as e:
                        issues.append(
                            ValidationIssue(
                                file=rel_path,
                                line=e.lineno or 1,
                                column=e.offset or 1,
                                severity=ValidationSeverity.ERROR,
                                code="E999",
                                message=f"SyntaxError: {e.msg}",
                                source="syntax",
                            )
                        )
                    except Exception as ex:
                        issues.append(
                            ValidationIssue(
                                file=rel_path,
                                line=1,
                                column=1,
                                severity=ValidationSeverity.ERROR,
                                code="ERR",
                                message=str(ex),
                                source="syntax",
                            )
                        )

        # 2. Pytest collection check to capture test discovery issues
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["pytest", "--collect-only", "-q"],
                cwd=str(ws_dir),
                capture_output=True,
                check=False,
            )
            if (proc.returncode != 0 and b"ERROR" in proc.stderr) or b"errors during collection" in proc.stdout:
                for line in (proc.stderr.decode() + "\n" + proc.stdout.decode()).splitlines():
                    if "ERROR collecting" in line or "ModuleNotFoundError" in line:
                        issues.append(
                            ValidationIssue(
                                file="pytest",
                                line=1,
                                column=1,
                                severity=ValidationSeverity.WARNING,
                                code="PYTEST_COLLECT",
                                message=line.strip(),
                                source="pytest",
                            )
                        )
        except Exception:
            pass

        return ValidationReport(
            workspace_id=workspace_id,
            valid=len([i for i in issues if i.severity == ValidationSeverity.ERROR]) == 0,
            issues=issues,
        )

    async def collect_tests(self, workspace_id: str) -> CollectionReport:
        """Parses test files using AST and pytest to collect all test nodeids."""
        ws_dir = self.get_workspace_dir(workspace_id)
        tests: list[CollectedTest] = []
        errors: list[str] = []

        tests_dir = ws_dir / "tests"
        if not tests_dir.exists():
            return CollectionReport(workspace_id=workspace_id, total=0, tests=[])

        for root, _, files in os.walk(tests_dir):
            for file in files:
                if file.startswith("test_") and file.endswith(".py"):
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(ws_dir).as_posix()
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        tree = ast.parse(content, filename=rel_path)

                        for node in tree.body:
                            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                                markers = [
                                    decorator.attr if isinstance(decorator, ast.Attribute) else str(decorator)
                                    for decorator in node.decorator_list
                                ]
                                tests.append(
                                    CollectedTest(
                                        nodeid=f"{rel_path}::{node.name}",
                                        file=rel_path,
                                        class_name=None,
                                        test_name=node.name,
                                        markers=markers,
                                        line=node.lineno,
                                    )
                                )
                            elif isinstance(node, ast.ClassDef) and (
                                node.name.startswith("Test") or "Test" in node.name
                            ):
                                for item in node.body:
                                    if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                                        tests.append(
                                            CollectedTest(
                                                nodeid=f"{rel_path}::{node.name}::{item.name}",
                                                file=rel_path,
                                                class_name=node.name,
                                                test_name=item.name,
                                                markers=[],
                                                line=item.lineno,
                                            )
                                        )
                    except Exception as e:
                        errors.append(f"Failed parsing {rel_path}: {e}")

        return CollectionReport(workspace_id=workspace_id, total=len(tests), tests=tests, errors=errors)
