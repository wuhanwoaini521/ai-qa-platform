"""Bounded context selection for AI prompts.

An imported QA repository can be large; sending it wholesale would be expensive, and would leak
unrelated code and secrets into a prompt. This module builds the context for one AI task from an
explicit, auditable selection: the current test, its related flow/page/component, the workspace
knowledge, the failure being diagnosed and the current git change set — never the whole repository.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

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
    ) -> ContextBundle:
        root = Path(workspace_root).resolve()
        bundle = ContextBundle()

        if test_nodeid:
            self._add_file(bundle, root, test_nodeid.split("::")[0], ContextSource.CURRENT_TEST)
            for path in self._related_assets(root, test_nodeid, asset_dir_names):
                self._add_file(bundle, root, path, self._source_for(path))
            for path in self._knowledge_files(root, test_nodeid, knowledge_dir_names):
                self._add_file(bundle, root, path, ContextSource.KNOWLEDGE)

        if failure_message or stack_trace:
            bundle.fragments.append(
                ContextFragment(
                    source=ContextSource.FAILURE,
                    path="<execution output>",
                    # Redaction happens upstream; only the tail is relevant for diagnosis.
                    content=((stack_trace or failure_message or "").strip())[-4000:],
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

        text = resolved.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > self.max_file_chars
        bundle.fragments.append(
            ContextFragment(
                source=source,
                path=relative,
                content=text[: self.max_file_chars],
                truncated=truncated,
            )
        )

    def _related_assets(self, root: Path, test_nodeid: str, asset_dir_names: tuple[str, ...]) -> list[str]:
        """Flip through the project's own library and pick the assets the test mentions."""
        file_part = test_nodeid.split("::")[0]
        try:
            source = (root / file_part).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        selected: list[str] = []
        for directory in asset_dir_names:
            base = root / directory
            if not base.is_dir():
                continue
            for candidate in sorted(base.rglob("*.py")):
                stem = candidate.stem
                if stem in {"__init__", "base_page", "base_component", "base_flow"}:
                    continue
                if stem and stem in source:
                    selected.append(str(candidate.relative_to(root)))
                    if len(selected) >= self.max_files // 2:
                        return selected
        return selected

    def _knowledge_files(self, root: Path, test_nodeid: str, knowledge_dir_names: tuple[str, ...]) -> list[str]:
        selected: list[str] = []
        for directory in knowledge_dir_names:
            base = root / directory
            if not base.is_dir():
                continue
            for candidate in sorted(base.rglob("*")):
                if candidate.is_file() and candidate.suffix in {".md", ".yaml", ".yml", ".json"}:
                    selected.append(str(candidate.relative_to(root)))
                    if len(selected) >= 3:
                        return selected
        return selected

    def _source_for(self, path: str) -> ContextSource:
        if path.startswith("pages/") or "/pages/" in path:
            return ContextSource.RELATED_PAGE
        if path.startswith("flows/") or "/flows/" in path:
            return ContextSource.RELATED_FLOW
        return ContextSource.RELATED_COMPONENT
