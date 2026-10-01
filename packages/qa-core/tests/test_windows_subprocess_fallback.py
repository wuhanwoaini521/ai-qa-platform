import asyncio
import sys
import threading
from pathlib import Path

import pytest
from qa_core.execution.pytest_runner import PytestRunner
from qa_core.onboarding.collector import run_project_command


@pytest.mark.asyncio
async def test_pytest_and_collection_run_when_asyncio_subprocesses_are_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    async def unsupported_subprocess(*args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError("this event loop does not support subprocesses")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", unsupported_subprocess)

    collection = await run_project_command(
        ["python", "-c", "print('collected')"],
        tmp_path,
        sys.executable,
        timeout_sec=10,
    )
    assert collection.exit_code == 0
    assert "collected" in collection.stdout

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text("def test_passes():\n    assert True\n", encoding="utf-8")

    streamed_logs: list[str] = []

    async def on_log(line: str) -> None:
        streamed_logs.append(line)

    result = await PytestRunner(default_timeout_sec=30).run_suite(tmp_path, on_log=on_log)

    assert result.exit_code == 0
    assert result.passed == 1
    assert any("PASSED" in line for line in streamed_logs)


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", [False, True])
async def test_cancelling_pytest_kills_the_real_child_process_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fallback: bool,
):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(30)\n",
        encoding="utf-8",
    )
    original_kill = PytestRunner._kill_process_tree
    killed: list[int] = []

    def observe_kill(pid: int) -> None:
        killed.append(pid)
        original_kill(pid)

    monkeypatch.setattr(PytestRunner, "_kill_process_tree", staticmethod(observe_kill))
    import qa_core.execution.pytest_runner as runner_module

    process_started = threading.Event()
    if fallback:

        async def unsupported_subprocess(*args, **kwargs):  # noqa: ANN002, ANN003
            raise NotImplementedError("exercise Windows selector-loop fallback")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", unsupported_subprocess)
        original_popen = runner_module.subprocess.Popen

        def observe_popen(*args, **kwargs):  # noqa: ANN002, ANN003
            process = original_popen(*args, **kwargs)
            process_started.set()
            return process

        monkeypatch.setattr(runner_module.subprocess, "Popen", observe_popen)
    else:
        original_create = asyncio.create_subprocess_exec

        async def observe_create(*args, **kwargs):  # noqa: ANN002, ANN003
            process = await original_create(*args, **kwargs)
            process_started.set()
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", observe_create)

    run = asyncio.create_task(PytestRunner(default_timeout_sec=60).run_suite(tmp_path))
    assert await asyncio.to_thread(process_started.wait, 15)
    await asyncio.sleep(0.4)
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert killed


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", [False, True])
async def test_pytest_log_callback_error_kills_the_child_process_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fallback: bool,
):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(30)\n",
        encoding="utf-8",
    )
    original_kill = PytestRunner._kill_process_tree
    killed: list[int] = []

    def observe_kill(pid: int) -> None:
        killed.append(pid)
        original_kill(pid)

    monkeypatch.setattr(PytestRunner, "_kill_process_tree", staticmethod(observe_kill))

    if fallback:

        async def unsupported_subprocess(*args, **kwargs):  # noqa: ANN002, ANN003
            raise NotImplementedError("exercise Windows selector-loop fallback")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", unsupported_subprocess)

    async def reject_log(_line: str) -> None:
        raise RuntimeError("log stream disconnected")

    with pytest.raises(RuntimeError, match="log stream disconnected"):
        await PytestRunner(default_timeout_sec=60).run_suite(tmp_path, on_log=reject_log)

    assert killed
