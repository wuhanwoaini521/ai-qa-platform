from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.api import recorder as recorder_api
from app.services.recorder_service import RecorderStepsRevisionConflict, RecorderStreamReplaced
from fastapi import WebSocketDisconnect


class FakeWebSocket:
    def __init__(self, commands: list[dict[str, object]]) -> None:
        self.commands = commands
        self.messages: list[dict[str, object]] = []
        self.closed: tuple[int, str | None] | None = None

    async def send_json(self, message: dict[str, object]) -> None:
        self.messages.append(message)

    async def receive_json(self) -> dict[str, object]:
        if self.commands:
            return self.commands.pop(0)
        raise WebSocketDisconnect()

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = (code, reason)


class FakeRecorderService:
    def __init__(self, *, replaced: bool = False) -> None:
        self.session = SimpleNamespace(
            project_id="project-1",
            steps=[{"id": "existing", "action": "click", "description": "Keep this step"}],
            steps_revision=0,
            applied_step_command_ids={"processed-before-reconnect": None},
            processed_navigation_command_ids={"navigation-before-reconnect": None},
        )
        self.snapshot_types: list[str] = []
        self.snapshot_index = 0
        self.replaced = replaced

    async def get(self, _session_id: str, _owner_id: str):
        return self.session

    def touch(self, _session) -> None:
        return None

    async def claim_websocket_stream(self, _session) -> int:
        return 1

    async def page_snapshot(self, _session, *, stream_generation: int | None = None) -> dict[str, object]:
        snapshot_type = (
            self.snapshot_types[self.snapshot_index] if self.snapshot_index < len(self.snapshot_types) else "frame"
        )
        self.snapshot_index += 1
        return {
            "type": snapshot_type,
            "steps_revision": self.session.steps_revision,
            "steps": self.session.steps,
        }

    async def apply_command(
        self, _session, command: dict[str, object], *, stream_generation: int | None = None
    ) -> str | None:
        if self.replaced:
            raise RecorderStreamReplaced("Recorder stream was replaced")
        if command.get("action") == "fail":
            raise RuntimeError("command failed")
        if command.get("action") == "edit_step":
            raise RuntimeError("step edit failed")
        if (
            command.get("action") == "replace_steps"
            and command.get("base_steps_revision") != self.session.steps_revision
        ):
            raise RecorderStepsRevisionConflict(
                "Recorder steps changed since the command snapshot; refresh before replacing."
            )
        if command.get("action") == "add_step":
            self.session.steps_revision += 1
        return None

    def session_status(self, _session) -> dict[str, str]:
        return {"url": "http://127.0.0.1:5183/"}


@pytest.mark.asyncio
async def test_recorder_stream_acknowledges_each_command_with_its_action(monkeypatch):
    user = SimpleNamespace(id="user-1")
    service = FakeRecorderService()
    websocket = FakeWebSocket(
        [
            {"action": "click", "command_id": "client-1"},
            {"action": "fail", "command_id": "client-2"},
        ]
    )

    async def authenticate(_websocket, _scope):
        return user

    async def enforce_project_access(_user, _project_id):
        return None

    monkeypatch.setattr(recorder_api, "authenticate_websocket_stream", authenticate)
    monkeypatch.setattr(recorder_api, "has_permission", lambda *_args: True)
    monkeypatch.setattr(recorder_api, "enforce_project_access", enforce_project_access)
    monkeypatch.setattr(recorder_api, "recorder_service", service)

    await recorder_api.recorder_stream(websocket, "session-1")

    acknowledgements = [message for message in websocket.messages if message["type"] != "frame"]
    assert acknowledgements == [
        {"type": "command_success", "action": "click", "command_id": "client-1"},
        {
            "type": "command_error",
            "action": "fail",
            "message": "command failed",
            "url": "http://127.0.0.1:5183/",
            "command_id": "client-2",
        },
    ]


@pytest.mark.asyncio
async def test_step_command_acknowledges_the_committed_revision(monkeypatch):
    user = SimpleNamespace(id="user-1")
    service = FakeRecorderService()
    websocket = FakeWebSocket([{"action": "add_step", "command_id": "add-1"}])

    async def authenticate(_websocket, _scope):
        return user

    async def enforce_project_access(_user, _project_id):
        return None

    monkeypatch.setattr(recorder_api, "authenticate_websocket_stream", authenticate)
    monkeypatch.setattr(recorder_api, "has_permission", lambda *_args: True)
    monkeypatch.setattr(recorder_api, "enforce_project_access", enforce_project_access)
    monkeypatch.setattr(recorder_api, "recorder_service", service)

    await recorder_api.recorder_stream(websocket, "session-1")

    acknowledgements = [message for message in websocket.messages if message["type"] == "command_success"]
    assert acknowledgements == [
        {"type": "command_success", "action": "add_step", "command_id": "add-1", "steps_revision": 1}
    ]


@pytest.mark.asyncio
async def test_stream_snapshot_settles_only_processed_navigation_commands(monkeypatch):
    user = SimpleNamespace(id="user-1")
    service = FakeRecorderService()
    service.snapshot_types = ["frame", "error", "frame"]
    websocket = FakeWebSocket(
        [
            {"action": "click", "command_id": "nav-1"},
            {"action": "navigate", "command_id": "nav-2"},
        ]
    )

    async def authenticate(_websocket, _scope):
        return user

    async def enforce_project_access(_user, _project_id):
        return None

    monkeypatch.setattr(recorder_api, "authenticate_websocket_stream", authenticate)
    monkeypatch.setattr(recorder_api, "has_permission", lambda *_args: True)
    monkeypatch.setattr(recorder_api, "enforce_project_access", enforce_project_access)
    monkeypatch.setattr(recorder_api, "recorder_service", service)

    await recorder_api.recorder_stream(websocket, "session-1")

    snapshots = [message for message in websocket.messages if "settled_navigation_count" in message]
    assert [message["settled_navigation_count"] for message in snapshots] == [0, 1, 1]
    assert snapshots[0]["applied_step_command_ids"] == ["processed-before-reconnect"]
    assert snapshots[0]["processed_navigation_command_ids"] == ["navigation-before-reconnect"]
    assert snapshots[0]["applied_navigation_command_ids"] == ["navigation-before-reconnect"]


@pytest.mark.asyncio
async def test_reconnected_stream_settles_an_inherited_navigation(monkeypatch):
    user = SimpleNamespace(id="user-1")
    service = FakeRecorderService()
    service.snapshot_types = ["navigating", "frame"]
    websocket = FakeWebSocket([{"action": "clear_hover", "command_id": "clear-1"}])

    async def authenticate(_websocket, _scope):
        return user

    async def enforce_project_access(_user, _project_id):
        return None

    monkeypatch.setattr(recorder_api, "authenticate_websocket_stream", authenticate)
    monkeypatch.setattr(recorder_api, "has_permission", lambda *_args: True)
    monkeypatch.setattr(recorder_api, "enforce_project_access", enforce_project_access)
    monkeypatch.setattr(recorder_api, "recorder_service", service)

    await recorder_api.recorder_stream(websocket, "session-1")

    snapshots = [message for message in websocket.messages if "settled_navigation_count" in message]
    assert [message["settled_navigation_count"] for message in snapshots] == [0, 1]


@pytest.mark.asyncio
async def test_rejected_step_edit_forces_next_canonical_steps_snapshot(monkeypatch):
    user = SimpleNamespace(id="user-1")
    service = FakeRecorderService()
    websocket = FakeWebSocket(
        [
            {
                "action": "edit_step",
                "command_id": "edit-1",
                "step": {"id": "missing", "action": "click", "description": "Rejected edit"},
            }
        ]
    )

    async def authenticate(_websocket, _scope):
        return user

    async def enforce_project_access(_user, _project_id):
        return None

    monkeypatch.setattr(recorder_api, "authenticate_websocket_stream", authenticate)
    monkeypatch.setattr(recorder_api, "has_permission", lambda *_args: True)
    monkeypatch.setattr(recorder_api, "enforce_project_access", enforce_project_access)
    monkeypatch.setattr(recorder_api, "recorder_service", service)

    await recorder_api.recorder_stream(websocket, "session-1")

    frames = [message for message in websocket.messages if message["type"] == "frame"]
    assert len(frames) == 2
    assert frames[1]["steps"] == service.session.steps
    acknowledgements = [message for message in websocket.messages if message["type"] != "frame"]
    assert acknowledgements == [
        {
            "type": "command_error",
            "action": "edit_step",
            "message": "step edit failed",
            "url": "http://127.0.0.1:5183/",
            "command_id": "edit-1",
        }
    ]


@pytest.mark.asyncio
async def test_stale_replace_steps_conflict_returns_code_and_canonical_snapshot(monkeypatch):
    user = SimpleNamespace(id="user-1")
    service = FakeRecorderService()
    websocket = FakeWebSocket(
        [
            {
                "action": "replace_steps",
                "command_id": "replace-stale",
                "base_steps_revision": 7,
                "steps": [],
            }
        ]
    )

    async def authenticate(_websocket, _scope):
        return user

    async def enforce_project_access(_user, _project_id):
        return None

    monkeypatch.setattr(recorder_api, "authenticate_websocket_stream", authenticate)
    monkeypatch.setattr(recorder_api, "has_permission", lambda *_args: True)
    monkeypatch.setattr(recorder_api, "enforce_project_access", enforce_project_access)
    monkeypatch.setattr(recorder_api, "recorder_service", service)

    await recorder_api.recorder_stream(websocket, "session-1")

    frames = [message for message in websocket.messages if message["type"] == "frame"]
    assert len(frames) == 2
    assert frames[1]["steps"] == service.session.steps
    errors = [message for message in websocket.messages if message["type"] == "command_error"]
    assert errors == [
        {
            "type": "command_error",
            "action": "replace_steps",
            "message": "Recorder steps changed since the command snapshot; refresh before replacing.",
            "url": "http://127.0.0.1:5183/",
            "command_id": "replace-stale",
            "code": "steps_revision_conflict",
        }
    ]


@pytest.mark.asyncio
async def test_replaced_recorder_stream_closes_without_acknowledging_a_stale_command(monkeypatch):
    user = SimpleNamespace(id="user-1")
    service = FakeRecorderService(replaced=True)
    websocket = FakeWebSocket([{"action": "click"}])

    async def authenticate(_websocket, _scope):
        return user

    async def enforce_project_access(_user, _project_id):
        return None

    monkeypatch.setattr(recorder_api, "authenticate_websocket_stream", authenticate)
    monkeypatch.setattr(recorder_api, "has_permission", lambda *_args: True)
    monkeypatch.setattr(recorder_api, "enforce_project_access", enforce_project_access)
    monkeypatch.setattr(recorder_api, "recorder_service", service)

    await recorder_api.recorder_stream(websocket, "session-1")

    assert websocket.closed == (1012, "Recorder stream replaced")
    assert [message for message in websocket.messages if message["type"] != "frame"] == []
