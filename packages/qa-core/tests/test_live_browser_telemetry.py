from pathlib import Path

import pytest
from qa_core.execution.live_browser_plugin import LIVE_BROWSER_PLUGIN_SOURCE
from qa_core.execution.pytest_runner import PytestRunner


def test_generated_live_browser_plugin_source_compiles():
    compile(LIVE_BROWSER_PLUGIN_SOURCE, "qa_platform_live_browser_plugin.py", "exec")


@pytest.mark.asyncio
async def test_runner_tails_live_browser_events_from_a_test_worker(tmp_path: Path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_sample.py").write_text("def test_sample():\n    assert True\n", encoding="utf-8")
    (tmp_path / "qa_live_test_plugin.py").write_text(
        "import json, os\n"
        "def pytest_runtest_setup(item):\n"
        "    path = os.environ['QA_PLATFORM_LIVE_BROWSER_LOG'] + '.main'\n"
        "    with open(path, 'a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps({'type': 'session.started', 'worker_id': 'main', 'nodeid': item.nodeid}) + '\\n')\n"
        "        handle.flush()\n",
        encoding="utf-8",
    )
    telemetry_path = tmp_path / "live-events"
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    result = await PytestRunner().run_suite(
        tmp_path,
        nodeids=["tests/test_sample.py::test_sample"],
        environment={"PYTHONPATH": str(tmp_path), "QA_PLATFORM_LIVE_BROWSER_LOG": str(telemetry_path)},
        browser_event_path=telemetry_path,
        on_browser_event=on_event,
        extra_pytest_args=["-p", "qa_live_test_plugin"],
    )

    assert result.exit_code == 0, "\n".join(result.raw_logs)
    assert any(event.get("type") == "session.started" and event.get("worker_id") == "main" for event in events)


@pytest.mark.asyncio
async def test_runner_parses_pytest_xdist_worker_results(tmp_path: Path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_parallel.py").write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('case', ['a', 'b', 'c'])\n"
        "def test_case(case):\n"
        "    assert case in {'a', 'b', 'c'}\n",
        encoding="utf-8",
    )

    result = await PytestRunner().run_suite(
        tmp_path,
        nodeids=["tests/test_parallel.py::test_case"],
        environment={"TMP": str(tmp_path), "TEMP": str(tmp_path)},
        parallel_workers=3,
    )

    assert result.exit_code == 0, "\n".join(result.raw_logs)
    assert result.total == 3
    assert result.passed == 3
    assert {item.nodeid for item in result.results} == {
        "tests/test_parallel.py::test_case[a]",
        "tests/test_parallel.py::test_case[b]",
        "tests/test_parallel.py::test_case[c]",
    }
