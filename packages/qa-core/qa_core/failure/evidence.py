"""One bounded, redacted failure evidence contract for Python, API and browser tests."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from qa_core.failure.redactor import SensitiveRedactor


class FailureEvidenceBundle(BaseModel):
    version: str = "v1.0"
    nodeid: str
    failure_kind: str
    error: str
    traceback: str = ""
    assertion: str = ""
    stdout: str = ""
    stderr: str = ""
    page_url: str = ""
    failing_locator: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    console: list[Any] = Field(default_factory=list)
    network: list[Any] = Field(default_factory=list)
    recent_steps: list[Any] = Field(default_factory=list)
    controls: list[Any] = Field(default_factory=list)
    source_context: str = ""
    context_paths: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)

    def render(self, limit: int = 24000) -> str:
        # Sections retain provenance when limited; missing evidence remains explicit.
        sections = []
        remaining = limit
        values = self.model_dump()
        ordered = {"missing": values.pop("missing"), **values}
        for key, value in ordered.items():
            text = SensitiveRedactor.redact_text(json.dumps(value, ensure_ascii=False))
            section = f"{key}: {text}"
            if len(section) > remaining:
                suffix = " [context limited]"
                section = (section[: max(0, remaining - len(suffix))] + suffix)[:remaining]
                sections.append(section)
                break
            sections.append(section)
            remaining -= len(section) + 1
            if remaining <= 0:
                break
        return "\n".join(sections)
