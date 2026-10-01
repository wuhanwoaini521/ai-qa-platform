from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from qa_core.execution.models import (
    SingleTestResult,
    SuiteExecutionResult,
    TestExecutionStatus,
)

logger = logging.getLogger("qa_core.execution.pytest_runner")


class PytestRunner:
    """Safe async subprocess execution runner for pytest suites."""

    def __init__(self, default_timeout_sec: float = 120.0) -> None:
        self.default_timeout_sec = default_timeout_sec

    @staticmethod
    def _kill_process_tree(pid: int) -> None:
        """Stop pytest and any browser/helper processes it started."""
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                return
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(pid, signal.SIGKILL)
                return
            except (OSError, ProcessLookupError):
                pass

    async def _run_in_thread(
        self,
        cmd: list[str],
        workspace: Path,
        env: dict[str, str],
        raw_logs: list[str],
        on_log: Callable[[str], Awaitable[None]] | None,
    ) -> tuple[int | None, bool]:
        """Stream a child process from a worker thread on Windows selector loops."""
        loop = asyncio.get_running_loop()
        output: asyncio.Queue[str | None] = asyncio.Queue()
        process = subprocess.Popen(
            cmd,
            cwd=str(workspace),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        assert process.stdout is not None
        process_holder: dict[str, int | BaseException] = {}

        def pump_output() -> None:
            try:
                for line in process.stdout:
                    loop.call_soon_threadsafe(output.put_nowait, line.rstrip("\r\n"))
                process_holder["exit_code"] = process.wait()
            except BaseException as error:
                process_holder["error"] = error
            finally:
                loop.call_soon_threadsafe(output.put_nowait, None)

        thread = threading.Thread(target=pump_output, daemon=True)
        thread.start()

        async def collect_output() -> None:
            while (line := await output.get()) is not None:
                raw_logs.append(line)
                if on_log:
                    await on_log(line + "\n")

        try:
            await asyncio.wait_for(collect_output(), timeout=self.default_timeout_sec)
        except asyncio.TimeoutError:
            await asyncio.to_thread(self._kill_process_tree, process.pid)
            if process.poll() is None:
                process.kill()
            await asyncio.to_thread(thread.join)
            return None, True
        except asyncio.CancelledError:
            await asyncio.to_thread(self._kill_process_tree, process.pid)
            if process.poll() is None:
                process.kill()
            await asyncio.to_thread(thread.join)
            raise
        except BaseException:
            await asyncio.to_thread(self._kill_process_tree, process.pid)
            if process.poll() is None:
                process.kill()
            await asyncio.to_thread(thread.join)
            raise

        await asyncio.to_thread(thread.join)
        error = process_holder.get("error")
        if isinstance(error, BaseException):
            raise error
        exit_code = process_holder.get("exit_code")
        assert isinstance(exit_code, int)
        return exit_code, False

    async def run_suite(
        self,
        workspace_dir: Path | str,
        nodeids: list[str] | None = None,
        markers: list[str] | None = None,
        environment: dict[str, str] | None = None,
        interpreter: str | None = None,
        on_log: Callable[[str], Awaitable[None]] | None = None,
        browser_event_path: Path | str | None = None,
        on_browser_event: Callable[[dict], Awaitable[None]] | None = None,
        extra_pytest_args: list[str] | None = None,
        parallel_workers: int = 1,
    ) -> SuiteExecutionResult:
        ws_path = Path(workspace_dir).resolve()
        if not ws_path.exists():
            raise FileNotFoundError(f"Workspace directory not found: {ws_path}")

        # Run pytest through an explicit interpreter: an imported project must use its own virtualenv
        # (its dependencies, its Python version), not whichever pytest happens to be on PATH.
        cmd = [interpreter or sys.executable, "-u", "-m", "pytest", "-v", "-s", "--tb=short"]
        if parallel_workers > 1:
            cmd.extend(["-n", str(min(parallel_workers, 16))])
        if extra_pytest_args:
            cmd.extend(extra_pytest_args)
        if markers:
            for m in markers:
                cmd.extend(["-m", m])
        if nodeids:
            cmd.extend(nodeids)
        else:
            cmd.append("tests")

        env = dict(os.environ)
        if environment:
            env.update(environment)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        start_time = time.perf_counter()
        raw_logs: list[str] = []

        async def collect_output() -> None:
            assert proc.stdout is not None
            while line := await proc.stdout.readline():
                decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
                raw_logs.append(decoded)
                if on_log:
                    await on_log(decoded + "\n")

        watch_stop = asyncio.Event()
        watch_task = None
        if browser_event_path is not None and on_browser_event is not None:
            watch_task = asyncio.create_task(
                self._watch_browser_events(Path(browser_event_path), on_browser_event, watch_stop),
                name="pytest-live-browser-events",
            )
        try:
            try:
                process_options = {
                    "cwd": str(ws_path),
                    "env": env,
                    "stdout": asyncio.subprocess.PIPE,
                    "stderr": asyncio.subprocess.STDOUT,
                }
                if os.name == "nt":
                    process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    process_options["start_new_session"] = True
                proc = await asyncio.create_subprocess_exec(*cmd, **process_options)
            except NotImplementedError:
                # Uvicorn uses a selector loop on Windows, which cannot create subprocess transports.
                exit_code, timed_out = await self._run_in_thread(cmd, ws_path, env, raw_logs, on_log)
            else:
                try:
                    await asyncio.wait_for(collect_output(), timeout=self.default_timeout_sec)
                    await proc.wait()
                except asyncio.TimeoutError:
                    await asyncio.to_thread(self._kill_process_tree, proc.pid)
                    if proc.returncode is None:
                        proc.kill()
                    await proc.wait()
                    timed_out = True
                except asyncio.CancelledError:
                    await asyncio.to_thread(self._kill_process_tree, proc.pid)
                    if proc.returncode is None:
                        proc.kill()
                    await proc.wait()
                    raise
                except BaseException:
                    await asyncio.to_thread(self._kill_process_tree, proc.pid)
                    if proc.returncode is None:
                        proc.kill()
                    await proc.wait()
                    raise
                else:
                    timed_out = False
                exit_code = proc.returncode if not timed_out else None
        finally:
            if watch_task is not None:
                watch_stop.set()
                await watch_task

        if timed_out:
            message = f"Execution timed out after {self.default_timeout_sec:g}s."
            raw_logs.append(message)
            if on_log:
                await on_log(message + "\n")
            return SuiteExecutionResult(
                exit_code=None,
                total=len(nodeids or []),
                failed=len(nodeids or []),
                duration_ms=(time.perf_counter() - start_time) * 1000,
                results=[],
                raw_logs=raw_logs,
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        stdout_str = "\n".join(raw_logs)

        # Parse test outcomes line by line
        results: list[SingleTestResult] = []

        passed_count = 0
        failed_count = 0
        skipped_count = 0
        pending_nodeid: str | None = None

        for line in raw_logs:
            # Pattern: tests/test_login.py::test_login_flow PASSED [100%]
            match = re.search(r"^(\S+::\S+)\s+(PASSED|FAILED|SKIPPED|ERROR)", line)
            if match:
                test_nodeid, verdict = match.group(1), match.group(2)
            else:
                # pytest-xdist prefixes each result with its worker ID and moves the verdict
                # before the node ID, for example: [gw0] PASSED tests/test_login.py::test_login.
                worker_match = re.search(r"^\[[^\]]+\]\s+(PASSED|FAILED|SKIPPED|ERROR)\s+(\S+::\S+)", line)
                if worker_match:
                    verdict, test_nodeid = worker_match.group(1), worker_match.group(2)
                    pending_nodeid = None
                else:
                    # With -s, a test's print() can appear after its nodeid and pytest may
                    # write the verdict alone on a later line (including across stream chunks).
                    node_line = re.match(r"^(\S+::\S+)(?:\s|$)", line)
                    if node_line and not line.startswith(("FAILED ", "ERROR ")):
                        pending_nodeid = node_line.group(1)
                    verdict_line = re.match(r"^(PASSED|FAILED|SKIPPED|ERROR)(?:\s|$)", line)
                    if verdict_line and pending_nodeid:
                        test_nodeid, verdict = pending_nodeid, verdict_line.group(1)
                    else:
                        continue
            pending_nodeid = None
            if test_nodeid:
                status = (
                    TestExecutionStatus.PASSED
                    if verdict == "PASSED"
                    else (TestExecutionStatus.SKIPPED if verdict == "SKIPPED" else TestExecutionStatus.FAILED)
                )

                if status == TestExecutionStatus.PASSED:
                    passed_count += 1
                elif status == TestExecutionStatus.FAILED:
                    failed_count += 1
                else:
                    skipped_count += 1

                error_line = next(
                    (entry.strip() for entry in raw_logs if entry.startswith("E   ")),
                    f"Test failed with {verdict}",
                )
                results.append(
                    SingleTestResult(
                        nodeid=test_nodeid.replace("\\", "/"),
                        status=status,
                        duration_ms=0,
                        error_message=error_line if status == TestExecutionStatus.FAILED else None,
                        stack_trace=stdout_str if status == TestExecutionStatus.FAILED else None,
                    )
                )

        estimated_case_duration_ms = duration_ms / max(1, len(results))
        for result in results:
            result.duration_ms = estimated_case_duration_ms

        return SuiteExecutionResult(
            exit_code=exit_code,
            total=len(results),
            passed=passed_count,
            failed=failed_count,
            skipped=skipped_count,
            duration_ms=duration_ms,
            results=results,
            raw_logs=raw_logs,
        )

    @staticmethod
    async def _watch_browser_events(
        path_prefix: Path,
        on_browser_event: Callable[[dict], Awaitable[None]],
        stop: asyncio.Event,
    ) -> None:
        """Tail per-xdist-worker telemetry files without passing image payloads through pytest logs."""
        offsets: dict[Path, int] = {}
        buffers: dict[Path, bytes] = {}

        async def drain() -> None:
            for path in path_prefix.parent.glob(path_prefix.name + ".*"):
                try:
                    offset = offsets.get(path, 0)
                    with path.open("rb") as stream:
                        stream.seek(offset)
                        chunk = stream.read()
                    if not chunk:
                        continue
                    offsets[path] = offset + len(chunk)
                    data = buffers.get(path, b"") + chunk
                    lines = data.split(b"\n")
                    buffers[path] = lines.pop()
                    for line in lines:
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                            if isinstance(event, dict):
                                try:
                                    await on_browser_event(event)
                                except Exception as error:  # telemetry must not fail a test process
                                    logger.warning("Live browser callback failed (%s)", type(error).__name__)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            logger.warning("Ignoring malformed live browser telemetry from %s", path.name)
                except OSError:
                    continue

        while not stop.is_set():
            await drain()
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
        await drain()
