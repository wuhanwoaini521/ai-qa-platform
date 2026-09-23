from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from project_model.models import (
    BranchInfo,
    GitChangedFile,
    GitCommitInfo,
    GitDiffResult,
    GitPushResult,
)


class GitSecurityError(Exception):
    """Raised when an unsafe or forbidden Git operation is attempted."""

    pass


@runtime_checkable
class GitRepositoryProtocol(Protocol):
    async def get_current_branch(self, repo_dir: Path) -> str: ...
    async def get_branches(self, repo_dir: Path) -> list[BranchInfo]: ...
    async def create_branch(self, repo_dir: Path, branch_name: str, checkout: bool = True) -> str: ...
    async def switch_branch(self, repo_dir: Path, branch_name: str) -> str: ...
    async def get_status(self, repo_dir: Path) -> list[GitChangedFile]: ...
    async def get_diff(self, repo_dir: Path, staged: bool = False) -> GitDiffResult: ...
    async def commit(
        self,
        repo_dir: Path,
        message: str,
        author_name: str = "AI QA Platform",
        author_email: str = "agent@ai-qa.local",
    ) -> str: ...
    async def push(self, repo_dir: Path, branch: str | None = None, remote: str = "origin") -> GitPushResult: ...
    async def get_log(self, repo_dir: Path, limit: int = 15) -> list[GitCommitInfo]: ...


class GitRepository(GitRepositoryProtocol):
    """Safe Git repository abstraction.
    Strictly forbids destructive commands such as force-push, reset --hard, or arbitrary checkout.
    """

    BRANCH_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\/]+$")

    def _validate_branch_name(self, branch_name: str) -> None:
        if not branch_name or not self.BRANCH_NAME_REGEX.match(branch_name):
            raise GitSecurityError(
                f"Invalid branch name: '{branch_name}'. Allowed characters: alphanumeric, _, -, ., /"
            )
        if (
            ".." in branch_name
            or branch_name.startswith("/")
            or branch_name.endswith("/")
            or branch_name.endswith(".lock")
        ):
            raise GitSecurityError(f"Unsafe branch name format: '{branch_name}'")

    async def get_current_branch(self, repo_dir: Path) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        branch = stdout.decode().strip()
        return branch if branch else "main"

    async def get_branches(self, repo_dir: Path) -> list[BranchInfo]:
        current = await self.get_current_branch(repo_dir)
        proc = await asyncio.create_subprocess_exec(
            "git",
            "branch",
            "--list",
            "-v",
            "--no-abbrev",
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        branches: list[BranchInfo] = []
        for line in stdout.decode().splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            is_cur = line.startswith("*")
            cleaned = line.lstrip("* ").strip()
            parts = cleaned.split(maxsplit=2)
            b_name = parts[0]
            sha = parts[1] if len(parts) > 1 else ""
            msg = parts[2] if len(parts) > 2 else ""
            branches.append(
                BranchInfo(
                    name=b_name,
                    is_current=(b_name == current or is_cur),
                    commit_sha=sha,
                    commit_message=msg,
                )
            )
        if not branches:
            branches.append(BranchInfo(name=current, is_current=True))
        return branches

    async def create_branch(self, repo_dir: Path, branch_name: str, checkout: bool = True) -> str:
        self._validate_branch_name(branch_name)
        args = ["checkout", "-b", branch_name] if checkout else ["branch", branch_name]
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode() or stdout.decode()
            raise RuntimeError(f"Failed to create branch '{branch_name}': {err_msg.strip()}")
        return branch_name

    async def switch_branch(self, repo_dir: Path, branch_name: str) -> str:
        self._validate_branch_name(branch_name)
        proc = await asyncio.create_subprocess_exec(
            "git",
            "checkout",
            branch_name,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode() or stdout.decode()
            raise RuntimeError(f"Failed to switch to branch '{branch_name}': {err_msg.strip()}")
        return branch_name

    async def get_status(self, repo_dir: Path) -> list[GitChangedFile]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "status",
            "--porcelain",
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        changed: list[GitChangedFile] = []
        for line in stdout.decode().splitlines():
            if not line or len(line) < 3:
                continue
            staged_char = line[0]
            worktree_char = line[1]
            status = line[:2].strip()
            path = line[3:].strip()
            is_staged = staged_char not in (" ", "?")
            changed.append(GitChangedFile(path=path, status=status or worktree_char or staged_char, staged=is_staged))
        return changed

    async def get_diff(self, repo_dir: Path, staged: bool = False) -> GitDiffResult:
        changed_files = await self.get_status(repo_dir)
        args = ["diff", "--cached"] if staged else ["diff", "HEAD"]
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        diff_text = stdout.decode()
        if not diff_text and not staged:
            # Fallback for unstaged or brand new working tree files
            proc2 = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                cwd=str(repo_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await proc2.communicate()
            diff_text = stdout2.decode()
        return GitDiffResult(diff=diff_text, changed_files=changed_files)

    async def commit(
        self,
        repo_dir: Path,
        message: str,
        author_name: str = "AI QA Platform",
        author_email: str = "agent@ai-qa.local",
    ) -> str:
        if not message.strip():
            raise ValueError("Commit message cannot be empty")

        # Stage all tracked/untracked changes safely
        proc_add = await asyncio.create_subprocess_exec(
            "git",
            "add",
            ".",
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc_add.communicate()

        proc_commit = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            message,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc_commit.communicate()
        if proc_commit.returncode != 0:
            err = (stderr.decode() or stdout.decode()).strip()
            if "nothing to commit" in err or "nothing to commit" in stdout.decode():
                return "Nothing to commit, working tree clean."
            raise RuntimeError(f"Commit failed: {err}")
        return stdout.decode().strip()

    async def push(self, repo_dir: Path, branch: str | None = None, remote: str = "origin") -> GitPushResult:
        if not branch:
            branch = await self.get_current_branch(repo_dir)
        self._validate_branch_name(branch)

        # Check if remote exists
        proc_remote = await asyncio.create_subprocess_exec(
            "git",
            "remote",
            "get-url",
            remote,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        remote_url_out, _ = await proc_remote.communicate()
        remote_url = remote_url_out.decode().strip() if proc_remote.returncode == 0 else ""

        if not remote_url:
            return GitPushResult(
                success=True,
                branch=branch,
                remote=remote,
                message=f"Simulated push: Branch '{branch}' validated (no remote '{remote}' configured for local workspace).",
            )

        # Execute push without --force
        proc_push = await asyncio.create_subprocess_exec(
            "git",
            "push",
            "-u",
            remote,
            branch,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc_push.communicate()
        if proc_push.returncode != 0:
            err_msg = (stderr.decode() or stdout.decode()).strip()
            return GitPushResult(
                success=False,
                branch=branch,
                remote=remote,
                message=f"Push failed: {err_msg}",
            )
        return GitPushResult(
            success=True,
            branch=branch,
            remote=remote,
            message=f"Successfully pushed branch '{branch}' to '{remote}'.",
        )

    async def get_log(self, repo_dir: Path, limit: int = 15) -> list[GitCommitInfo]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "log",
            f"-n{limit}",
            "--pretty=format:%H%x00%an%x00%ae%x00%ad%x00%s",
            "--date=iso",
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        commits: list[GitCommitInfo] = []
        for line in stdout.decode().splitlines():
            if not line:
                continue
            parts = line.split("\x00")
            if len(parts) >= 5:
                commits.append(
                    GitCommitInfo(
                        sha=parts[0],
                        author_name=parts[1],
                        author_email=parts[2],
                        date=parts[3],
                        message=parts[4],
                    )
                )
        return commits
