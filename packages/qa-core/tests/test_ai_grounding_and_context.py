"""AI safety for imported projects: bounded context selection and grounding validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from qa_core.ai.context import ContextSelector, ContextSource
from qa_core.author import GroundingValidator, ViolationKind

pytestmark = pytest.mark.unit


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_workspace(root: Path) -> Path:
    write(root / "conftest.py", "import pytest\n\n\n@pytest.fixture\ndef api_client():\n    return object()\n")
    write(root / "pages" / "search_page.py", "class SearchPage:\n    def search(self, term):\n        return term\n")
    write(root / "flows" / "search_flow.py", "class SearchFlow:\n    pass\n")
    write(root / "components" / "search_box.py", "class SearchBox:\n    pass\n")
    write(root / "knowledge" / "search_rules.md", "# search rules\n")
    write(
        root / "tests" / "test_search.py",
        "from pages.search_page import SearchPage\nfrom flows.search_flow import SearchFlow\n\n\n"
        "def test_search_uses_page_and_flow():\n    page = SearchPage()\n    flow = SearchFlow()\n    assert page and flow\n",
    )
    return root


# --- context selection -----------------------------------------------------------------------


def test_context_includes_only_the_test_its_related_assets_and_knowledge(tmp_path: Path):
    build_workspace(tmp_path)
    write(tmp_path / "pages" / "unrelated_page.py", "class UnrelatedPage:\n    pass\n")
    write(tmp_path / "tests" / "test_other.py", "def test_other():\n    assert True\n")

    bundle = ContextSelector().select(
        tmp_path,
        test_nodeid="tests/test_search.py::test_search_uses_page_and_flow",
        failure_message="TimeoutError: waiting for locator",
    )

    paths = bundle.paths
    assert "tests/test_search.py" in paths
    assert "pages/search_page.py" in paths
    assert "flows/search_flow.py" in paths
    assert "knowledge/search_rules.md" in paths
    # Unrelated pages and other tests are never shipped to a model.
    assert "pages/unrelated_page.py" not in paths
    assert "tests/test_other.py" not in paths
    assert ContextSource.FAILURE in {fragment.source for fragment in bundle.fragments}


def test_context_is_bounded_for_a_large_repository(tmp_path: Path):
    for index in range(40):
        write(tmp_path / "pages" / f"page_{index}.py", "class Page:\n    pass\n")
    write(tmp_path / "tests" / "test_big.py", "from pages.page_1 import Page\n\n\ndef test_big():\n    assert Page\n")

    bundle = ContextSelector(max_files=5, max_file_chars=50).select(tmp_path, test_nodeid="tests/test_big.py::test_big")

    assert len(bundle.fragments) <= 5
    assert all(len(fragment.content) <= 50 for fragment in bundle.fragments)
    assert bundle.total_chars <= 5 * 50


def test_context_refuses_to_read_outside_the_workspace(tmp_path: Path):
    workspace = build_workspace(tmp_path / "workspace")
    secret = tmp_path / "outside.py"
    secret.write_text("TOKEN = 'super-secret'\n", encoding="utf-8")

    bundle = ContextSelector().select(workspace, changed_files=["../outside.py"])

    assert bundle.fragments == []
    assert any("outside the workspace" in entry for entry in bundle.omitted)


# --- grounding validation --------------------------------------------------------------------


def test_grounded_code_passes_validation(tmp_path: Path):
    build_workspace(tmp_path)

    report = GroundingValidator(tmp_path).validate(
        """
import pytest
from pages.search_page import SearchPage
from flows.search_flow import SearchFlow


def test_search_flow(api_client):
    page = SearchPage()
    flow = SearchFlow()
    assert page.search("term") == "term"
    assert flow is not None
""",
        target_path="tests/generated/test_search_flow.py",
    )

    assert report.grounded is True, report.summary
    assert report.checked_fixtures >= 1
    assert report.checked_assets >= 3


def test_unknown_page_object_flow_import_and_fixture_are_violations(tmp_path: Path):
    build_workspace(tmp_path)

    report = GroundingValidator(tmp_path).validate(
        """
import pandas
from pages.checkout_page import CheckoutPage


def test_checkout(browser_session):
    page = CheckoutPage()
    flow = CheckoutFlow()
    assert page and flow
""",
        target_path="tests/generated/test_checkout.py",
    )

    kinds = {violation.kind for violation in report.violations}
    references = {violation.reference for violation in report.violations}
    assert report.grounded is False
    assert ViolationKind.UNKNOWN_IMPORT in kinds
    assert "pandas" in references
    assert ViolationKind.UNKNOWN_PAGE_OBJECT in kinds
    assert "CheckoutPage" in references
    assert ViolationKind.UNKNOWN_FLOW in kinds
    assert "CheckoutFlow" in references
    assert ViolationKind.UNKNOWN_FIXTURE in kinds
    assert "browser_session" in references


def test_generated_code_must_not_overwrite_an_existing_test(tmp_path: Path):
    build_workspace(tmp_path)
    write(tmp_path / "tests" / "test_existing.py", "def test_existing():\n    assert True\n")

    report = GroundingValidator(tmp_path).validate(
        "def test_ok():\n    assert True\n", target_path="tests/test_existing.py"
    )

    assert report.grounded is False
    assert ViolationKind.DIRECT_TESTS_WRITE in {violation.kind for violation in report.violations}

    # A new file in a dedicated directory is allowed.
    fresh = GroundingValidator(tmp_path).validate(
        "def test_ok():\n    assert True\n", target_path="tests/generated/test_new.py"
    )
    assert fresh.grounded is True


def test_syntax_errors_are_reported_as_violations_not_crashes(tmp_path: Path):
    build_workspace(tmp_path)

    report = GroundingValidator(tmp_path).validate("def test_broken(:\n", target_path="tests/generated/test_broken.py")

    assert report.grounded is False
    assert report.violations
