from pathlib import Path

import pytest
from qa_core.execution.pytest_runner import PytestRunner


@pytest.mark.asyncio
async def test_checked_in_quickstart_runs_and_reports_each_test():
    example_dir = Path(__file__).resolve().parents[3] / "examples" / "quickstart"

    result = await PytestRunner().run_suite(example_dir)

    assert result.exit_code == 0, "\n".join(result.raw_logs)
    assert result.passed == result.total == 6
    assert {test.nodeid for test in result.results} == {
        "tests/test_cart.py::test_cart_total_for_multiple_items",
        "tests/test_cart.py::test_cart_total_for_empty_cart",
        "tests/test_cart.py::test_cart_rejects_invalid_quantity",
        "tests/test_login.py::test_login_flow",
        "tests/test_login.py::test_login_invalid_password",
        "tests/test_login.py::test_login_unknown_user",
    }


@pytest.mark.asyncio
async def test_streamed_print_output_keeps_the_real_pytest_verdict(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_progress.py").write_text(
        "def test_progress():\n    print('STEP 1', flush=True)\n    print('STEP 2', flush=True)\n    assert True\n",
        encoding="utf-8",
    )
    streamed: list[str] = []

    async def on_log(chunk: str) -> None:
        streamed.append(chunk)

    result = await PytestRunner().run_suite(tmp_path, on_log=on_log)

    assert result.exit_code == 0
    assert result.total == result.passed == 1
    assert result.results[0].nodeid.replace("\\", "/") == "tests/test_progress.py::test_progress"
    assert "STEP 1" in "".join(streamed)


@pytest.mark.asyncio
async def test_timeout_is_recorded_as_an_error_instead_of_a_pass(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_slow.py").write_text(
        "import time\ndef test_slow():\n    time.sleep(2)\n    assert True\n",
        encoding="utf-8",
    )

    result = await PytestRunner(default_timeout_sec=0.2).run_suite(tmp_path, nodeids=["tests/test_slow.py::test_slow"])

    assert result.exit_code is None
    assert result.results == []
    assert any("timed out" in line for line in result.raw_logs)


@pytest.mark.asyncio
async def test_run_timeout_can_be_extended_for_a_long_running_task(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_slow.py").write_text(
        "import time\ndef test_slow():\n    time.sleep(0.4)\n    assert True\n",
        encoding="utf-8",
    )

    result = await PytestRunner(default_timeout_sec=0.1).run_suite(
        tmp_path,
        nodeids=["tests/test_slow.py::test_slow"],
        timeout_sec=3,
    )

    assert result.exit_code == 0
    assert result.passed == result.total == 1
