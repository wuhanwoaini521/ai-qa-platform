from pathlib import Path

import pytest
from qa_core.execution.pytest_runner import PytestRunner, validate_pytest_nodeids
from qa_core.failure.classifier import FailureClassifier


@pytest.mark.asyncio
async def test_runner_rejects_workspace_escape_before_execution(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "test_outside.py").write_text("def test_outside():\n    assert True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="workspace"):
        await PytestRunner().run_suite(workspace, nodeids=["../outside/test_outside.py::test_outside"])


@pytest.mark.parametrize(
    "nodeid",
    [
        "--version",
        "-p",
        "@pytest-args.txt",
        "../other/test_case.py",
        "/other/test_case.py",
        "C:\\other\\test_case.py",
        "",
        "tests/\x00.py",
    ],
)
def test_nodeid_validation_rejects_options_and_non_workspace_paths(tmp_path, nodeid):
    with pytest.raises(ValueError, match="workspace"):
        validate_pytest_nodeids(tmp_path, [nodeid])


@pytest.mark.parametrize("selection", [[], ["tests/test_case.py::test_example"]])
def test_nodeid_validation_resolves_symlinks_before_accepting_selection(tmp_path, selection):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    try:
        (workspace / "tests").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks requires Windows developer mode or elevated privileges")
    with pytest.raises(ValueError, match="workspace"):
        validate_pytest_nodeids(workspace, selection)


def test_nodeid_validation_preserves_parameter_ids_when_normalizing_windows_paths(tmp_path):
    assert validate_pytest_nodeids(tmp_path, [r"tests\test_case.py::test_case[C:\user::route with spaces]"]) == [
        r"tests/test_case.py::test_case[C:\user::route with spaces]"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selection", ["tests", "tests/test_case.py", "tests/test_case.py::test_case[route::case with spaces]"]
)
async def test_real_runner_accepts_directory_file_and_parameterized_nodeid(tmp_path, selection):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_case.py").write_text(
        'import pytest\n@pytest.mark.parametrize("value", [1], ids=["route::case with spaces"])\n'
        "def test_case(value):\n    assert value == 1\n",
        encoding="utf-8",
    )
    result = await PytestRunner().run_suite(tmp_path, nodeids=[selection])
    assert result.exit_code == 0
    assert result.total == result.passed == 1


@pytest.mark.asyncio
async def test_real_runner_keeps_each_tests_error_and_trace_isolated(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_cases.py").write_text(
        """import pytest
def test_assertion():
    assert 1 == 2
def test_code():
    raise TypeError("missing required argument: quantity")
def test_network():
    raise ConnectionError("connection refused")
@pytest.fixture
def broken_teardown():
    yield 1
    raise RuntimeError("teardown failed")
def test_lifecycle(broken_teardown):
    assert broken_teardown == 1
""",
        encoding="utf-8",
    )
    result = await PytestRunner().run_suite(tmp_path)
    cases = {case.nodeid.split("::")[-1]: case for case in result.results}
    assert result.total == result.failed == 4
    assert "assert 1 == 2" in cases["test_assertion"].stack_trace
    assert (
        FailureClassifier.failure_kind(cases["test_assertion"].error_message, cases["test_assertion"].stack_trace)
        == "ASSERTION_FAILURE"
    )
    assert "missing required argument" in cases["test_code"].error_message
    assert "connection refused" not in cases["test_code"].stack_trace
    assert "connection refused" in cases["test_network"].error_message
    assert "teardown failed" in cases["test_lifecycle"].error_message
    assert all(case.duration_ms >= 0 for case in result.results)
