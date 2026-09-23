"""Onboarding a real QA project: safety classification, execution parsing, identity and Allure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from qa_core.onboarding import (
    AllureResultImporter,
    CaseIdSource,
    NodeIdCaseMapper,
    QAProjectCollector,
    QAProjectContract,
    QAProjectImporter,
    QAProjectRunner,
    SafetyPolicy,
    SuiteRunOutcome,
    parse_collection,
    parse_execution,
    parse_nodeid,
)

pytestmark = pytest.mark.unit


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --- safety policy ---------------------------------------------------------------------------


def test_safety_policy_separates_offline_tests_from_browser_and_network_tests(tmp_path: Path):
    write(
        tmp_path / "tests" / "test_mixed.py",
        """
import pytest


@pytest.mark.smoke
def test_offline_calculation():
    assert 1 + 1 == 2


@pytest.mark.smoke
def test_live_homepage(page):
    page.goto("https://example.com")


@pytest.mark.slow
def test_flagged_slow():
    assert True


def test_inline_network_call():
    import urllib.request
    urllib.request.urlopen("https://example.com")
""".lstrip(),
    )
    policy = SafetyPolicy()
    safe, rejected = policy.split(
        [
            "tests/test_mixed.py::test_offline_calculation",
            "tests/test_mixed.py::test_live_homepage",
            "tests/test_mixed.py::test_flagged_slow",
            "tests/test_mixed.py::test_inline_network_call",
        ],
        tmp_path,
    )

    assert safe == ["tests/test_mixed.py::test_offline_calculation"]
    reasons = {verdict.nodeid: " ".join(verdict.reasons) for verdict in rejected}
    assert "requires the 'page' fixture" in reasons["tests/test_mixed.py::test_live_homepage"]
    assert "goto(" in reasons["tests/test_mixed.py::test_live_homepage"]
    assert "marked 'slow'" in reasons["tests/test_mixed.py::test_flagged_slow"]
    assert "urllib" in reasons["tests/test_mixed.py::test_inline_network_call"]


def test_safety_policy_rejects_tests_it_cannot_inspect(tmp_path: Path):
    verdict = SafetyPolicy().verdict("tests/test_missing.py::test_x", tmp_path)

    assert verdict.safe is False
    assert "could not be inspected" in verdict.reasons[0]


def test_safety_policy_handles_class_based_tests(tmp_path: Path):
    write(
        tmp_path / "tests" / "test_classy.py",
        """
class TestFlows:
    def test_drives_a_browser(self, page):
        page.click("#go")

    def test_pure_logic(self):
        assert True
""".lstrip(),
    )
    policy = SafetyPolicy()

    assert policy.verdict("tests/test_classy.py::TestFlows::test_pure_logic", tmp_path).safe is True
    assert policy.verdict("tests/test_classy.py::TestFlows::test_drives_a_browser", tmp_path).safe is False


# --- collection parsing ----------------------------------------------------------------------


def test_collection_parses_nodeids_classes_and_parameters():
    outcome, error = parse_collection(
        "\n".join(
            [
                "tests/unit/test_knowledge.py::test_loader_reads_markdown",
                "tests/unit/test_matrix.py::TestMatrix::test_region[cn-east]",
                "tests/unit/test_matrix.py::TestMatrix::test_region[us-west]",
                "",
                "3 tests collected in 0.21s",
            ]
        ),
        "",
        0,
    )

    assert error is None
    assert [test.test_name for test in outcome] == ["test_loader_reads_markdown", "test_region", "test_region"]
    assert outcome[1].class_name == "TestMatrix"
    assert outcome[1].parameters == ["cn", "east"]
    assert outcome[1].is_parameterised is True
    assert outcome[0].is_parameterised is False


def test_collection_failure_is_an_error_never_an_empty_success():
    tests, error = parse_collection(
        "ERROR tests/unit/test_broken.py - ImportError: cannot import name 'missing'\n",
        "",
        2,
    )

    assert tests == []
    assert error is not None
    assert "status 2" in error
    assert "tests/unit/test_broken.py" in error


def test_collection_of_zero_tests_without_error_is_still_reported():
    tests, error = parse_collection("no tests ran in 0.01s\n", "", 0)

    assert tests == []
    assert error == "pytest collected 0 tests"


def test_parse_nodeid_rejects_lines_that_are_not_nodeids():
    assert parse_nodeid("3 tests collected") is None
    assert parse_nodeid("tests/test_a.py") is None


async def test_collector_reports_collection_error_for_a_broken_project(tmp_path: Path):
    write(tmp_path / "tests" / "test_broken.py", "import does_not_exist_at_all\n\n\ndef test_x():\n    assert True\n")
    contract = QAProjectContract(
        collect_command=["python", "-m", "pytest", "--collect-only", "-q"],
        test_command=["python", "-m", "pytest", "-v"],
        test_roots=["tests"],
        runtime={"interpreter": "python3"},
    )

    outcome = await QAProjectCollector(contract, timeout_sec=120).collect(tmp_path)

    assert outcome.status.value == "COLLECTION_ERROR"
    assert outcome.tests == []
    assert outcome.error_message
    assert outcome.exit_code not in (0, None)


# --- execution parsing: physical vs logical --------------------------------------------------


def test_execution_distinguishes_reruns_from_logical_tests():
    stdout = """
tests/unit/test_flaky.py::test_eventually_passes RERUN [ 50%]
tests/unit/test_flaky.py::test_eventually_passes PASSED [100%]
tests/unit/test_flaky.py::test_always_fails FAILED [100%]
=========== 1 failed, 1 passed, 1 rerun in 2.50s ===========
FAILED tests/unit/test_flaky.py::test_always_fails - AssertionError: assert 1 == 2
""".strip()

    logical, counts, physical, reruns = parse_execution(stdout, "")

    assert len(logical) == 2
    flaky = next(item for item in logical if item.nodeid.endswith("test_eventually_passes"))
    assert flaky.status.value == "PASSED"
    assert flaky.attempts == 2
    assert flaky.reruns == 1
    assert flaky.is_flaky_rerun is True

    failing = next(item for item in logical if item.nodeid.endswith("test_always_fails"))
    assert failing.status.value == "FAILED"
    assert failing.failure_message == "AssertionError: assert 1 == 2"

    assert physical == 3
    assert reruns == 1
    assert counts["passed"] == 1
    assert counts["failed"] == 1


def test_execution_counts_are_not_confused_by_xdist_style_output():
    stdout = """
[gw0] [ 50%] PASSED tests/unit/test_a.py::test_a
[gw1] [100%] PASSED tests/unit/test_b.py::test_b
2 passed in 1.00s
""".strip()

    logical, counts, physical, reruns = parse_execution(stdout, "")

    assert logical == []
    assert counts["passed"] == 2
    assert physical == 0
    assert reruns == 0


async def test_runner_records_a_real_bounded_selection(tmp_path: Path):
    write(
        tmp_path / "tests" / "test_sample.py",
        "def test_ok():\n    assert True\n\n\ndef test_nope():\n    assert False\n",
    )
    contract = QAProjectContract(
        collect_command=["python", "-m", "pytest", "--collect-only", "-q"],
        test_command=["python", "-m", "pytest", "-v", "-p", "no:cacheprovider"],
        test_roots=["tests"],
    )

    outcome: SuiteRunOutcome = await QAProjectRunner(contract, timeout_sec=180).run(
        tmp_path, nodeids=["tests/test_sample.py::test_ok", "tests/test_sample.py::test_nope"]
    )

    statuses = {item.nodeid: item.status.value for item in outcome.logical_tests}
    assert statuses == {
        "tests/test_sample.py::test_ok": "PASSED",
        "tests/test_sample.py::test_nope": "FAILED",
    }
    assert outcome.exit_code == 1
    assert outcome.reruns_total == 0
    assert outcome.physical_attempts == 2


# --- test identity ---------------------------------------------------------------------------


def test_identity_maps_markers_docstrings_function_names_and_parameters(tmp_path: Path):
    write(
        tmp_path / "tests" / "test_cases.py",
        '''
import pytest


@pytest.mark.testrail("C1234")
@pytest.mark.testrail("C1235")
def test_checkout():
    """[testrail: C9999]"""
    assert True


def test_c12005_login_flow():
    assert True


@pytest.mark.case_id("c777")
def test_region_matrix():
    assert True


def test_unmapped():
    assert True
'''.lstrip(),
    )
    collected = [
        parse_nodeid("tests/test_cases.py::test_checkout"),
        parse_nodeid("tests/test_cases.py::test_c12005_login_flow"),
        parse_nodeid("tests/test_cases.py::test_region_matrix[cn-east]"),
        parse_nodeid("tests/test_cases.py::test_region_matrix[us-west]"),
        parse_nodeid("tests/test_cases.py::test_unmapped"),
    ]
    collected = [test for test in collected if test is not None]

    report = NodeIdCaseMapper().map(tmp_path, collected)

    by_nodeid = {identity.nodeid: identity for identity in report.identities}
    assert by_nodeid["tests/test_cases.py::test_checkout"].case_ids == ["C1234", "C1235", "C9999"]
    assert by_nodeid["tests/test_cases.py::test_checkout"].source is CaseIdSource.MARKER
    assert by_nodeid["tests/test_cases.py::test_c12005_login_flow"].case_ids == ["C12005"]
    assert by_nodeid["tests/test_cases.py::test_region_matrix[cn-east]"].case_ids == ["C777"]
    assert by_nodeid["tests/test_cases.py::test_region_matrix[us-west]"].case_ids == ["C777"]
    assert by_nodeid["tests/test_cases.py::test_unmapped"].mapped is False

    # One function, two logical tests; unmapped tests are reported rather than silently dropped.
    assert report.logical_tests == 5
    assert report.parameterised_functions == 2
    assert report.unmapped_nodeids == ["tests/test_cases.py::test_unmapped"]
    assert any("no external case id" in note for note in report.notes)


def test_explicit_mapping_wins_over_source_heuristics(tmp_path: Path):
    write(tmp_path / "tests" / "test_x.py", "def test_c1000_x():\n    assert True\n")
    mapper = NodeIdCaseMapper({"tests/test_x.py::test_c1000_x[cn]": ["C4242"]})

    report = mapper.map(tmp_path, [parse_nodeid("tests/test_x.py::test_c1000_x[cn]")])

    assert report.identities[0].case_ids == ["C4242"]
    assert report.identities[0].source is CaseIdSource.EXPLICIT_MAP


# --- allure import ---------------------------------------------------------------------------


def test_allure_importer_reads_results_and_reports_status(tmp_path: Path):
    results = tmp_path / "allure-results"
    results.mkdir()
    (results / "abc-result.json").write_text(
        json.dumps(
            {
                "uuid": "abc",
                "historyId": "hist-1",
                "testCaseId": "case-1",
                "fullName": "tests.unit.test_x.test_y",
                "name": "test_y",
                "status": "failed",
                "start": 1000,
                "stop": 1500,
                "labels": [{"name": "suite", "value": "unit"}, {"name": "parentSuite", "value": "tests"}],
                "parameters": [{"name": "region", "value": "cn-east"}],
                "attachments": [{"name": "screenshot", "source": "abc-attachment.png", "type": "image/png"}],
            }
        ),
        encoding="utf-8",
    )
    (results / "broken-result.json").write_text("{not json", encoding="utf-8")
    (results / "abc-container.json").write_text("{}", encoding="utf-8")

    report = AllureResultImporter().import_from(results)

    assert report.total == 1
    assert report.containers == 1
    assert report.by_status == {"FAILED": 1}
    result = report.results[0]
    assert result.history_id == "hist-1"
    assert result.duration_ms == 500
    assert result.suite == "unit"
    assert result.parent_suite == "tests"
    assert result.parameters == {"region": "cn-east"}
    assert result.attachments[0].source == "abc-attachment.png"
    assert report.skipped_files == ["broken-result.json"]
    assert any("unreadable" in warning for warning in report.warnings)


def test_allure_importer_warns_when_no_results_exist(tmp_path: Path):
    empty = tmp_path / "allure-results"
    empty.mkdir()

    report = AllureResultImporter().import_from(empty)

    assert report.total == 0
    assert any("no Allure results found" in warning for warning in report.warnings)


# --- isolated import -------------------------------------------------------------------------


def test_import_copies_into_an_isolated_workspace_and_never_touches_the_source(tmp_path: Path):
    source = tmp_path / "reference"
    write(source / "pyproject.toml", '[project]\nname = "ref"\ndependencies = ["pytest"]\n')
    write(source / "tests" / "test_a.py", "def test_a():\n    assert True\n")
    write(source / ".git" / "config", "[core]\n")
    write(source / ".venv" / "bin" / "python", "binary")
    write(source / "allure-results" / "old-result.json", "{}")
    before = {path: path.stat().st_mtime for path in source.rglob("*") if path.is_file()}

    importer = QAProjectImporter()
    destination = tmp_path / "workspaces" / "ref"
    plan = importer.plan(source, destination)
    result = importer.execute(plan)

    assert result.copied_files == 2
    assert (destination / "tests" / "test_a.py").exists()
    assert not (destination / ".git").exists()
    assert not (destination / ".venv").exists()
    assert not (destination / "allure-results").exists()
    assert result.contract.test_roots == ["tests"]

    after = {path: path.stat().st_mtime for path in source.rglob("*") if path.is_file()}
    assert before == after
    assert sorted(plan.excluded_dirs) == [".git", ".venv", "allure-results"]


def test_import_refuses_to_overwrite_or_to_import_into_itself(tmp_path: Path):
    source = tmp_path / "reference"
    write(source / "tests" / "test_a.py", "def test_a():\n    assert True\n")
    importer = QAProjectImporter()
    destination = tmp_path / "workspaces" / "ref"

    plan = importer.plan(source, destination)
    importer.execute(plan)

    with pytest.raises(Exception, match="already exists"):
        importer.execute(plan)
    with pytest.raises(Exception, match="must not be inside"):
        importer.plan(source, source / "workspaces")
