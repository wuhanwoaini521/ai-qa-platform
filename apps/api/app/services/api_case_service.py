"""Generate pytest API cases from a request spec.

The platform already runs pytest; an API case is therefore a small httpx test rather than a second
execution engine. Cases compile into the same workspace/run/evidence path as UI cases.

Principles borrowed from open-source API tooling (HttpRunner's case-as-code/HAR-to-case pipeline,
Bruno's file-based collections, Hoppscotch's request builder, Playwright's HAR capture): keep the
request explicit and reviewable, keep secrets in the environment, assert on the response contract,
and let the same runner own the verdict.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.services.recorder_service import split_origin

_SECRET_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
}


class ApiHeader(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    value: str = Field(default="", max_length=2000)


class ApiAssertion(BaseModel):
    kind: Literal["status", "json_path", "body_contains"]
    path: str | None = Field(default=None, max_length=200)
    expected: Any = None


class ApiCaseRequest(BaseModel):
    test_name: str = Field(default="api_case", min_length=1, max_length=120)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    url: str = Field(min_length=1, max_length=2048)
    headers: list[ApiHeader] = Field(default_factory=list, max_length=40)
    base_url: str | None = Field(default=None, max_length=2048)
    body: str | None = Field(default=None, max_length=20000)
    json_body: Any = None
    assertions: list[ApiAssertion] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_request(self):
        if self.body is not None and self.json_body is not None:
            raise ValueError("provide either a raw body or a JSON body, not both")
        if any(item.kind == "json_path" and not (item.path or "").strip() for item in self.assertions):
            raise ValueError("json_path assertions require a path")
        return self


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") or "api_case"


def _secret_env(name: str) -> str:
    return "QA_API_SECRET_" + re.sub(r"[^A-Za-z0-9]", "_", name.upper()).strip("_")


def _assertion_lines(assertions: list[ApiAssertion]) -> list[str]:
    lines: list[str] = []
    if not assertions:
        assertions = [ApiAssertion(kind="status", expected=200)]
    for assertion in assertions:
        if assertion.kind == "status":
            expected = int(assertion.expected or 200)
            lines.append(f"    assert response.status_code == {expected}, response.text[:500]")
        elif assertion.kind == "body_contains":
            lines.append(f"    assert {json.dumps(str(assertion.expected))} in response.text")
        else:
            expected = assertion.expected
            lines.append(
                f"    assert _value_at(response.json(), {json.dumps(assertion.path)}) == {json.dumps(expected)}"
            )
    return lines


def _request_call(request: ApiCaseRequest) -> tuple[list[str], str]:
    """Return (setup lines, httpx call arguments)."""
    setup: list[str] = []
    url = request.url.strip()
    origin, rest = split_origin(url) or ("", "")
    if origin:
        setup.append(f'    base = os.getenv("QA_BASE_URL", {json.dumps(origin)})')
        setup.append(f"    url = base + {json.dumps(rest)}")
    else:
        if not (request.base_url or "").strip():
            raise ValueError("relative URLs need a base_url (for example the project SUT address)")
        setup.append(f'    base = os.getenv("QA_BASE_URL", {json.dumps(request.base_url.strip())})')
        setup.append(f"    url = base + {json.dumps(url)}")

    headers: dict[str, tuple[bool, str]] = {}
    for header in request.headers:
        name = header.name.strip()
        if not name:
            continue
        if name.lower() in _SECRET_HEADERS:
            env = _secret_env(name)
            local = f"secret_{_safe_identifier(name).lower()}"
            setup.append(f"    {local} = os.getenv({json.dumps(env)})")
            setup.append(f"    if {local} is None: raise RuntimeError({json.dumps('Set environment variable ' + env)})")
            headers[name] = (True, local)
        else:
            headers[name] = (False, header.value)
    if headers:
        rendered = ", ".join(
            f"{json.dumps(name)}: {value if is_expression else json.dumps(value)}"
            for name, (is_expression, value) in headers.items()
        )
        setup.append(f"    headers = {{{rendered}}}")
    else:
        setup.append("    headers = {}")

    arguments = [f"{json.dumps(request.method)}", "url", "headers=headers", "timeout=30.0", "follow_redirects=True"]
    if request.json_body is not None:
        arguments.append(f"json={json.dumps(request.json_body, ensure_ascii=False)}")
    elif request.body is not None:
        arguments.append(f"content={json.dumps(request.body, ensure_ascii=False)}")
    return setup, ", ".join(arguments)


def compile_api_case(request: ApiCaseRequest) -> dict:
    test_name = _safe_identifier(request.test_name)
    if not test_name.startswith("test_"):
        test_name = "test_" + test_name
    setup, arguments = _request_call(request)
    lines = [
        "import json",
        "import os",
        "",
        "import httpx",
        "",
        "",
        "def _value_at(payload, path):",
        "    current = payload",
        "    for part in path.split('.'):",
        "        if part.endswith(']') and '[' in part:",
        "            name, index = part[:-1].split('[', 1)",
        "            if name:",
        "                current = current[name]",
        "            current = current[int(index)]",
        "        else:",
        "            current = current[part]",
        "    return current",
        "",
        "",
        f"def {test_name}():",
        *setup,
        f"    response = httpx.request({arguments})",
        *_assertion_lines(request.assertions),
        "",
    ]
    return {
        "code": "\n".join(lines),
        "test_name": test_name,
        "assertion_count": len(request.assertions) or 1,
    }
