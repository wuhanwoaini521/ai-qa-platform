"""Structured pytest collection and execution for an imported QA project.

Collection never reports "0 tests" for a broken project: a non-zero pytest exit status or an
unparsable report becomes an explicit COLLECTION_ERROR carrying the real diagnostics. Execution
distinguishes *physical attempts* from *logical tests* so a rerun is never counted as a second test.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from qa_core.onboarding.contract import QAProjectContract

#: `tests/unit/test_x.py::test_y` / `tests/unit/test_x.py::TestC::test_y[param-1]`
NODEID_LINE = re.compile(r"^(?P<nodeid>[^\s:]+\.py::[^\s]+)$")
#: `tests/unit/test_x.py::test_y PASSED [ 12%]`
VERBOSE_RESULT = re.compile(
    r"^(?P<nodeid>[^\s:]+\.py::[^\s]+)\s+(?P<outcome>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS|RERUN)\b"
)
#: `74 tests collected in 0.20s` / `12 tests collected, 2 errors in 1.2s`
COLLECT_SUMMARY = re.compile(r"^(?P<count>\d+) tests? collected.*?(?P<errors>\d+) errors?", re.MULTILINE)
COLLECT_SUMMARY_PLAIN = re.compile(r"^(?P<count>\d+) tests? collected")
COLLECT_ERROR_LINE = re.compile(r"^ERROR (?P<nodeid>[^\s]+)", re.MULTILINE)
SUMMARY_COUNTS = re.compile(
    r"(?P<count>\d+) (?P<kind>passed|failed|error|errors|skipped|xfailed|xpassed|rerun|reruns|warning|warnings|deselected)"
)
#: `FAILED tests/unit/test_x.py::test_y - AssertionError: assert 1 == 2`
FAILURE_SUMMARY_LINE = re.compile(r"^(?:FAILED|ERROR) (?P<nodeid>[^\s]+)(?: - (?P<message>.*))?$", re.MULTILINE)
#: `tests/unit/test_x.py::test_y` at the start of a traceback section
FAILURE_SECTION = re.compile(r"^_{5,} (?P<nodeid>[^\s]+) _{5,}$", re.MULTILINE)

#: Plugins whose output formatting would break parsing; disabling them never changes test outcomes.
PARSER_STABILITY_ARGS = ("-p", "no:sugar", "--no-header", "-p", "no:cacheprovider")


class CollectionStatus(str, Enum):
    COLLECTED = "COLLECTED"
    COLLECTION_ERROR = "COLLECTION_ERROR"
    TIMEOUT = "TIMEOUT"


class CollectedTest(BaseModel):
    nodeid: str
    file: str
    class_name: str | None = None
    test_name: str
    parameters: list[str] = Field(default_factory=list)

    @property
    def is_parameterised(self) -> bool:
        return bool(self.parameters)


class CollectionOutcome(BaseModel):
    status: CollectionStatus
    tests: list[CollectedTest] = Field(default_factory=list)
    test_file_count: int = 0
    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    duration_ms: float = 0.0
    error_type: str | None = None
    error_message: str | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""


class RunStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    XFAIL = "XFAIL"
    XPASS = "XPASS"
    NOT_RUN = "NOT_RUN"


class LogicalTestOutcome(BaseModel):
    nodeid: str
    status: RunStatus
    #: PASSED/FAILED/... lines observed for this nodeid (a rerun increases the count).
    attempts: int = 0
    reruns: int = 0
    failure_message: str | None = None

    @property
    def is_flaky_rerun(self) -> bool:
        return self.reruns > 0 and self.status is RunStatus.PASSED


class SuiteRunOutcome(BaseModel):
    exit_code: int | None
    command: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
    logical_tests: list[LogicalTestOutcome] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    #: Every PASSED/FAILED/... observation, i.e. what actually ran on the machine.
    physical_attempts: int = 0
    reruns_total: int = 0
    timed_out: bool = False
    stdout_tail: str = ""
    stderr_tail: str = ""

    @property
    def collected_count(self) -> int:
        return len(self.logical_tests)


class _ProcessResult(BaseModel):
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool


async def run_project_command(
    command: list[str],
    project_root: Path,
    interpreter: str,
    environment: dict[str, str] | None = None,
    timeout_sec: float = 300.0,
) -> _ProcessResult:
    """Run one platform-built command inside the project workspace with the project's interpreter."""
    resolved = [interpreter, *command[1:]] if command and command[0] in ("python", "python3") else list(command)
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env.update(environment or {})

    start = time.perf_counter()
    process = await asyncio.create_subprocess_exec(
        *resolved,
        cwd=str(project_root),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_sec)
        timed_out = False
    except asyncio.TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        timed_out = True

    return _ProcessResult(
        exit_code=None if timed_out else process.returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        duration_ms=(time.perf_counter() - start) * 1000,
        timed_out=timed_out,
    )


def parse_nodeid(nodeid: str) -> CollectedTest | None:
    file_part, _, remainder = nodeid.partition("::")
    if not file_part or not remainder:
        return None
    parameters: list[str] = []
    parts = remainder.split("::")
    test_part = parts[-1]
    class_name = parts[0] if len(parts) > 1 else None
    if "[" in test_part:
        test_name, _, params = test_part.partition("[")
        parameters = [param for param in params.rstrip("]").split("-") if param]
    else:
        test_name = test_part
    return CollectedTest(
        nodeid=nodeid,
        file=file_part,
        class_name=class_name,
        test_name=test_name,
        parameters=parameters,
    )


def parse_collection(stdout: str, stderr: str, exit_code: int | None) -> tuple[list[CollectedTest], str | None]:
    """Return (tests, error message). Never returns an empty list with no error for a failed run."""
    tests: list[CollectedTest] = []
    for line in stdout.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        match = NODEID_LINE.match(candidate)
        if not match:
            continue
        parsed = parse_nodeid(match.group("nodeid"))
        if parsed:
            tests.append(parsed)

    error: str | None = None
    if exit_code not in (0, None):
        error_lines = COLLECT_ERROR_LINE.findall(stdout) or []
        detail = "\n".join(line for line in stdout.splitlines()[-15:] if line.strip())
        error = (
            f"pytest exited with status {exit_code} during collection"
            + (f"; problem entries: {', '.join(error_lines[:5])}" if error_lines else "")
            + (f"\n{detail}" if detail else "")
        )
    elif not tests:
        summary = COLLECT_SUMMARY.search(stdout) or COLLECT_SUMMARY_PLAIN.search(stdout)
        error = "pytest collected 0 tests" + (f" (report: {summary.group(0)})" if summary else "")
    return tests, error


def parse_execution(stdout: str, stderr: str) -> tuple[list[LogicalTestOutcome], dict[str, int], int, int]:
    """Return (logical outcomes, summary counts, physical attempts, reruns)."""
    attempts_by_nodeid: dict[str, list[str]] = {}
    order: list[str] = []
    combined = f"{stdout}\n{stderr}"
    for line in combined.splitlines():
        match = VERBOSE_RESULT.match(line.strip())
        if not match:
            continue
        nodeid = match.group("nodeid")
        if nodeid not in attempts_by_nodeid:
            attempts_by_nodeid[nodeid] = []
            order.append(nodeid)
        attempts_by_nodeid[nodeid].append(match.group("outcome"))

    logical: list[LogicalTestOutcome] = []
    reruns_total = 0
    for nodeid in order:
        outcomes = attempts_by_nodeid[nodeid]
        reruns = sum(1 for outcome in outcomes if outcome == "RERUN")
        reruns_total += reruns
        decisive = next((outcome for outcome in reversed(outcomes) if outcome != "RERUN"), None)
        status = RunStatus(decisive) if decisive in {member.value for member in RunStatus} else RunStatus.NOT_RUN
        logical.append(
            LogicalTestOutcome(
                nodeid=nodeid,
                status=status,
                attempts=len(outcomes),
                reruns=reruns,
            )
        )

    counts: dict[str, int] = {}
    for match in SUMMARY_COUNTS.finditer(combined):
        kind = (
            match.group("kind").rstrip("s")
            if match.group("kind") in ("errors", "reruns", "warnings")
            else match.group("kind")
        )
        counts[kind] = int(match.group("count"))

    failure_messages = {
        match.group("nodeid"): (match.group("message") or "").strip()
        for match in FAILURE_SUMMARY_LINE.finditer(combined)
    }
    for outcome in logical:
        message = failure_messages.get(outcome.nodeid)
        if message:
            outcome.failure_message = message

    return logical, counts, sum(len(item) for item in attempts_by_nodeid.values()), reruns_total


class QAProjectCollector:
    """Runs structured collection against an imported project."""

    def __init__(self, contract: QAProjectContract, timeout_sec: float = 300.0) -> None:
        self.contract = contract
        self.timeout_sec = timeout_sec

    async def collect(self, project_root: Path, markers: list[str] | None = None) -> CollectionOutcome:
        command = [*self.contract.collect_command]
        if markers:
            command.extend(["-m", " or ".join(markers)])
        command.extend(PARSER_STABILITY_ARGS)
        interpreter = self.contract.runtime.resolve_interpreter(project_root)
        result = await run_project_command(
            command,
            project_root,
            interpreter,
            environment=self.contract.environment,
            timeout_sec=self.timeout_sec,
        )

        tests, error = parse_collection(result.stdout, result.stderr, result.exit_code)
        status = CollectionStatus.COLLECTED
        if result.timed_out:
            status = CollectionStatus.TIMEOUT
            error = error or f"collection timed out after {self.timeout_sec:.0f}s"
        elif error:
            status = CollectionStatus.COLLECTION_ERROR

        return CollectionOutcome(
            status=status,
            tests=tests,
            test_file_count=len({test.file for test in tests}),
            command=command,
            exit_code=result.exit_code,
            duration_ms=round(result.duration_ms, 2),
            error_type="pytest" if status is not CollectionStatus.COLLECTED else None,
            error_message=error,
            stdout_tail="\n".join(result.stdout.splitlines()[-30:]),
            stderr_tail="\n".join(result.stderr.splitlines()[-30:]),
        )


class QAProjectRunner:
    """Runs a bounded selection of an imported project's tests and parses the outcome."""

    def __init__(self, contract: QAProjectContract, timeout_sec: float = 900.0) -> None:
        self.contract = contract
        self.timeout_sec = timeout_sec

    async def run(
        self,
        project_root: Path,
        nodeids: list[str] | None = None,
        markers: list[str] | None = None,
        extra_args: list[str] | None = None,
    ) -> SuiteRunOutcome:
        command = self.contract.command_for_tests(nodeids=nodeids, markers=markers)
        command.extend(PARSER_STABILITY_ARGS)
        command.extend(extra_args or [])
        interpreter = self.contract.runtime.resolve_interpreter(project_root)
        result = await run_project_command(
            command,
            project_root,
            interpreter,
            environment=self.contract.environment,
            timeout_sec=self.timeout_sec,
        )
        logical, counts, physical_attempts, reruns_total = parse_execution(result.stdout, result.stderr)
        return SuiteRunOutcome(
            exit_code=result.exit_code,
            command=command,
            duration_ms=round(result.duration_ms, 2),
            logical_tests=logical,
            counts=counts,
            physical_attempts=physical_attempts,
            reruns_total=reruns_total,
            timed_out=result.timed_out,
            stdout_tail="\n".join(result.stdout.splitlines()[-60:]),
            stderr_tail="\n".join(result.stderr.splitlines()[-30:]),
        )
