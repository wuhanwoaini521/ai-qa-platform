from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path, PurePosixPath

from qa_core.execution.environment import project_subprocess_environment
from qa_core.execution.models import (
    SingleTestResult,
    SuiteExecutionResult,
    TestExecutionStatus,
)
from qa_core.onboarding.collector import parse_execution, parse_report_log
from qa_core.onboarding.pytest_plugin import write_plugin

logger = logging.getLogger("qa_core.execution.pytest_runner")


def validate_pytest_nodeids(workspace_dir: Path | str, nodeids: list[str]) -> list[str]:
    """Keep test selections inside their workspace and out of pytest's option parser."""
    root = Path(workspace_dir).resolve()
    validated = []
    for nodeid in nodeids or ["tests"]:
        file_part, separator, target = nodeid.strip().partition("::")
        file_part = file_part.replace("\\", "/")
        normalized = file_part + separator + target
        relative = PurePosixPath(file_part)
        if (
            not file_part
            or normalized.startswith(("-", "@"))
            or "\x00" in normalized
            or ":" in file_part
            or relative.is_absolute()
            or not (root / Path(*relative.parts)).resolve().is_relative_to(root)
        ):
            raise ValueError("Test selection must use a relative path inside the workspace, not pytest options.")
        validated.append(normalized)
    return validated if nodeids else []


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
        timeout_sec: float,
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
            await asyncio.wait_for(collect_output(), timeout=timeout_sec)
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
        timeout_sec: float | None = None,
    ) -> SuiteExecutionResult:
        execution_timeout = self.default_timeout_sec if timeout_sec is None else timeout_sec
        ws_path = Path(workspace_dir).resolve()
        if not ws_path.exists():
            raise FileNotFoundError(f"Workspace directory not found: {ws_path}")
        nodeids = validate_pytest_nodeids(ws_path, nodeids or [])

        # Run pytest through an explicit interpreter: an imported project must use its own virtualenv
        # (its dependencies, its Python version), not whichever pytest happens to be on PATH.
        cmd = [
            interpreter or sys.executable,
            "-u",
            "-m",
            "pytest",
            "-v",
            "-s",
            "--tb=short",
            f"--rootdir={ws_path}",
            f"--confcutdir={ws_path}",
        ]
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

        env = project_subprocess_environment(environment)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        report_runtime = tempfile.TemporaryDirectory(prefix="qa-pytest-report-")
        report_directory = Path(report_runtime.name)
        report_path = report_directory / "results.jsonl"
        # xdist workers must not scan the host's global pytest temp directory. Keeping worker temp
        # files alongside this run's structured report also makes local runs isolated and repeatable.
        cmd.append(f"--basetemp={report_directory / 'pytest-tmp'}")
        cmd.extend(["-p", write_plugin(report_directory)])
        env["QA_PLATFORM_REPORT_LOG"] = str(report_path)
        env["PYTHONPATH"] = str(report_directory) + os.pathsep + env.get("PYTHONPATH", "")
        structured_results = None
        failure_details = {}

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
                exit_code, timed_out = await self._run_in_thread(cmd, ws_path, env, raw_logs, on_log, execution_timeout)
            else:
                try:
                    await asyncio.wait_for(collect_output(), timeout=execution_timeout)
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
            try:
                if watch_task is not None:
                    watch_stop.set()
                    await watch_task
                structured_results = parse_report_log(report_path)
                for report_file in report_directory.glob("results.jsonl.*"):
                    for line in report_file.read_text(encoding="utf-8").splitlines():
                        try:
                            record = json.loads(line)
                            if record.get("outcome") == "failed":
                                failure_details[record["nodeid"]] = record
                        except (ValueError, KeyError, TypeError):
                            logger.warning("Ignoring malformed per-test report record")
            finally:
                report_runtime.cleanup()

        if timed_out:
            message = f"Execution timed out after {execution_timeout:g}s."
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

        logical, _, _, _ = parse_execution(stdout_str, "")
        if structured_results:
            structured, _, _ = structured_results
            if sum(item.status.value in {"FAILED", "ERROR"} for item in structured) >= sum(
                item.status.value in {"FAILED", "ERROR"} for item in logical
            ):
                logical = structured
        results = []
        for outcome in logical:
            status = (
                TestExecutionStatus.PASSED
                if outcome.status.value in {"PASSED", "XPASS"}
                else TestExecutionStatus.SKIPPED
                if outcome.status.value in {"SKIPPED", "XFAIL", "NOT_RUN"}
                else TestExecutionStatus.FAILED
            )
            detail = failure_details.get(outcome.nodeid, {})
            results.append(
                SingleTestResult(
                    nodeid=outcome.nodeid.replace("\\", "/"),
                    status=status,
                    duration_ms=(outcome.duration_ms or 0.0),
                    error_message=(
                        detail.get("error_message")
                        or outcome.failure_message
                        or "Failure details were not captured for this test."
                    )
                    if status == TestExecutionStatus.FAILED
                    else None,
                    stack_trace=detail.get("stack_trace") if status == TestExecutionStatus.FAILED else None,
                )
            )
        passed_count = sum(item.status == TestExecutionStatus.PASSED for item in results)
        failed_count = sum(item.status == TestExecutionStatus.FAILED for item in results)
        skipped_count = sum(item.status == TestExecutionStatus.SKIPPED for item in results)

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
