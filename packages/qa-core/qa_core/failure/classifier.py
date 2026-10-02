from __future__ import annotations

import re

from qa_core.failure.models import FailureCategory


class FailureClassifier:
    """Classifies test failure root causes into actionable taxonomy."""

    @classmethod
    def classify(cls, error_message: str, stack_trace: str = "") -> tuple[FailureCategory, str, str | None]:
        exceptions = [
            line.strip()
            for line in stack_trace.splitlines()
            if re.match(r"^(?:E\s+)?(?:[\w.]+(?:Error|Exception)|Error):", line.strip())
        ]
        exception_text = "\n".join(exceptions[-3:])
        combined = f"{error_message}\n{exception_text}".lower()

        # Classify the current assertion itself before incidental locator names in the traceback.
        if "assertionerror" in error_message.lower() or re.search(r"(?:^|\n)\s*(?:E\s+)?assert\b", error_message):
            return (
                FailureCategory.ASSERTION_FAILURE,
                "State or attribute did not match expected test assertion.",
                None,
            )

        # Inspect the current exception before incidental library names in a traceback.
        current = combined
        rules = (
            (FailureCategory.PAGE_CRASH, ("page crashed", "targetcrashed", "pagecrash"), "Browser page crashed."),
            (
                FailureCategory.INFRASTRUCTURE_ERROR,
                ("worker lost", "worker unavailable", "disk full", "no space left", "database is locked"),
                "Execution infrastructure failed.",
            ),
            (
                FailureCategory.TEST_DATA_ERROR,
                ("fixture not found", "fixture '", "test data missing", "invalid test data"),
                "Test data or fixture setup failed.",
            ),
            (
                FailureCategory.ENVIRONMENT_ERROR,
                (
                    "modulenotfounderror",
                    "importerror",
                    "filenotfounderror",
                    "permissionerror",
                    "browser executable",
                    "executable doesn't exist",
                ),
                "A test environment dependency or permission is unavailable.",
            ),
            (
                FailureCategory.NETWORK_ERROR,
                (
                    "httperror",
                    "httpstatuserror",
                    "connecterror",
                    "connectionerror",
                    "networkerror",
                    "econnrefused",
                    "connection refused",
                    "502 bad gateway",
                    "500 internal",
                ),
                "An API or network request failed.",
            ),
            (
                FailureCategory.CODE_ERROR,
                (
                    "typeerror",
                    "nameerror",
                    "attributeerror",
                    "syntaxerror",
                    "zerodivisionerror",
                    "keyerror",
                    "indexerror",
                    "valueerror",
                    "unboundlocalerror",
                ),
                "Python code raised an exception.",
            ),
        )
        for category, patterns, explanation in rules:
            if any(pattern in current for pattern in patterns):
                return category, explanation, None

        # 1. Locator Changed / Not Found
        if any(
            kw in combined
            for kw in [
                "locator",
                "strict mode violation",
                "element is not attached",
                "element not found",
                "nosuchelement",
            ]
        ):
            locator_match = re.search(r"(?i)locator\(['\"](.*?)['\"]\)", error_message)
            failing_loc = locator_match.group(1) if locator_match else None
            return (
                FailureCategory.LOCATOR_CHANGED,
                "Target web element locator could not be resolved in the DOM.",
                failing_loc,
            )

        # 2. Timing / Timeout
        if any(kw in combined for kw in ["timeouterror", "timed out", "timeout 30000ms", "timeout 5000ms"]):
            return (
                FailureCategory.TIMING_ISSUE,
                "Action or navigation timed out before condition was met.",
                None,
            )

        # 3. Assertion Failure
        if any(kw in combined for kw in ["assertionerror", "expect(", "assert "]):
            return (
                FailureCategory.ASSERTION_FAILURE,
                "State or attribute did not match expected test assertion.",
                None,
            )

        # 4. Environment / Network
        if any(
            kw in combined
            for kw in ["connection refused", "econnrefused", "502 bad gateway", "500 internal", "networkerror"]
        ):
            return (
                FailureCategory.ENVIRONMENT_ERROR,
                "Target server or test environment returned network/connection error.",
                None,
            )

        return FailureCategory.UNKNOWN, "Unclassified failure.", None

    @classmethod
    def failure_kind(cls, error_message: str, stack_trace: str = "") -> str:
        category, _, _ = cls.classify(error_message, stack_trace)
        return {FailureCategory.LOCATOR_CHANGED: "LOCATOR_ERROR", FailureCategory.TIMING_ISSUE: "TIMEOUT_ERROR"}.get(
            category, category.value
        )
