"""Bounded context selection for AI prompts.

An imported QA repository can be large; sending it wholesale would be expensive, and would leak
unrelated code and secrets into a prompt. This module builds the context for one AI task from an
explicit, auditable selection: the current test, its related flow/page/component, the workspace
knowledge, the failure being diagnosed and the current git change set — never the whole repository.
"""

from __future__ import annotations

import ast
import os
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from qa_core.failure.redactor import SensitiveRedactor

#: Hard limits so a prompt can never grow with the repository.
MAX_FILES = 12
MAX_FILE_CHARS = 6000
MAX_TOTAL_CHARS = 24000
SKIPPED_DIRS = frozenset({".git", ".venv", "venv", "__pycache__", "node_modules", ".qa-platform-runtime"})
SKIPPED_SUFFIXES = (".pyc", ".png", ".jpg", ".webp", ".zip", ".db", ".sqlite")


class ContextSource(str, Enum):
    CURRENT_TEST = "current_test"
    RELATED_PAGE = "related_page"
    RELATED_FLOW = "related_flow"
    RELATED_COMPONENT = "related_component"
    KNOWLEDGE = "knowledge"
    FAILURE = "failure"
    GIT_DIFF = "git_diff"
    FIXTURE = "fixture"
    CONFIG = "config"
    RELATED_MODULE = "related_module"


class ContextFragment(BaseModel):
    source: ContextSource
    path: str
    content: str
    truncated: bool = False


class ContextBundle(BaseModel):
    """What was selected, why, and what was deliberately left out."""

    fragments: list[ContextFragment] = Field(default_factory=list)
    total_chars: int = 0
    omitted: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def render(self) -> str:
        """Render the bundle for a prompt, with the provenance of every fragment."""
        return "\n\n".join(
            f"<!-- source: {fragment.source.value} | {fragment.path} -->\n{fragment.content}"
            for fragment in self.fragments
        )

    @property
    def paths(self) -> list[str]:
        return [fragment.path for fragment in self.fragments]


class ContextSelector:
    """Selects the smallest set of files that explains one test."""

    def __init__(self, max_files: int = MAX_FILES, max_file_chars: int = MAX_FILE_CHARS) -> None:
        self.max_files = max_files
        self.max_file_chars = max_file_chars

    def select(
        self,
        workspace_root: Path | str,
        test_nodeid: str | None = None,
        failure_message: str | None = None,
        stack_trace: str | None = None,
        changed_files: list[str] | None = None,
        knowledge_dir_names: tuple[str, ...] = ("knowledge",),
        asset_dir_names: tuple[str, ...] = ("flows", "pages", "components"),
        query: str = "",
    ) -> ContextBundle:
        root = Path(workspace_root).resolve()
        bundle = ContextBundle()

        if test_nodeid:
            self._add_file(bundle, root, test_nodeid.split("::")[0], ContextSource.CURRENT_TEST)
            self._expand_imports(bundle, root, test_nodeid.split("::")[0])
            parent = (root / test_nodeid.split("::")[0]).resolve().parent
            while parent.is_relative_to(root):
                self._add_file(
                    bundle, root, (parent / "conftest.py").relative_to(root).as_posix(), ContextSource.FIXTURE
                )
                if parent == root:
                    break
                parent = parent.parent
            for path in self._related_assets(root, test_nodeid, asset_dir_names):
                self._add_file(bundle, root, path, self._source_for(path))
            for path in self._knowledge_files(root, test_nodeid, knowledge_dir_names):
                self._add_file(bundle, root, path, ContextSource.KNOWLEDGE)

        for fixture in ("conftest.py", "tests/conftest.py"):
            self._add_file(bundle, root, fixture, ContextSource.FIXTURE)
        for config in ("pyproject.toml", "pytest.ini", "requirements.txt", "setup.cfg"):
            self._add_file(bundle, root, config, ContextSource.CONFIG)
        if query:
            terms = set(re.findall(r"[A-Za-z][A-Za-z_0-9]{2,}", query.lower()))
            candidates = []
            for candidate in self._files(root, {".py"}):
                if any(part in SKIPPED_DIRS for part in candidate.parts) or not candidate.resolve().is_relative_to(
                    root
                ):
                    continue
                relative = candidate.relative_to(root).as_posix()
                try:
                    with candidate.open(encoding="utf-8", errors="replace") as handle:
                        tree = ast.parse(handle.read(32000))
                    names = {
                        node.name.lower()
                        for node in ast.walk(tree)
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    }
                except (OSError, SyntaxError):
                    continue
                score = sum(1 for term in terms if any(term in name for name in names) or term in relative.lower())
                if score or relative.startswith(("pages/", "flows/", "components/")) or candidate.name == "conftest.py":
                    candidates.append((-score, relative))
            for _, relative in sorted(candidates)[:6]:
                self._add_file(
                    bundle,
                    root,
                    relative,
                    ContextSource.FIXTURE if relative.endswith("conftest.py") else self._source_for(relative),
                )

        if (failure_message or stack_trace) and len(bundle.fragments) < self.max_files:
            bundle.fragments.append(
                ContextFragment(
                    source=ContextSource.FAILURE,
                    path="<execution output>",
                    # Redaction happens upstream; only the tail is relevant for diagnosis.
                    content=SensitiveRedactor.redact_text(((stack_trace or failure_message or "").strip())[-4000:])[
                        : max(0, MAX_TOTAL_CHARS - sum(len(item.content) for item in bundle.fragments))
                    ],
                    truncated=bool(stack_trace and len(stack_trace) > 4000),
                )
            )

        for changed in changed_files or []:
            self._add_file(bundle, root, changed, ContextSource.GIT_DIFF)

        bundle.total_chars = sum(len(fragment.content) for fragment in bundle.fragments)
        if bundle.total_chars > MAX_TOTAL_CHARS:
            bundle.notes.append(f"context exceeded {MAX_TOTAL_CHARS} chars and was limited to {self.max_files} files")
        if len(bundle.fragments) < 2:
            bundle.notes.append("little workspace context was available; the answer may be generic")
        return bundle

    def _add_file(self, bundle: ContextBundle, root: Path, relative: str, source: ContextSource) -> None:
        if any(fragment.path == relative for fragment in bundle.fragments):
            return
        if len(bundle.fragments) >= self.max_files:
            bundle.omitted.append(relative)
            return
        resolved = (root / relative).resolve()
        if root not in resolved.parents and resolved != root:
            bundle.omitted.append(f"{relative} (outside the workspace)")
            return
        if not resolved.is_file() or resolved.suffix in SKIPPED_SUFFIXES:
            return
        if any(part in SKIPPED_DIRS for part in resolved.parts):
            return

        remaining = MAX_TOTAL_CHARS - sum(len(item.content) for item in bundle.fragments)
        if remaining <= 0:
            bundle.omitted.append(f"{relative} (context budget)")
            return
        try:
            with resolved.open(encoding="utf-8", errors="replace") as handle:
                text = handle.read(self.max_file_chars + 1)
        except OSError:
            bundle.omitted.append(f"{relative} (unreadable)")
            return
        text = SensitiveRedactor.redact_text(text)
        truncated = len(text) > self.max_file_chars
        bundle.fragments.append(
            ContextFragment(
                source=source,
                path=relative,
                content=text[: min(self.max_file_chars, remaining)],
                truncated=truncated or len(text) > remaining,
            )
        )

    def _expand_imports(self, bundle: ContextBundle, root: Path, relative: str, depth: int = 0) -> None:
        if depth >= 2 or len(bundle.fragments) >= self.max_files:
            return
        resolved = (root / relative).resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            return
        try:
            with resolved.open(encoding="utf-8", errors="replace") as handle:
                tree = ast.parse(handle.read(64000))
        except (OSError, SyntaxError):
            return
        for node in ast.walk(tree):
            modules = (
                [name.name for name in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            for module in modules:
                base = resolved.parent if isinstance(node, ast.ImportFrom) and node.level else root
                if isinstance(node, ast.ImportFrom):
                    for _ in range(max(0, node.level - 1)):
                        base = base.parent
                candidate = base.joinpath(*module.split("."))
                choices = [candidate.with_suffix(".py"), candidate / "__init__.py"]
                if candidate.is_relative_to(root):
                    source_candidate = root / "src" / candidate.relative_to(root)
                    choices.extend([source_candidate.with_suffix(".py"), source_candidate / "__init__.py"])
                for imported in choices:
                    if imported.is_relative_to(root) and imported.is_file():
                        path = imported.relative_to(root).as_posix()
                        if path not in bundle.paths:
                            self._add_file(bundle, root, path, self._source_for(path))
                            self._expand_imports(bundle, root, path, depth + 1)

    def _related_assets(self, root: Path, test_nodeid: str, asset_dir_names: tuple[str, ...]) -> list[str]:
        """Flip through the project's own library and pick the assets the test mentions."""
        file_part = test_nodeid.split("::")[0]
        resolved = (root / file_part).resolve()
        if not resolved.is_relative_to(root):
            return []
        try:
            with resolved.open(encoding="utf-8", errors="replace") as handle:
                source = handle.read(64000)
        except OSError:
            return []

        selected: list[str] = []
        for directory in asset_dir_names:
            base = root / directory
            if not base.is_dir():
                continue
            for candidate in self._files(base, {".py"}):
                stem = candidate.stem
                if stem in {"__init__", "base_page", "base_component", "base_flow"}:
                    continue
                if stem and stem in source:
                    selected.append(candidate.relative_to(root).as_posix())
                    if len(selected) >= self.max_files // 2:
                        return selected
        return selected

    def _knowledge_files(self, root: Path, test_nodeid: str, knowledge_dir_names: tuple[str, ...]) -> list[str]:
        selected: list[str] = []
        for directory in knowledge_dir_names:
            base = root / directory
            if not base.is_dir():
                continue
            for candidate in self._files(base, {".md", ".yaml", ".yml", ".json"}):
                if candidate.is_file() and candidate.suffix in {".md", ".yaml", ".yml", ".json"}:
                    selected.append(candidate.relative_to(root).as_posix())
                    if len(selected) >= 3:
                        return selected
        return selected

    @staticmethod
    def _files(root: Path, suffixes: set[str]):
        """Prune dependency trees before traversal and bound all symbol/asset scans."""
        count = 0
        for directory, directories, files in os.walk(root, followlinks=False):
            directories[:] = sorted(
                name for name in directories if name not in SKIPPED_DIRS and not name.startswith(".")
            )
            for name in sorted(files):
                candidate = Path(directory) / name
                if candidate.suffix not in suffixes or not candidate.resolve().is_relative_to(root.resolve()):
                    continue
                yield candidate
                count += 1
                if count >= 500:
                    return

    def _source_for(self, path: str) -> ContextSource:
        if path.startswith("pages/") or "/pages/" in path:
            return ContextSource.RELATED_PAGE
        if path.startswith("flows/") or "/flows/" in path:
            return ContextSource.RELATED_FLOW
        if path.startswith("components/") or "/components/" in path:
            return ContextSource.RELATED_COMPONENT
        return ContextSource.RELATED_MODULE
