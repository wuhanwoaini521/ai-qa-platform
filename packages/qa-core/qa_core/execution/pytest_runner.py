from __future__ import annotations

import asyncio
import os
import re
import time
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

    async def run_suite(
        self,
        workspace_dir: Path | str,
        nodeids: list[str] | None = None,
        markers: list[str] | None = None,
        environment: dict[str, str] | None = None,
    ) -> SuiteExecutionResult:
        ws_path = Path(workspace_dir).resolve()
        if not ws_path.exists():
            raise FileNotFoundError(f"Workspace directory not found: {ws_path}")

        cmd = ["pytest", "-v", "--tb=short"]
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

        start_time = time.perf_counter()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(ws_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.default_timeout_sec)
        except asyncio.TimeoutError:
            proc.kill()
            return SuiteExecutionResult(
                total=len(nodeids or []),
                failed=len(nodeids or []),
                duration_ms=(time.perf_counter() - start_time) * 1000,
                results=[],
                raw_logs=["Execution timed out after 120s."],
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        # Parse test outcomes line by line
        results: list[SingleTestResult] = []
        raw_logs: list[str] = (stdout_str + "\n" + stderr_str).splitlines()

        passed_count = 0
        failed_count = 0
        skipped_count = 0

        for line in raw_logs:
            # Pattern: tests/test_login.py::test_login_flow PASSED [100%]
            match = re.search(r"^(\S+::\S+)\s+(PASSED|FAILED|SKIPPED|ERROR)", line)
            if match:
                test_nodeid = match.group(1)
                verdict = match.group(2)
                status = (
                    TestExecutionStatus.PASSED
                    if verdict == "PASSED"
                    else (TestExecutionStatus.FAILED if verdict == "FAILED" else TestExecutionStatus.SKIPPED)
                )

                if status == TestExecutionStatus.PASSED:
                    passed_count += 1
                elif status == TestExecutionStatus.FAILED:
                    failed_count += 1
                else:
                    skipped_count += 1

                results.append(
                    SingleTestResult(
                        nodeid=test_nodeid,
                        status=status,
                        duration_ms=duration_ms / max(1, len(nodeids or [1])),
                        error_message=f"Test failed with {verdict}" if status == TestExecutionStatus.FAILED else None,
                        stack_trace=stdout_str if status == TestExecutionStatus.FAILED else None,
                    )
                )

        # Fallback if no specific nodeids matched but command completed
        if not results and nodeids:
            for nid in nodeids:
                status = TestExecutionStatus.PASSED if proc.returncode == 0 else TestExecutionStatus.FAILED
                if status == TestExecutionStatus.PASSED:
                    passed_count += 1
                else:
                    failed_count += 1
                results.append(
                    SingleTestResult(
                        nodeid=nid,
                        status=status,
                        duration_ms=duration_ms,
                        error_message=None if status == TestExecutionStatus.PASSED else stdout_str,
                    )
                )

        return SuiteExecutionResult(
            total=len(results),
            passed=passed_count,
            failed=failed_count,
            skipped=skipped_count,
            duration_ms=duration_ms,
            results=results,
            raw_logs=raw_logs,
        )
