from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from app.persistence.models import utc_now
from app.repositories.debug_session_repo import DebugSessionRepository
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
@pytest.mark.parametrize("live_updates", [False, True])
async def test_debugpy_dap_pauses_steps_reads_locals_and_continues(
    tmp_path: Path, target: str, live_updates: bool, test_db_session
) -> None:
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
    service = DebugSessionService(adapter_interpreter=Path(sys.executable), repository=DebugSessionRepository())
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
    assert (await service.get_record(bootstrap.id, "owner")).status == "STARTING"
    await service.activate(bootstrap.id)
    assert (await service.get_record(bootstrap.id, "owner")).status == "ACTIVE"
    # Event source paths follow the same workspace-relative contract as stack traces.
    breakpoint_event = service._to_client_paths(
        debug_session,
        {
            "type": "event",
            "event": "breakpoint",
            "body": {"reason": "changed", "breakpoint": {"id": 1, "source": {"path": str(test_file)}}},
        },
    )
    assert breakpoint_event["body"]["breakpoint"]["source"]["path"] == "tests/test_debugger.py"

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

        if live_updates:
            _, updated = await request(
                "setBreakpoints",
                {"source": {"path": "tests/test_debugger.py"}, "breakpoints": [{"line": 7}]},
            )
            assert updated["body"]["breakpoints"][0]["verified"] is True
            assert updated["body"]["breakpoints"][0]["line"] == 7
        await request("continue" if live_updates else "next", {"threadId": thread_id})
        step_stop = await _wait_message(
            debug_session,
            lambda message: message.get("type") == "event" and message.get("event") == "stopped",
            backlog,
        )
        assert step_stop["body"]["reason"] == ("breakpoint" if live_updates else "step")
        _, updated_stack = await request("stackTrace", {"threadId": thread_id})
        assert updated_stack["body"]["stackFrames"][0]["line"] == 7
        if live_updates:
            _, removed = await request(
                "setBreakpoints", {"source": {"path": "tests/test_debugger.py"}, "breakpoints": []}
            )
            assert removed["body"]["breakpoints"] == []
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
    persisted = await service.get_record(bootstrap.id, "owner")
    assert persisted is not None and persisted.status == "CLOSED"


@pytest.mark.asyncio
async def test_debug_session_record_keeps_run_execution_and_failure_lineage(client, test_db_session):
    from app.persistence.models import FailureRecordORM, TestExecutionORM, TestRunORM
    from app.repositories.debug_session_repo import DebugSessionRepository

    project_response = await client.post("/api/projects", json={"name": "Debug lineage", "bootstrap_workspace": False})
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]
    me = await client.get("/api/auth/me")
    owner_id = me.json()["user"]["id"]
    nodeid = "tests/test_debug.py::test_case"
    async with test_db_session() as session:
        session.add(TestRunORM(id="run-debug", project_id=project_id, workspace_id=project_id))
        session.add(TestExecutionORM(id="execution-debug", run_id="run-debug", nodeid=nodeid, status="FAILED"))
        session.add(
            FailureRecordORM(
                id="failure-debug",
                run_id="run-debug",
                execution_id="execution-debug",
                test_nodeid=nodeid,
                test_name="test_case",
            )
        )
        await session.commit()

    repository = DebugSessionRepository()
    await repository.create(
        session_id="debug-session-lineage",
        owner_id=owner_id,
        workspace_id=project_id,
        nodeid=nodeid,
        run_id="run-debug",
        execution_id="execution-debug",
        failure_id="failure-debug",
    )
    active = await client.get("/api/debug/sessions/debug-session-lineage")
    assert active.status_code == 200, active.text
    assert active.json() == {
        "id": "debug-session-lineage",
        "workspace_id": project_id,
        "nodeid": nodeid,
        "status": "STARTING",
        "run_id": "run-debug",
        "execution_id": "execution-debug",
        "failure_id": "failure-debug",
        "breakpoints": [],
    }

    await repository.activate("debug-session-lineage")
    active = await client.get("/api/debug/sessions/debug-session-lineage")
    assert active.status_code == 200, active.text
    assert active.json()["status"] == "ACTIVE"

    await repository.close("debug-session-lineage")
    closed = await client.get("/api/debug/sessions/debug-session-lineage")
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["run_id"] == "run-debug"
    assert closed.json()["execution_id"] == "execution-debug"
    assert closed.json()["failure_id"] == "failure-debug"


@pytest.mark.asyncio
async def test_debug_create_validates_and_returns_failure_execution_link(client, test_db_session, monkeypatch):
    from app.api import debugger
    from app.persistence.models import FailureRecordORM, TestExecutionORM, TestRunORM
    from project_model.models import DebugSessionBootstrap

    project_response = await client.post("/api/projects", json={"name": "Debug source", "bootstrap_workspace": False})
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]
    source = await client.put(
        f"/api/workspaces/{project_id}/file",
        json={"path": "tests/test_debug.py", "content": "def test_case(): pass\n"},
    )
    assert source.status_code == 200, source.text
    nodeid = "tests/test_debug.py::test_case"
    async with test_db_session() as session:
        session.add(TestRunORM(id="run-debug-api", project_id=project_id, workspace_id=project_id))
        session.add(TestExecutionORM(id="execution-debug-api", run_id="run-debug-api", nodeid=nodeid, status="FAILED"))
        session.add(
            FailureRecordORM(
                id="failure-debug-api",
                run_id="run-debug-api",
                execution_id="execution-debug-api",
                test_nodeid=nodeid,
                test_name="test_case",
            )
        )
        await session.commit()

    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return DebugSessionBootstrap(
            id="debug-session-api",
            workspace_id=kwargs["workspace_id"],
            nodeid=kwargs["nodeid"],
            run_id=kwargs["run_id"],
            execution_id=kwargs["execution_id"],
            failure_id=kwargs["failure_id"],
            breakpoints=kwargs["breakpoints"],
        )

    monkeypatch.setattr(debugger.debug_session_service, "create", fake_create)
    response = await client.post(
        "/api/debug/sessions",
        json={"workspace_id": project_id, "nodeid": nodeid, "failure_id": "failure-debug-api"},
    )
    assert response.status_code == 200, response.text
    assert {key: captured[key] for key in ("run_id", "execution_id", "failure_id")} == {
        "run_id": "run-debug-api",
        "execution_id": "execution-debug-api",
        "failure_id": "failure-debug-api",
    }
    assert response.json()["execution_id"] == "execution-debug-api"

    mismatch = await client.post(
        "/api/debug/sessions",
        json={
            "workspace_id": project_id,
            "nodeid": "tests/test_debug.py::test_other",
            "failure_id": "failure-debug-api",
        },
    )
    assert mismatch.status_code == 404


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
