from pathlib import Path

import pytest
from qa_core.execution.pytest_runner import PytestRunner
from qa_core.failure.classifier import FailureClassifier


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
