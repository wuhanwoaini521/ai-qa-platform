"""Safety policy for executing tests from an imported QA project.

The platform must be able to say, before running anything, that a selected test does not touch the
outside world. Marker names are not evidence: in the reference repository the `smoke` marker selects
tests that drive a live public website. This policy inspects each test's own source and requires an
explicit override before anything unsafe is executed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from pydantic import BaseModel, Field

#: Fixture names that imply a real browser session.
BROWSER_FIXTURES = frozenset(
    {
        "page",
        "browser",
        "browser_context",
        "context",
        "browser_type",
        "api_request_context",
        "playwright",
    }
)

#: Call/attribute prefixes that imply outbound network or external writes.
NETWORK_INDICATORS = (
    "goto(",
    "http://",
    "https://",
    "requests.",
    "httpx.",
    "urllib",
    "urlopen",
    "socket.",
    "subprocess",
    "os.system",
)

#: Markers that mean "expensive and usually external".
UNSAFE_MARKERS = frozenset({"slow", "e2e", "integration", "live"})


class SafetyVerdict(BaseModel):
    """Whether a single test is safe to execute unattended, and why."""

    nodeid: str
    safe: bool
    reasons: list[str] = Field(default_factory=list)


class SafetyPolicy(BaseModel):
    """Classifies tests as offline-safe or not, from their source."""

    unsafe_markers: frozenset[str] = Field(default_factory=lambda: UNSAFE_MARKERS)
    browser_fixtures: frozenset[str] = Field(default_factory=lambda: BROWSER_FIXTURES)

    def verdict(
        self,
        nodeid: str,
        project_root: Path,
        markers: list[str] | None = None,
    ) -> SafetyVerdict:
        reasons: list[str] = []

        source, _function_name = self._function_source(project_root, nodeid)
        if source is None:
            reasons.append("test source could not be inspected")
            return SafetyVerdict(nodeid=nodeid, safe=False, reasons=reasons)

        # Markers are read from the test's own decorators rather than from pytest's runtime
        # resolution, because the policy has to be able to decide *before* anything is executed.
        for marker in sorted({*(markers or []), *self._markers_from_source(source)}):
            if marker in self.unsafe_markers:
                reasons.append(f"marked '{marker}'")

        parameters = source.args.args + source.args.kwonlyargs + source.args.posonlyargs
        names = {arg.arg for arg in parameters}
        for fixture in sorted(names & self.browser_fixtures):
            reasons.append(f"requires the '{fixture}' fixture")

        body = ast.unparse(source)
        for indicator in NETWORK_INDICATORS:
            if indicator in body:
                reasons.append(f"contains '{indicator}'")

        # A fixture requested through a helper (e.g. `def helper(page):`) still counts.
        if "playwright" in body and "requires" not in " ".join(reasons):
            reasons.append("references playwright")

        return SafetyVerdict(nodeid=nodeid, safe=not reasons, reasons=reasons)

    def split(
        self,
        nodeids: list[str],
        project_root: Path,
        markers_by_nodeid: dict[str, list[str]] | None = None,
    ) -> tuple[list[str], list[SafetyVerdict]]:
        """Return (safe nodeids, verdicts for every rejected nodeid)."""
        markers_by_nodeid = markers_by_nodeid or {}
        safe: list[str] = []
        rejected: list[SafetyVerdict] = []
        for nodeid in nodeids:
            verdict = self.verdict(nodeid, project_root, markers_by_nodeid.get(nodeid))
            if verdict.safe:
                safe.append(nodeid)
            else:
                rejected.append(verdict)
        return safe, rejected

    def _markers_from_source(self, source: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        markers: set[str] = set()
        for decorator in source.decorator_list:
            text = ast.unparse(decorator)
            match = re.match(r"^[\w.]*mark[\w.]*\.(\w+)", text)
            if match:
                markers.add(match.group(1))
        return markers

    def _function_source(self, project_root: Path, nodeid: str) -> tuple[ast.FunctionDef | None, str | None]:
        file_part, _, test_part = nodeid.partition("::")
        path = project_root / file_part
        if not path.is_file():
            return None, None
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            return None, None

        parts = [part for part in test_part.split("::") if part and "[" not in part]
        function_name = parts[-1] if parts else test_part
        class_name = parts[0] if len(parts) > 1 else None

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name != function_name:
                continue
            if class_name:
                parent_class = next(
                    (
                        candidate
                        for candidate in ast.walk(tree)
                        if isinstance(candidate, ast.ClassDef)
                        and candidate.name == class_name
                        and any(child is node for child in candidate.body)
                    ),
                    None,
                )
                if parent_class is None:
                    continue
            return node, function_name
        return None, function_name
