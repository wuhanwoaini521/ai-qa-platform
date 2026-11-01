from types import SimpleNamespace

import pytest
from app.services.api_case_service import ApiCaseRequest, compile_api_case
from app.services.recorder_service import BrowserRecorderService


def _code(request: ApiCaseRequest) -> str:
    result = compile_api_case(request)
    compile(result["code"], "api_case.py", "exec")
    return result["code"]


def test_get_case_keeps_path_and_status_assertion():
    code = _code(ApiCaseRequest(test_name="health", method="GET", url="http://127.0.0.1:8000/api/health?deep=1"))
    assert 'os.getenv("QA_BASE_URL", "http://127.0.0.1:8000")' in code
    assert '"/api/health?deep=1"' in code
    assert 'httpx.request("GET", url' in code
    assert "assert response.status_code == 200" in code


def test_post_json_with_json_path_assertion():
    code = _code(
        ApiCaseRequest(
            test_name="create_order",
            method="POST",
            url="/api/orders",
            base_url="http://127.0.0.1:8099",
            headers=[{"name": "content-type", "value": "application/json"}],
            json_body={"sku": "tee", "qty": 2},
            assertions=[
                {"kind": "status", "expected": 201},
                {"kind": "json_path", "path": "data.items[0].id", "expected": 7},
            ],
        )
    )
    assert 'json={"sku": "tee", "qty": 2}' in code
    assert 'headers = {"content-type": "application/json"}' in code
    assert "response.status_code == 201" in code
    assert '_value_at(response.json(), "data.items[0].id") == 7' in code


def test_secret_header_reads_environment_and_fails_loudly():
    code = _code(
        ApiCaseRequest(
            test_name="secured",
            method="GET",
            url="/api/private",
            base_url="http://127.0.0.1:8099",
            headers=[{"name": "Authorization", "value": "Bearer leak"}],
        )
    )
    assert "QA_API_SECRET_AUTHORIZATION" in code
    assert "Bearer leak" not in code
    assert "Set environment variable QA_API_SECRET_AUTHORIZATION" in code
    assert 'headers = {"Authorization": secret_authorization}' in code


def test_relative_url_requires_and_uses_base_url():
    with pytest.raises(ValueError, match="relative URLs need a base_url"):
        compile_api_case(ApiCaseRequest(test_name="info", method="GET", url="/api/info"))
    code = _code(ApiCaseRequest(test_name="info", method="GET", url="/api/info", base_url="http://127.0.0.1:8099"))
    assert 'os.getenv("QA_BASE_URL", "http://127.0.0.1:8099")' in code


def test_body_contains_assertion():
    code = _code(
        ApiCaseRequest(
            test_name="text",
            method="GET",
            url="/api/ping",
            base_url="http://127.0.0.1:8099",
            assertions=[{"kind": "body_contains", "expected": "pong"}],
        )
    )
    assert 'assert "pong" in response.text' in code


def test_conflicting_bodies_are_rejected():
    with pytest.raises(ValueError, match="either a raw body or a JSON body"):
        ApiCaseRequest(test_name="x", method="POST", url="/api/x", body="raw", json_body={"a": 1})


def test_json_path_assertion_requires_a_path():
    with pytest.raises(ValueError, match="require a path"):
        ApiCaseRequest(
            test_name="x",
            method="GET",
            url="/api/x",
            assertions=[{"kind": "json_path", "path": " ", "expected": 1}],
        )


def test_recorder_api_calls_filter_dedupe_and_redact():
    entry = {
        "url": "http://127.0.0.1:8099/api/info?token=secret",
        "method": "GET",
        "failed": False,
        "status": 200,
        "resource_type": "xhr",
        "request_headers": {"accept": "application/json"},
        "request_body": None,
        "response_headers": {"content-type": "application/json"},
    }
    session = SimpleNamespace(
        runtime_session=SimpleNamespace(
            network=[
                entry,
                dict(entry),
                {**entry, "url": "http://127.0.0.1:8099/app.js", "resource_type": "script"},
                {**entry, "url": "http://127.0.0.1:8099/api/fail", "status": 500, "failed": True},
            ]
        )
    )
    calls = BrowserRecorderService.api_calls(session)
    assert len(calls) == 2
    assert calls[0]["method"] == "GET"
    assert "token" not in calls[0]["url"]
    assert calls[0]["response_content_type"] == "application/json"
    assert {call["status"] for call in calls} == {200, 500}
