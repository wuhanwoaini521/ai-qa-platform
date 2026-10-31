"""Deterministic data-variable extraction for recorded browser steps.

Design notes (see .ai-runs/2026-11-01-overnight-product-improvement/oss-evaluation.md):

- No model call, no new runtime: the rules below are pure functions over recorded steps.
- Sensitive values keep their existing env-var path; this module never reads them.
- Generated tests must stay plain pytest functions (no parametrize), so variables become
  ``os.getenv("NAME", "default")`` defaults inside the test body.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_VARIABLES = 20
MIN_VALUE_LENGTH = 2


@dataclass(frozen=True)
class RecorderVariable:
    name: str
    default: str
    source: str  # "url" | "fill"
    step_id: str
    hint: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "default": self.default,
            "source": self.source,
            "step_id": self.step_id,
            "hint": self.hint,
        }


def _slug(text: str, fallback: str) -> str:
    letters = [character if character.isalnum() else "_" for character in text.strip().lower()]
    slug = "".join(letters).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    if not slug or not slug[0].isalpha():
        slug = f"{fallback}_{slug}".strip("_")
    return slug[:32].upper()


def _origin(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}"


def extract_variables(steps) -> list[RecorderVariable]:
    """Return bounded, deterministic variables for URL base and non-sensitive inputs."""
    variables: list[RecorderVariable] = []
    seen: dict[tuple[str, str], str] = {}

    def add(variable: RecorderVariable) -> None:
        key = (variable.source, variable.default)
        if key in seen or len(variables) >= MAX_VARIABLES:
            return
        seen[key] = variable.name
        variables.append(variable)

    base_origin = ""
    for step in steps:
        if getattr(step, "action", "") != "navigate":
            continue
        origin = _origin(getattr(step, "url", "") or "")
        if origin:
            base_origin = origin
            break
    if base_origin:
        add(RecorderVariable(name="QA_BASE_URL", default=base_origin, source="url", step_id="navigate"))

    index = 0
    for step in steps:
        if getattr(step, "action", "") not in {"fill", "select"}:
            continue
        if getattr(step, "value_redacted", False):
            continue  # handled by the existing secret env-var path
        value = getattr(step, "value", None)
        if not value or len(value.strip()) < MIN_VALUE_LENGTH:
            continue
        hint = (getattr(step, "description", "") or "").strip()
        if not hint and getattr(step, "locator", None) is not None:
            locator = step.locator
            hint = getattr(locator, "name", "") or getattr(locator, "test_id", "") or getattr(locator, "css", "")
        index += 1
        add(
            RecorderVariable(
                name=f"QA_DATA_{index}_{_slug(hint, 'value')}"[:48],
                default=value,
                source="fill",
                step_id=getattr(step, "id", ""),
                hint=hint[:80],
            )
        )
    return variables


def variable_for_fill(variables: list[RecorderVariable], step) -> RecorderVariable | None:
    for variable in variables:
        if variable.source == "fill" and variable.step_id == getattr(step, "id", ""):
            return variable
    return None


def split_origin(url: str) -> tuple[str, str] | None:
    origin = _origin(url)
    if not origin:
        return None
    return origin, url[len(origin) :]
