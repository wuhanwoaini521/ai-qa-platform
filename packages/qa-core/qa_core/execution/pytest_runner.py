from __future__ import annotations

import asyncio
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
    ) -> SuiteExecutionResult:
        ws_path = Path(workspace_dir).resolve()
        if not ws_path.exists():
            raise FileNotFoundError(f"Workspace directory not found: {ws_path}")

        # Run pytest through an explicit interpreter: an imported project must use its own virtualenv
        # (its dependencies, its Python version), not whichever pytest happens to be on PATH.
        cmd = [interpreter or sys.executable, "-u", "-m", "pytest", "-v", "-s", "--tb=short"]
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
            else:
                timed_out = False
            exit_code = proc.returncode if not timed_out else None

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
                        duration_ms=duration_ms / max(1, len(nodeids or [1])),
                        error_message=error_line if status == TestExecutionStatus.FAILED else None,
                        stack_trace=stdout_str if status == TestExecutionStatus.FAILED else None,
                    )
                )

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
