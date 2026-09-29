from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from pathlib import Path
from collections.abc import Awaitable, Callable

from qa_core.execution.models import (
    SingleTestResult,
    SuiteExecutionResult,
    TestExecutionStatus,
)


class PytestRunner:
    """Safe async subprocess execution runner for pytest suites."""

    def __init__(self, default_timeout_sec: float = 120.0) -> None:
        self.default_timeout_sec = default_timeout_sec

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
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(ws_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        raw_logs: list[str] = []

        async def collect_output() -> None:
            assert proc.stdout is not None
            while line := await proc.stdout.readline():
                decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
                raw_logs.append(decoded)
                if on_log:
                    await on_log(decoded + "\n")

        try:
            await asyncio.wait_for(collect_output(), timeout=self.default_timeout_sec)
            await proc.wait()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
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
            exit_code=proc.returncode,
            total=len(results),
            passed=passed_count,
            failed=failed_count,
            skipped=skipped_count,
            duration_ms=duration_ms,
            results=results,
            raw_logs=raw_logs,
        )
