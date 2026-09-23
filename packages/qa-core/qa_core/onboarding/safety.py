"""Safety policy for executing tests from an imported QA project.

The platform must be able to say, before running anything, that a selected test does not touch the
outside world. Marker names are not evidence: in the reference repository the `smoke` marker selects
tests that drive a live public website.

The policy analyses the test function's AST rather than its raw text, and it errs towards refusing:

* browser/network/subprocess calls are matched **case-insensitively** and by method name, so a
  browser reached through a helper (`get_page().goto(...)`) or a differently-named fixture
  (`browser_session.visit(...)`) is refused just like `page.goto(...)`;
* a module import of a driver (`socket`, `subprocess`, `playwright`, requests clients) is itself a
  refusal reason, so an aliased call cannot slip through;
* file calls with an absolute, `~`-rooted or `..` path are refused, because reading a private key or
  writing outside the workspace is exactly the access this policy gates;
* the test file must resolve **inside the workspace**: an absolute node id cannot make the platform
  inspect (or run) a host file.

Anything the policy cannot inspect is refused, and executing a flagged test requires an explicit
override.
"""

from __future__ import annotations

import ast
from pathlib import Path

from pydantic import BaseModel, Field

#: Fixture names that imply a real browser session.
BROWSER_FIXTURES = frozenset(
    {
        "page",
        "browser",
        "browser_context",
        "browser_type",
        "api_request_context",
        "playwright",
    }
)

#: Method names that reach outside the process. Matched case-insensitively, whatever the receiver is.
NETWORK_CALL_NAMES = frozenset(
    {
        "goto",
        "navigate",
        "visit",
        "open_url",
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "request",
        "send",
        "urlopen",
        "urlretrieve",
        "connect",
        "create_connection",
        "fetch",
        "download",
        "upload",
    }
)

#: Method names that drive a browser even when the receiver is a local variable or a helper result.
BROWSER_ACTION_NAMES = frozenset(
    {
        "goto",
        "navigate",
        "visit",
        "reload",
        "go_back",
        "go_forward",
        "click",
        "dblclick",
        "fill",
        "type",
        "press",
        "check",
        "select_option",
        "hover",
        "screenshot",
        "wait_for_selector",
        "expect",
    }
)

#: Calls that are unsafe whatever the receiver looks like (lower-case; compared case-insensitively).
UNCONDITIONAL_UNSAFE_CALLS = frozenset(
    {
        "system",
        "popen",
        "run",
        "call",
        "check_call",
        "check_output",
        "spawn",
        "spawnl",
        "spawnlp",
        "spawnv",
        "exec",
        "execl",
        "execv",
        "eval",
        "urlopen",
        "urlretrieve",
        "connect",
        "create_connection",
        "fork",
    }
)

#: File-access calls: an absolute, `~`-rooted or parent-relative path is a refusal.
FILE_CALL_NAMES = frozenset({"open", "read_text", "write_text", "read_bytes", "write_bytes", "unlink", "remove"})

#: Modules that put a test in touch with the outside world just by being imported.
UNSAFE_MODULES = frozenset(
    {
        "playwright",
        "selenium",
        "requests",
        "httpx",
        "aiohttp",
        "socket",
        "subprocess",
        "shutil",
        "ftplib",
        "smtplib",
        "telnetlib",
        "paramiko",
        "boto3",
    }
)

#: Markers that mean "expensive and usually external".
UNSAFE_MARKERS = frozenset({"slow", "e2e", "integration", "live"})

URL_PREFIXES = ("http://", "https://", "ftp://")


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

        source_file, function = self._function_source(project_root, nodeid)
        if function is None:
            reasons.append("test source could not be inspected")
            return SafetyVerdict(nodeid=nodeid, safe=False, reasons=dedupe(reasons))

        for marker in sorted({*(markers or []), *self._markers_from_source(function)}):
            if marker in self.unsafe_markers:
                reasons.append(f"marked '{marker}'")

        parameters = function.args.args + function.args.kwonlyargs + function.args.posonlyargs
        for fixture in sorted({arg.arg for arg in parameters} & self.browser_fixtures):
            reasons.append(f"requires the '{fixture}' fixture")

        reasons.extend(self._module_level_reasons(source_file))

        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            name = str(target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", ""))
            lowered = name.lower()
            receiver = (
                ast.unparse(target.value).split(".")[0].split("[")[0].lower()
                if isinstance(target, ast.Attribute)
                else None
            )

            if lowered in UNCONDITIONAL_UNSAFE_CALLS:
                reasons.append(f"calls {name}()")
            elif lowered in BROWSER_ACTION_NAMES:
                reasons.append(f"calls browser action {name}()")
            elif lowered in NETWORK_CALL_NAMES and receiver in {
                "requests",
                "httpx",
                "urllib",
                "aiohttp",
                "session",
                "client",
            }:
                reasons.append(f"calls {receiver}.{name}()")
            elif lowered in NETWORK_CALL_NAMES and self._has_url_argument(node):
                reasons.append(f"calls {name}() with an absolute URL")
            elif lowered in FILE_CALL_NAMES and self._has_escaping_path_argument(node):
                reasons.append(f"calls {name}() with a path outside the workspace")

        return SafetyVerdict(nodeid=nodeid, safe=not reasons, reasons=dedupe(reasons))

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

    def _has_url_argument(self, call: ast.Call) -> bool:
        for argument in [*call.args, *call.keywords]:
            value = argument.value if isinstance(argument, ast.keyword) else argument
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if value.value.startswith(URL_PREFIXES):
                    return True
        return False

    def _has_escaping_path_argument(self, call: ast.Call) -> bool:
        for argument in [*call.args, *call.keywords]:
            value = argument.value if isinstance(argument, ast.keyword) else argument
            text = ast.unparse(value)
            if text.startswith(("'/", '"/', "'~", '"~')) or ".." in text or "home()" in text:
                return True
        return False

    def _module_level_reasons(self, source_file: Path) -> list[str]:
        """A test module that imports a driver or shells out is treated as touching the outside world."""
        try:
            tree = ast.parse(source_file.read_text(encoding="utf-8", errors="replace"), filename=str(source_file))
        except SyntaxError:
            return []
        reasons: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                modules = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules = {(node.module or "").split(".")[0]}
            else:
                continue
            touched = modules & UNSAFE_MODULES
            if touched:
                reasons.append(f"module imports {', '.join(sorted(touched))}")
        return dedupe(reasons)

    def _markers_from_source(self, source: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        import re

        markers: set[str] = set()
        for decorator in source.decorator_list:
            text = ast.unparse(decorator)
            match = re.match(r"^[\w.]*mark[\w.]*\.(\w+)", text)
            if match:
                markers.add(match.group(1))
        return markers

    def _function_source(self, project_root: Path, nodeid: str) -> tuple[Path | None, ast.FunctionDef | None]:
        file_part, _, test_part = nodeid.partition("::")
        root = Path(project_root).resolve()
        candidate = Path(file_part)
        if candidate.is_absolute():
            # An absolute node id must never make the policy inspect a host file.
            return None, None
        path = (root / file_part).resolve()
        if root not in path.parents and path != root:
            return None, None
        if not path.is_file():
            return None, None
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            return path, None

        # `Class::test_name[param]` -> class "Class", function "test_name".
        parts = [part for part in test_part.split("::") if part]
        function_name = parts[-1].split("[")[0] if parts else test_part.split("[")[0]
        class_name = parts[0] if len(parts) > 1 else None

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name != function_name:
                continue
            if class_name:
                parent_class = next(
                    (
                        candidate_class
                        for candidate_class in ast.walk(tree)
                        if isinstance(candidate_class, ast.ClassDef)
                        and candidate_class.name == class_name
                        and any(child is node for child in candidate_class.body)
                    ),
                    None,
                )
                if parent_class is None:
                    continue
            return path, node
        return path, None


def dedupe(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen
