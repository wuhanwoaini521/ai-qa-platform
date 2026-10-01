from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from app.persistence.models import utc_now
from app.services.debug_session_service import DebugSessionService, validate_debug_nodeid
from project_model.models import Breakpoint


async def _wait_message(session, predicate, backlog: list[dict[str, Any]], timeout: float = 20) -> dict[str, Any]:
    for index, message in enumerate(backlog):
        if predicate(message):
            return backlog.pop(index)
    while True:
        message = await asyncio.wait_for(session.outgoing.get(), timeout=timeout)
        if predicate(message):
            return message
        backlog.append(message)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["tests/test_debugger.py", "tests/test_debugger.py::test_debuggable_case"])
async def test_debugpy_dap_pauses_steps_reads_locals_and_continues(tmp_path: Path, target: str) -> None:
    workspace = tmp_path / "workspace"
    test_file = workspace / "tests" / "test_debugger.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "def test_first_case():\n    assert True\n\ndef test_debuggable_case():\n    value = 1\n    value += 1\n    assert value == 2\n",
        encoding="utf-8",
    )
    now = utc_now()
    breakpoint = Breakpoint(
        id="debug-breakpoint",
        workspace_id="workspace-debug",
        file_path="tests/test_debugger.py",
        line_number=6,
        enabled=True,
        source="manual",
        created_at=now,
        updated_at=now,
    )
    service = DebugSessionService(adapter_interpreter=Path(sys.executable))
    bootstrap = await service.create(
        owner_id="owner",
        workspace_id="workspace-debug",
        workspace_dir=workspace,
        nodeid=target,
        target_interpreter=Path(sys.executable),
        breakpoints=[breakpoint],
    )
    debug_session = await service.get(bootstrap.id, "owner")
    assert debug_session is not None
    assert bootstrap.breakpoints == [breakpoint]

    seq = 0
    backlog: list[dict[str, Any]] = []

    async def request(command: str, arguments: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        nonlocal seq
        seq += 1
        request_id = seq
        await service.forward(
            debug_session,
            {"seq": request_id, "type": "request", "command": command, "arguments": arguments or {}},
        )
        response = await _wait_message(
            debug_session,
            lambda message: message.get("type") == "response" and message.get("request_seq") == request_id,
            backlog,
        )
        assert response.get("success") is True, response
        return request_id, response

    try:
        await request(
            "initialize",
            {
                "clientID": "ai-qa-platform-tests",
                "adapterID": "python",
                "pathFormat": "path",
                "linesStartAt1": True,
                "columnsStartAt1": True,
                "supportsRunInTerminalRequest": False,
            },
        )
        seq += 1
        launch_id = seq
        await service.forward(
            debug_session, {"seq": launch_id, "type": "request", "command": "launch", "arguments": {}}
        )
        await _wait_message(
            debug_session,
            lambda message: message.get("type") == "event" and message.get("event") == "initialized",
            backlog,
        )
        _, set_breakpoints = await request(
            "setBreakpoints",
            {
                "source": {"name": "test_debugger.py", "path": "tests/test_debugger.py"},
                "breakpoints": [{"line": 6}],
                "sourceModified": False,
            },
        )
        assert set_breakpoints["body"]["breakpoints"][0]["verified"] is True
        await request("setExceptionBreakpoints", {"filters": []})
        await request("configurationDone")

        stopped = await _wait_message(
            debug_session,
            lambda message: message.get("type") == "event" and message.get("event") == "stopped",
            backlog,
        )
        assert stopped["body"]["reason"] == "breakpoint"
        thread_id = stopped["body"]["threadId"]
        _, stack_response = await request("stackTrace", {"threadId": thread_id})
        frame = stack_response["body"]["stackFrames"][0]
        assert frame["name"] == "test_debuggable_case"
        assert frame["line"] == 6
        assert frame["source"]["path"] == "tests/test_debugger.py"
        _, scopes_response = await request("scopes", {"frameId": frame["id"]})
        locals_scope = next(scope for scope in scopes_response["body"]["scopes"] if scope["name"] == "Locals")
        _, variables_response = await request("variables", {"variablesReference": locals_scope["variablesReference"]})
        assert {item["name"]: item["value"] for item in variables_response["body"]["variables"]}["value"] == "1"

        await request("next", {"threadId": thread_id})
        step_stop = await _wait_message(
            debug_session,
            lambda message: message.get("type") == "event" and message.get("event") == "stopped",
            backlog,
        )
        assert step_stop["body"]["reason"] == "step"
        _, continued = await request("continue", {"threadId": thread_id})
        assert continued["body"]["allThreadsContinued"] is True
        exited = await _wait_message(
            debug_session,
            lambda message: message.get("type") == "event" and message.get("event") == "exited",
            backlog,
        )
        assert exited["body"]["exitCode"] == 0
    finally:
        await service.close(bootstrap.id, "owner")

    assert await service.get(bootstrap.id, "owner") is None


def test_debug_nodeid_must_be_one_workspace_python_test(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "tests" / "test_ok.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    assert validate_debug_nodeid(workspace, "tests/test_ok.py::test_ok") == "tests/test_ok.py::test_ok"
    assert validate_debug_nodeid(workspace, "tests/test_ok.py") == "tests/test_ok.py"
    with pytest.raises(ValueError, match="fully qualified"):
        validate_debug_nodeid(workspace, "tests/test_ok.py::")
    with pytest.raises(ValueError, match="relative Python file"):
        validate_debug_nodeid(workspace, "../test_ok.py::test_ok")
