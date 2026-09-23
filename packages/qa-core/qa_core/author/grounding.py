"""Grounding validation for AI-authored tests.

Generated code that references a fixture, page object, flow or import that does not exist is not a
draft to be reviewed — it is a fabrication. This module walks the generated AST against the actual
workspace and reports every ungrounded reference, so the platform can refuse the output instead of
presenting it as runnable.
"""

from __future__ import annotations

import ast
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

#: Modules a generated test may import without the workspace declaring them.
ALLOWED_IMPORTS = frozenset(
    {
        "pytest",
        "playwright",
        "allure",
        "json",
        "re",
        "os",
        "pathlib",
        "datetime",
        "typing",
        "math",
        "random",
        "time",
        "logging",
        "dataclasses",
        "collections",
        "itertools",
    }
)

#: Fixtures pytest itself provides (or that the platform injects).
BUILTIN_FIXTURES = frozenset(
    {
        "request",
        "tmp_path",
        "tmp_path_factory",
        "monkeypatch",
        "capsys",
        "caplog",
        "pytestconfig",
        "page",
        "browser",
        "context",
        "browser_context",
        "browser_type",
        "playwright",
    }
)

#: Test-file/class naming the platform treats as groundable assets.
ASSET_DIRECTORIES = ("pages", "flows", "components", "locators", "api", "utils")


class ViolationKind(str, Enum):
    UNKNOWN_IMPORT = "unknown_import"
    UNKNOWN_FIXTURE = "unknown_fixture"
    UNKNOWN_PAGE_OBJECT = "unknown_page_object"
    UNKNOWN_FLOW = "unknown_flow"
    UNKNOWN_METHOD = "unknown_method"
    DIRECT_TESTS_WRITE = "direct_tests_write"


class GroundingViolation(BaseModel):
    kind: ViolationKind
    reference: str
    detail: str


class GroundingReport(BaseModel):
    grounded: bool
    violations: list[GroundingViolation] = Field(default_factory=list)
    checked_fixtures: int = 0
    checked_assets: int = 0

    @property
    def summary(self) -> str:
        if self.grounded:
            return "code is grounded in the workspace"
        return "; ".join(f"{violation.kind.value}: {violation.reference}" for violation in self.violations)


class GroundingValidator:
    """Validates generated code against the workspace it claims to belong to."""

    def __init__(self, workspace_root: Path | str) -> None:
        self.root = Path(workspace_root).resolve()

    def validate(self, code: str, target_path: str | None = None) -> GroundingReport:
        try:
            tree = ast.parse(code)
        except SyntaxError as error:
            return GroundingReport(
                grounded=False,
                violations=[
                    GroundingViolation(kind=ViolationKind.UNKNOWN_METHOD, reference="<syntax>", detail=str(error))
                ],
            )

        violations: list[GroundingViolation] = []
        violations.extend(self._check_imports(tree))
        fixtures = self._workspace_fixtures()
        asset_names = self._workspace_asset_names()
        violations.extend(self._check_fixtures(tree, fixtures))
        violations.extend(self._check_assets(tree, asset_names))
        if target_path and self._overwrites_existing_test(target_path):
            violations.append(
                GroundingViolation(
                    kind=ViolationKind.DIRECT_TESTS_WRITE,
                    reference=target_path,
                    detail="generated code must not overwrite an existing test file",
                )
            )
        return GroundingReport(
            grounded=not violations,
            violations=violations,
            checked_fixtures=len(fixtures),
            checked_assets=len(asset_names),
        )

    def _check_imports(self, tree: ast.AST) -> list[GroundingViolation]:
        violations: list[GroundingViolation] = []
        local_modules = self._workspace_module_names()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if not name or name in ALLOWED_IMPORTS or name in local_modules:
                    continue
                violations.append(
                    GroundingViolation(
                        kind=ViolationKind.UNKNOWN_IMPORT,
                        reference=name,
                        detail=f"module '{name}' is neither a known dependency nor present in the workspace",
                    )
                )
        return violations

    def _check_fixtures(self, tree: ast.AST, fixtures: set[str]) -> list[GroundingViolation]:
        violations: list[GroundingViolation] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            parameters = node.args.args + node.args.kwonlyargs + node.args.posonlyargs
            for parameter in parameters:
                name = parameter.arg
                if name in ("self", "cls") or name in BUILTIN_FIXTURES or name in fixtures:
                    continue
                violations.append(
                    GroundingViolation(
                        kind=ViolationKind.UNKNOWN_FIXTURE,
                        reference=name,
                        detail=f"fixture '{name}' is not defined by the workspace or pytest",
                    )
                )
        return violations

    def _check_assets(self, tree: ast.AST, asset_names: set[str]) -> list[GroundingViolation]:
        violations: list[GroundingViolation] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name not in asset_names and self._looks_like_asset(node.name):
                violations.append(
                    GroundingViolation(
                        kind=self._asset_kind(node.name),
                        reference=node.name,
                        detail=f"'{node.name}' is not defined in the workspace",
                    )
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                name = node.func.id
                if self._looks_like_asset(name) and name not in asset_names:
                    violations.append(
                        GroundingViolation(
                            kind=self._asset_kind(name),
                            reference=name,
                            detail=f"'{name}' is not defined in the workspace",
                        )
                    )
        return violations

    def _looks_like_asset(self, name: str) -> bool:
        return bool(re.search(r"(Page|Flow|Component|Locator)$", name)) and len(name) > 6

    def _asset_kind(self, name: str) -> ViolationKind:
        if name.endswith("Page"):
            return ViolationKind.UNKNOWN_PAGE_OBJECT
        if name.endswith("Flow"):
            return ViolationKind.UNKNOWN_FLOW
        return ViolationKind.UNKNOWN_METHOD

    def _workspace_asset_names(self) -> set[str]:
        names: set[str] = set()
        for directory in ASSET_DIRECTORIES:
            base = self.root / directory
            if not base.is_dir():
                continue
            for candidate in base.rglob("*.py"):
                names.add(self._to_class_name(candidate.stem))
                names.update(self._class_names(candidate))
        return names

    def _workspace_module_names(self) -> set[str]:
        modules: set[str] = set()
        for candidate in self.root.rglob("*.py"):
            if any(part in {".venv", ".git", "__pycache__"} for part in candidate.parts):
                continue
            relative = candidate.relative_to(self.root)
            modules.add(relative.stem)
            if len(relative.parts) > 1:
                modules.add(relative.parts[0])
        return modules

    def _workspace_fixtures(self) -> set[str]:
        fixtures: set[str] = set()
        for candidate in self.root.rglob("conftest.py"):
            fixtures.update(self._fixture_names(candidate))
        for candidate in self.root.rglob("tests/**/*.py"):
            if candidate.name.startswith("test_"):
                fixtures.update(self._fixture_names(candidate))
        return fixtures

    def _fixture_names(self, path: Path) -> set[str]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            return set()
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                decorators = " ".join(ast.unparse(decorator) for decorator in node.decorator_list)
                if "fixture" in decorators:
                    names.add(node.name)
        return names

    def _class_names(self, path: Path) -> set[str]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            return set()
        return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}

    def _to_class_name(self, stem: str) -> str:
        return "".join(part.capitalize() for part in stem.split("_"))

    def _overwrites_existing_test(self, target_path: str) -> bool:
        """Writing *new* files under `tests/` is fine; replacing hand-written tests is not."""
        parts = Path(target_path).parts
        if not parts or parts[0] != "tests":
            return False
        return (self.root / target_path).exists()
