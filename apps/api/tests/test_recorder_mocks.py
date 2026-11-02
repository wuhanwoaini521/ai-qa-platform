from types import SimpleNamespace

from app.services.recorder_service import (
    BrowserRecorderService,
    RecorderGenerateRequest,
    RecorderStep,
    generate_python_case,
)


def test_generated_case_replays_captured_responses():
    request = RecorderGenerateRequest(
        test_name="test_replay",
        steps=[RecorderStep(action="navigate", url="http://127.0.0.1:8099/new/")],
        mock_responses=[
            {
                "url": "**/api/info",
                "method": "GET",
                "status": 200,
                "headers": {"content-type": "application/json"},
                "body": '{"ok": true, "service": "replayed"}',
            }
        ],
    )
    code = generate_python_case(request)
    compile(code, "generated.py", "exec")
    assert "page.route(" in code
    assert "lambda route, request, m=mock" in code
    assert "**/api/info" in code
    assert "replayed" in code


def test_generated_case_has_no_routes_without_mocks():
    code = generate_python_case(
        RecorderGenerateRequest(
            test_name="test_plain",
            steps=[RecorderStep(action="navigate", url="http://127.0.0.1:8099/new/")],
        )
    )
    assert "page.route(" not in code


def test_api_calls_include_captured_response_body():
    session = SimpleNamespace(
        runtime_session=SimpleNamespace(
            network=[
                {
                    "url": "http://127.0.0.1:8099/api/info",
                    "method": "GET",
                    "status": 200,
                    "resource_type": "fetch",
                    "request_headers": {"accept": "application/json"},
                    "response_headers": {"content-type": "application/json"},
                    "response_body": '{"ok": true}',
                }
            ]
        )
    )
    calls = BrowserRecorderService.api_calls(session)
    assert calls[0]["response_body"] == '{"ok": true}'
