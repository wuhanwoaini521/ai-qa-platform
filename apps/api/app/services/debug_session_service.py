from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from project_model.models import Breakpoint, DebugSessionBootstrap

from app.repositories.debug_session_repo import DebugSessionRepository
from app.settings import get_config

logger = logging.getLogger(__name__)

ALLOWED_DAP_COMMANDS = frozenset(
    {
        "initialize",
        "launch",
        "configurationDone",
        "setBreakpoints",
        "setExceptionBreakpoints",
        "threads",
        "stackTrace",
        "scopes",
        "variables",
        "continue",
        "next",
        "stepIn",
        "stepOut",
        "pause",
        "disconnect",
    }
)


def validate_debug_nodeid(workspace_dir: Path, nodeid: str) -> str:
    """Accept a Python test file or one pytest case inside the selected workspace."""
    normalized = nodeid.replace("\\", "/").strip()
    parts = normalized.split("::")
    if any(not part for part in parts):
        raise ValueError("Debug requires a Python test file or a fully qualified pytest nodeid.")

    relative = PurePosixPath(parts[0])
    if relative.is_absolute() or ".." in relative.parts or ":" in parts[0]:
        raise ValueError("Debug nodeid must use a relative Python file inside the workspace.")
    root = workspace_dir.resolve()
    source = (root / Path(*relative.parts)).resolve()
    if not source.is_relative_to(root):
        raise ValueError("Debug nodeid points outside the workspace.")
    if source.suffix != ".py" or not source.is_file():
        raise ValueError("Debug nodeid must point to an existing Python test file.")
    return normalized


def _workspace_relative_path(workspace_dir: Path, value: str) -> Path:
    normalized = value.replace("\\", "/").strip()
    relative = PurePosixPath(normalized)
    if not normalized or relative.is_absolute() or ".." in relative.parts or ":" in normalized:
        raise ValueError("DAP source path must be relative to the workspace.")
    root = workspace_dir.resolve()
    target = (root / Path(*relative.parts)).resolve()
    if not target.is_relative_to(root):
        raise ValueError("DAP source path points outside the workspace.")
    return target


@dataclass
class DebugSession:
    id: str
    owner_id: str
    workspace_id: str
    workspace_dir: Path
    nodeid: str
    target_interpreter: Path
    breakpoints: list[Breakpoint]
    process: asyncio.subprocess.Process
    run_id: str | None = None
    execution_id: str | None = None
    failure_id: str | None = None
    outgoing: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    reader_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None
    launch_requested: bool = False
    connected: bool = False
    closing: bool = False
    request_seq: int = 1_000_000
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class DebugSessionService:
    """Owns a single debugpy DAP adapter per authenticated debug session."""

    def __init__(
        self, adapter_interpreter: Path | None = None, repository: DebugSessionRepository | None = None
    ) -> None:
        # Preserve virtual-environment symlinks: resolving .venv/bin/python escapes the venv and
        # can make debugpy/pytest disappear from the adapter subprocess.
        self.adapter_interpreter = Path(os.path.abspath(adapter_interpreter or Path(sys.executable)))
        self.repository = repository
        self._sessions: dict[str, DebugSession] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        *,
        owner_id: str,
        workspace_id: str,
        workspace_dir: Path,
        nodeid: str,
        target_interpreter: Path | None,
        breakpoints: list[Breakpoint],
        run_id: str | None = None,
        execution_id: str | None = None,
        failure_id: str | None = None,
    ) -> DebugSessionBootstrap:
        root = workspace_dir.resolve()
        normalized_nodeid = validate_debug_nodeid(root, nodeid)
        interpreter = Path(
            os.path.abspath(
                target_interpreter if target_interpreter and target_interpreter.is_file() else sys.executable
            )
        )
        session_id = str(uuid4())
        process_options: dict[str, Any] = {
            "cwd": str(root),
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if os.name == "nt":
            process_options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            process_options["start_new_session"] = True

        try:
            process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    str(self.adapter_interpreter), "-m", "debugpy.adapter", **process_options
                ),
                timeout=get_config().debugger.startup_timeout_seconds,
            )
        except asyncio.TimeoutError as error:
            raise RuntimeError("Python Debug Runtime did not start before the configured timeout.") from error
        except (FileNotFoundError, OSError) as error:
            raise RuntimeError("Python Debug Runtime is unavailable; install the API debugpy dependency.") from error

        session = DebugSession(
            id=session_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
            workspace_dir=root,
            nodeid=normalized_nodeid,
            target_interpreter=interpreter,
            breakpoints=breakpoints,
            process=process,
            run_id=run_id,
            execution_id=execution_id,
            failure_id=failure_id,
        )
        if self.repository is not None:
            try:
                await self.repository.create(
                    session_id=session_id,
                    owner_id=owner_id,
                    workspace_id=workspace_id,
                    nodeid=normalized_nodeid,
                    run_id=run_id,
                    execution_id=execution_id,
                    failure_id=failure_id,
                )
            except Exception as error:
                await self._stop_process(session)
                raise RuntimeError("Debug session could not be persisted.") from error
        async with self._lock:
            self._sessions[session_id] = session
        session.reader_task = asyncio.create_task(self._read_adapter(session), name=f"debug-dap-{session_id}")
        session.stderr_task = asyncio.create_task(self._discard_stderr(session), name=f"debug-stderr-{session_id}")
        return DebugSessionBootstrap(
            id=session_id,
            workspace_id=workspace_id,
            nodeid=normalized_nodeid,
            status="STARTING",
            run_id=run_id,
            execution_id=execution_id,
            failure_id=failure_id,
            breakpoints=breakpoints,
        )

    async def get(self, session_id: str, owner_id: str) -> DebugSession | None:
        async with self._lock:
            session = self._sessions.get(session_id)
        return session if session and session.owner_id == owner_id else None

    async def activate(self, session_id: str) -> None:
        if self.repository is None:
            return
        try:
            await self.repository.activate(session_id)
        except Exception:
            logger.exception("Failed to activate persisted debug session %s", session_id)

    async def failure_lineage(self, *, failure_id: str, workspace_id: str, nodeid: str) -> dict[str, str] | None:
        if self.repository is None:
            return None
        return await self.repository.failure_lineage(failure_id=failure_id, workspace_id=workspace_id, nodeid=nodeid)

    async def get_record(self, session_id: str, owner_id: str) -> DebugSessionBootstrap | None:
        if self.repository is None:
            return None
        record = await self.repository.get(session_id, owner_id)
        return DebugSessionBootstrap(**record) if record else None

    async def forward(self, session: DebugSession, message: dict[str, Any]) -> None:
        if not isinstance(message, dict):
            raise ValueError("Only DAP request objects are accepted from the client.")
        if message.get("type") != "request" or not isinstance(message.get("seq"), int):
            raise ValueError("Only DAP request messages are accepted from the client.")
        command = message.get("command")
        if command not in ALLOWED_DAP_COMMANDS:
            raise ValueError(f"DAP command is not allowed: {command}")
        if session.process.returncode is not None or session.closing:
            raise RuntimeError("Debug session has already ended.")

        outgoing = dict(message)
        arguments = dict(message.get("arguments") or {})
        if command == "launch":
            if session.launch_requested:
                raise ValueError("A debug session can launch only one pytest case.")
            session.launch_requested = True
            outgoing["arguments"] = {
                "name": f"Debug {session.nodeid}",
                "type": "python",
                "request": "launch",
                "module": "pytest",
                "args": ["-p", "no:xdist", "-s", "-q", session.nodeid],
                "cwd": str(session.workspace_dir),
                "python": [str(session.target_interpreter)],
                "console": "internalConsole",
                "justMyCode": False,
                "subProcess": False,
                "redirectOutput": True,
                "env": {"PYTEST_ADDOPTS": ""},
            }
        elif command == "setBreakpoints":
            source = arguments.get("source") or {}
            source_path = source.get("path")
            if not isinstance(source_path, str):
                raise ValueError("DAP setBreakpoints requires a workspace-relative source path.")
            source["path"] = str(_workspace_relative_path(session.workspace_dir, source_path))
            arguments["source"] = source
            outgoing["arguments"] = arguments
        elif command == "disconnect":
            arguments["terminateDebuggee"] = True
            outgoing["arguments"] = arguments

        await self._write_message(session, outgoing)

    async def close(self, session_id: str, owner_id: str | None = None) -> bool:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or (owner_id is not None and session.owner_id != owner_id):
                return False
            self._sessions.pop(session_id, None)
            session.closing = True
        await self._stop_process(session)
        if self.repository is not None:
            try:
                await self.repository.close(session_id)
            except Exception:
                logger.exception("Failed to close persisted debug session %s", session_id)
        return True

    async def close_all(self) -> None:
        async with self._lock:
            session_ids = list(self._sessions)
        await asyncio.gather(*(self.close(session_id) for session_id in session_ids), return_exceptions=True)

    async def _write_message(self, session: DebugSession, message: dict[str, Any]) -> None:
        writer = session.process.stdin
        if writer is None:
            raise RuntimeError("Debug Adapter input is closed.")
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        async with session.write_lock:
            writer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload)
            await writer.drain()

    async def _read_adapter(self, session: DebugSession) -> None:
        reader = session.process.stdout
        if reader is None:
            return
        try:
            while True:
                headers: dict[str, str] = {}
                while True:
                    line = await reader.readline()
                    if not line:
                        return
                    if line in (b"\r\n", b"\n"):
                        break
                    key, separator, value = line.decode("ascii", errors="strict").partition(":")
                    if not separator:
                        raise ValueError("Invalid DAP header from adapter.")
                    headers[key.lower()] = value.strip()
                length = int(headers["content-length"])
                if length < 0 or length > 16 * 1024 * 1024:
                    raise ValueError("DAP message exceeded the 16 MiB limit.")
                message = json.loads(await reader.readexactly(length))
                await session.outgoing.put(self._to_client_paths(session, message))
        except (asyncio.IncompleteReadError, asyncio.CancelledError):
            return
        except Exception as error:
            if not session.closing:
                await session.outgoing.put(
                    {
                        "type": "event",
                        "event": "output",
                        "body": {"category": "stderr", "output": f"DAP adapter error: {error}"},
                    }
                )
        finally:
            if not session.closing:
                code = await session.process.wait()
                await session.outgoing.put({"type": "event", "event": "terminated", "body": {"exitCode": code}})

    async def _discard_stderr(self, session: DebugSession) -> None:
        reader = session.process.stderr
        if reader is None:
            return
        while await reader.read(4096):
            pass

    @staticmethod
    def _to_client_paths(session: DebugSession, message: dict[str, Any]) -> dict[str, Any]:
        def relative_source(source: Any) -> Any:
            if not isinstance(source, dict):
                return source
            result = dict(source)
            path = result.get("path")
            if isinstance(path, str):
                try:
                    resolved = Path(path).resolve()
                    if resolved.is_relative_to(session.workspace_dir):
                        result["path"] = resolved.relative_to(session.workspace_dir).as_posix()
                except (OSError, ValueError):
                    pass
            return result

        result = dict(message)
        body = result.get("body")
        if isinstance(body, dict):
            body = dict(body)
            if "source" in body:
                body["source"] = relative_source(body["source"])
            if isinstance(body.get("breakpoint"), dict) and "source" in body["breakpoint"]:
                body["breakpoint"] = {
                    **body["breakpoint"],
                    "source": relative_source(body["breakpoint"].get("source")),
                }
            if isinstance(body.get("stackFrames"), list):
                body["stackFrames"] = [
                    {**frame, "source": relative_source(frame.get("source"))}
                    if isinstance(frame, dict) and "source" in frame
                    else frame
                    for frame in body["stackFrames"]
                ]
            if isinstance(body.get("breakpoints"), list):
                body["breakpoints"] = [
                    {**item, "source": relative_source(item.get("source"))}
                    if isinstance(item, dict) and "source" in item
                    else item
                    for item in body["breakpoints"]
                ]
            result["body"] = body
        return result

    async def _stop_process(self, session: DebugSession) -> None:
        process = session.process
        if process.returncode is None and process.stdin is not None:
            try:
                session.request_seq += 1
                await self._write_message(
                    session,
                    {
                        "seq": session.request_seq,
                        "type": "request",
                        "command": "disconnect",
                        "arguments": {"restart": False, "terminateDebuggee": True},
                    },
                )
            except (BrokenPipeError, ConnectionError, RuntimeError):
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=get_config().debugger.shutdown_grace_timeout_seconds)
            except asyncio.TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=get_config().debugger.shutdown_force_timeout_seconds)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        for task in (session.reader_task, session.stderr_task):
            if task and task is not asyncio.current_task() and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (session.reader_task, session.stderr_task) if task),
            return_exceptions=True,
        )


debug_session_service = DebugSessionService(repository=DebugSessionRepository())
