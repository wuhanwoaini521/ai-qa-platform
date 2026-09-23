from __future__ import annotations

import re

from qa_core.failure.models import FailureCategory


class FailureClassifier:
    """Classifies test failure root causes into actionable taxonomy."""

    @classmethod
    def classify(cls, error_message: str, stack_trace: str = "") -> tuple[FailureCategory, str, str | None]:
        combined = f"{error_message}\n{stack_trace}".lower()

        # 1. Locator Changed / Not Found
        if any(
            kw in combined
            for kw in ["locator", "not found", "waiting for locator", "element not found", "nosuchelement"]
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
