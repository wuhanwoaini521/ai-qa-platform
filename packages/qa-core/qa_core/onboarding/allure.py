"""Allure result import.

Allure is a reporting format, not the platform's source of truth: imported results are attached to
the platform's own execution records as evidence. Nothing here decides a verdict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

#: Allure writes one `*-result.json` per test and `*-container.json` for fixtures/steps.
RESULT_GLOB = "*-result.json"
CONTAINER_GLOB = "*-container.json"

STATUS_MAP = {
    "passed": "PASSED",
    "failed": "FAILED",
    "broken": "ERROR",
    "skipped": "SKIPPED",
    "unknown": "SKIPPED",
}


class AllureAttachment(BaseModel):
    name: str
    source: str | None = None
    content_type: str | None = None


class AllureTestCaseResult(BaseModel):
    """The subset of an Allure result the platform cares about."""

    uuid: str | None = None
    history_id: str | None = None
    test_case_id: str | None = None
    full_name: str | None = None
    name: str | None = None
    status: str | None = None
    platform_status: str = "SKIPPED"
    start: int | None = None
    stop: int | None = None
    duration_ms: float | None = None
    suite: str | None = None
    parent_suite: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, str] = Field(default_factory=dict)
    attachments: list[AllureAttachment] = Field(default_factory=list)


class AllureImportReport(BaseModel):
    results_dir: str
    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    results: list[AllureTestCaseResult] = Field(default_factory=list)
    containers: int = 0
    skipped_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AllureResultImporter:
    """Reads an `allure-results` directory into platform-side records."""

    def __init__(self, max_results: int = 5000) -> None:
        self.max_results = max_results

    def import_from(self, results_dir: Path | str) -> AllureImportReport:
        directory = Path(results_dir)
        if not directory.is_dir():
            raise NotADirectoryError(f"Allure results directory not found: {directory}")

        report = AllureImportReport(results_dir=str(directory))
        for path in sorted(directory.glob(RESULT_GLOB))[: self.max_results]:
            try:
                payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                report.skipped_files.append(path.name)
                continue

            result = self._to_result(payload)
            report.results.append(result)
            report.by_status[result.platform_status] = report.by_status.get(result.platform_status, 0) + 1

        report.total = len(report.results)
        report.containers = len(list(directory.glob(CONTAINER_GLOB)))
        if report.skipped_files:
            report.warnings.append(f"{len(report.skipped_files)} unreadable Allure result files were skipped")
        if report.total == 0:
            report.warnings.append(
                "no Allure results found: the project may not run with --alluredir, or the directory is empty"
            )
        return report

    def _to_result(self, payload: dict[str, Any]) -> AllureTestCaseResult:
        labels = {
            str(label.get("name")): str(label.get("value"))
            for label in payload.get("labels", [])
            if label.get("name") is not None
        }
        parameters = {
            str(parameter.get("name")): str(parameter.get("value"))
            for parameter in payload.get("parameters", [])
            if parameter.get("name") is not None
        }
        attachments = [
            AllureAttachment(
                name=str(attachment.get("name", "")),
                source=attachment.get("source"),
                content_type=attachment.get("type"),
            )
            for attachment in payload.get("attachments", [])
        ]
        start = payload.get("start")
        stop = payload.get("stop")
        duration = (stop - start) if isinstance(start, int) and isinstance(stop, int) else None
        status = str(payload.get("status", "unknown")).lower()

        return AllureTestCaseResult(
            uuid=payload.get("uuid"),
            history_id=payload.get("historyId"),
            test_case_id=payload.get("testCaseId"),
            full_name=payload.get("fullName"),
            name=payload.get("name"),
            status=status,
            platform_status=STATUS_MAP.get(status, "SKIPPED"),
            start=start,
            stop=stop,
            duration_ms=duration,
            suite=labels.get("suite"),
            parent_suite=labels.get("parentSuite"),
            labels=labels,
            parameters=parameters,
            attachments=attachments,
        )
