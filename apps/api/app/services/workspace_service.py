from __future__ import annotations

import asyncio
from pathlib import Path

import aiofiles
import aiofiles.os
from project_model.models import (
    FileNode,
    FileNodeType,
    GitChangedFile,
    GitDiffResult,
)

from app.settings import settings


class SecurityException(Exception):
    pass


class WorkspaceService:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = (base_dir or settings.workspace_storage_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_workspace_dir(self, workspace_id: str) -> Path:
        # Prevent traversal in workspace_id
        clean_id = Path(workspace_id).name
        target = (self.base_dir / clean_id).resolve()
        if not str(target).startswith(str(self.base_dir)):
            raise SecurityException("Invalid workspace ID or path traversal attempt.")
        return target

    def _resolve_safe_file_path(self, workspace_id: str, relative_path: str) -> Path:
        ws_dir = self.get_workspace_dir(workspace_id)
        # Normalize relative path
        cleaned = relative_path.lstrip("/\\")
        target = (ws_dir / cleaned).resolve()
        if not (str(target) == str(ws_dir) or str(target).startswith(str(ws_dir) + "/")):
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

        # Create sample files
        readme_content = f"""# {project_name} Automation Workspace

Welcome to the AI QA Automation Studio.

## Workspace Layout
- `tests/`: End-to-end and functional test suites.
- `pages/`: Page Object Models and selector definitions.
- `flows/`: Reusable user flow and scenario abstractions.
- `components/`: Modular UI component locators and actions.
- `knowledge/`: QA domain rules, test data, and locator dictionaries.
"""
        gitignore_content = """.pytest_cache/
__pycache__/
*.pyc
.env
screenshots/
traces/
"""
        sample_page = """from playwright.sync_api import Page, expect

class LoginPage:
    def __init__(self, page: Page):
        self.page = page
        self.username_input = page.locator('input[name="username"]')
        self.password_input = page.locator('input[name="password"]')
        self.login_button = page.locator('button[type="submit"]')

    def login(self, username: str, password: str):
        self.username_input.fill(username)
        self.password_input.fill(password)
        self.login_button.click()
"""
        sample_test = """import pytest
from playwright.sync_api import Page, expect
from pages.login_page import LoginPage

def test_login_flow(page: Page):
    login_page = LoginPage(page)
    page.goto("/login")
    login_page.login("qa_user", "secure_password")
    expect(page).to_have_url(r".*/dashboard")
"""
        await self.write_file(workspace_id, "README.md", readme_content)
        await self.write_file(workspace_id, ".gitignore", gitignore_content)
        await self.write_file(workspace_id, "pages/login_page.py", sample_page)
        await self.write_file(workspace_id, "tests/test_login.py", sample_test)

        # Initialize local git repository in workspace for diff tracking
        proc = await asyncio.create_subprocess_exec(
            "git",
            "init",
            "-b",
            "main",
            cwd=str(ws_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        proc_add = await asyncio.create_subprocess_exec(
            "git",
            "add",
            ".",
            cwd=str(ws_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc_add.communicate()

        proc_commit = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            "user.name=AI QA Platform",
            "-c",
            "user.email=agent@ai-qa.local",
            "commit",
            "-m",
            "chore: initialize blank qa project workspace",
            cwd=str(ws_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc_commit.communicate()

        return ws_dir

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
                if entry.name == ".git":
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

    async def get_git_status(self, workspace_id: str) -> list[GitChangedFile]:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            return []

        proc = await asyncio.create_subprocess_exec(
            "git",
            "status",
            "--porcelain",
            cwd=str(ws_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        changed: list[GitChangedFile] = []
        for line in stdout.decode().splitlines():
            if not line:
                continue
            status = line[:2].strip()
            path = line[3:].strip()
            changed.append(GitChangedFile(path=path, status=status, staged=" " not in line[:1]))
        return changed

    async def get_diff(self, workspace_id: str) -> GitDiffResult:
        ws_dir = self.get_workspace_dir(workspace_id)
        if not (ws_dir / ".git").exists():
            return GitDiffResult(diff="", changed_files=[])

        changed_files = await self.get_git_status(workspace_id)

        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "HEAD",
            cwd=str(ws_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        diff_text = stdout.decode()
        if not diff_text:
            # Check unstaged diff
            proc2 = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                cwd=str(ws_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await proc2.communicate()
            diff_text = stdout2.decode()

        return GitDiffResult(diff=diff_text, changed_files=changed_files)
