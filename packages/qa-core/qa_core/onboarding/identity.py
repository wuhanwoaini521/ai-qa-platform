"""Test identity: linking pytest node ids to the identifiers QA teams actually track.

One pytest function is not one business test case. A parameterised function is several logical
tests, and a repository may attach TestRail/Jira identifiers through markers, docstrings, function
names or an explicit map. The mapper reports every mapping *and* every test it could not map, so
"unmapped" is visible rather than silently treated as "no case".
"""

from __future__ import annotations

import ast
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from qa_core.onboarding.collector import CollectedTest

#: `@pytest.mark.testrail("C1234")`, `@pytest.mark.case_id("C1234")`, `@pytest.mark.qase("c1234")`
CASE_ID_MARKER = re.compile(r"(?:testrail|case_id|qase|xray)\s*[(_=]\s*['\"]?([A-Za-z]+-?\d+)['\"]?", re.IGNORECASE)
#: docstring tags: `[testrail: C1234]`, `testrail: C1234`, `[xray: PROJ-567]`
DOCSTRING_TAG = re.compile(r"\[?\s*(?:testrail|xray|case[_-]?id)\s*[:=]\s*([A-Za-z]+-?\d+)\s*\]?", re.IGNORECASE)
#: function names such as `test_c1234_login_flow` / `test_C1234_login`
FUNCTION_NAME_ID = re.compile(r"(?:^|_)([Cc]\d{3,7})(?:_|$)")
#: TestRail ids are normalised to `C<digits>`
TESTRAIL_ID = re.compile(r"^[Cc](\d+)$")


class CaseIdSource(str, Enum):
    EXPLICIT_MAP = "explicit_map"
    MARKER = "marker"
    DOCSTRING = "docstring"
    FUNCTION_NAME = "function_name"
    NONE = "none"


class CaseIdentity(BaseModel):
    nodeid: str
    case_ids: list[str] = Field(default_factory=list)
    source: CaseIdSource = CaseIdSource.NONE
    #: Parameter values when the nodeid is a parametrised instance.
    parameters: list[str] = Field(default_factory=list)

    @property
    def mapped(self) -> bool:
        return bool(self.case_ids)


class IdentityReport(BaseModel):
    strategy: str
    identities: list[CaseIdentity] = Field(default_factory=list)
    unmapped_nodeids: list[str] = Field(default_factory=list)
    parameterised_functions: int = 0
    logical_tests: int = 0
    notes: list[str] = Field(default_factory=list)


def normalise_case_id(raw: str) -> str:
    """`c1234` / `C1234` -> `C1234`; other conventions (`PROJ-567`) are preserved."""
    match = TESTRAIL_ID.match(raw.strip())
    if match:
        return f"C{match.group(1)}"
    return raw.strip()


class NodeIdCaseMapper:
    """Resolves external case ids for collected tests."""

    def __init__(self, explicit_mappings: dict[str, str | list[str]] | None = None) -> None:
        self.explicit_mappings: dict[str, list[str]] = {}
        for nodeid, value in (explicit_mappings or {}).items():
            self.explicit_mappings[nodeid] = value if isinstance(value, list) else [value]

    def map(self, project_root: Path, tests: list[CollectedTest]) -> IdentityReport:
        identities: list[CaseIdentity] = []
        function_cache: dict[tuple[str, str | None, str], list[str]] = {}
        parameterised = 0
        seen_functions: set[tuple[str, str | None, str]] = set()

        for test in tests:
            if test.is_parameterised:
                parameterised += 1
            key = (test.file, test.class_name, test.test_name)
            if key not in function_cache:
                function_cache[key] = self._ids_from_source(project_root, test)
            seen_functions.add(key)

            explicit = self.explicit_mappings.get(test.nodeid)
            if explicit:
                identities.append(
                    CaseIdentity(
                        nodeid=test.nodeid,
                        case_ids=[normalise_case_id(item) for item in explicit],
                        source=CaseIdSource.EXPLICIT_MAP,
                        parameters=test.parameters,
                    )
                )
                continue

            case_ids = function_cache[key]
            source = CaseIdSource.NONE
            if case_ids:
                source = self._source_for(project_root, test)
            identities.append(
                CaseIdentity(
                    nodeid=test.nodeid,
                    case_ids=case_ids,
                    source=source,
                    parameters=test.parameters,
                )
            )

        unmapped = [identity.nodeid for identity in identities if not identity.mapped]
        notes: list[str] = []
        if unmapped:
            notes.append(
                f"{len(unmapped)} of {len(identities)} logical tests carry no external case id; "
                "they are tracked by pytest node id only"
            )
        if parameterised:
            notes.append(
                f"{parameterised} logical tests come from parameterised functions; each instance is "
                "a distinct logical test that shares its function's case mapping unless an explicit "
                "mapping is declared per instance"
            )
        return IdentityReport(
            strategy="explicit_map > marker > docstring > function_name",
            identities=identities,
            unmapped_nodeids=unmapped,
            parameterised_functions=parameterised,
            logical_tests=len(identities),
            notes=notes,
        )

    def _ids_from_source(self, project_root: Path, test: CollectedTest) -> list[str]:
        source = self._function_source(project_root, test)
        if source is None:
            return []
        found: list[str] = []

        for decorator in source.decorator_list:
            text = ast.unparse(decorator)
            for match in CASE_ID_MARKER.finditer(text):
                found.append(normalise_case_id(match.group(1)))

        docstring = ast.get_docstring(source) or ""
        for match in DOCSTRING_TAG.finditer(docstring):
            found.append(normalise_case_id(match.group(1)))

        name_match = FUNCTION_NAME_ID.search(test.test_name)
        if name_match:
            found.append(normalise_case_id(name_match.group(1)))

        if not found:
            for match in CASE_ID_MARKER.finditer(ast.unparse(source)):
                found.append(normalise_case_id(match.group(1)))

        unique: list[str] = []
        for case_id in found:
            if case_id not in unique:
                unique.append(case_id)
        return unique

    def _source_for(self, project_root: Path, test: CollectedTest) -> CaseIdSource:
        source = self._function_source(project_root, test)
        if source is None:
            return CaseIdSource.NONE
        decorators = " ".join(ast.unparse(decorator) for decorator in source.decorator_list)
        if CASE_ID_MARKER.search(decorators) or CASE_ID_MARKER.search(ast.unparse(source)):
            return CaseIdSource.MARKER
        if DOCSTRING_TAG.search(ast.get_docstring(source) or ""):
            return CaseIdSource.DOCSTRING
        if FUNCTION_NAME_ID.search(test.test_name):
            return CaseIdSource.FUNCTION_NAME
        return CaseIdSource.NONE

    def _function_source(self, project_root: Path, test: CollectedTest) -> ast.FunctionDef | None:
        path = project_root / test.file
        if not path.is_file():
            return None
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            return None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == test.test_name:
                return node
        return None
