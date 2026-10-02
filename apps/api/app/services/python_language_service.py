"""A workspace-scoped JSON-RPC transport for the installed basedpyright server."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from qa_core.onboarding.contract import venv_interpreter

ALLOWED_METHODS = frozenset(
    {
        "initialize",
        "initialized",
        "shutdown",
        "exit",
        "$/cancelRequest",
        "textDocument/didOpen",
        "textDocument/didChange",
        "textDocument/didClose",
        "textDocument/didSave",
        "textDocument/completion",
        "textDocument/hover",
        "textDocument/definition",
        "textDocument/references",
        "textDocument/signatureHelp",
        "textDocument/documentSymbol",
        "workspace/symbol",
    }
)


class PythonLanguageService:
    def __init__(self, workspace: Path, workspace_id: str):
        self.workspace = workspace.resolve()
        self.workspace_id = workspace_id
        self.process = None
        self._write_lock = asyncio.Lock()

    def source_uri(self, uri: str) -> str:
        parsed = urlparse(uri)
        if parsed.scheme != "qa-workspace" or parsed.netloc != self.workspace_id:
            raise ValueError("Language service document must belong to the selected workspace.")
        relative = unquote(parsed.path).lstrip("/")
        if "\\" in relative or ".." in Path(relative).parts or ":" in relative:
            raise ValueError("Invalid language service source path.")
        path = (self.workspace / relative).resolve()
        if not path.is_relative_to(self.workspace) or path.suffix != ".py":
            raise ValueError("Language service only accepts workspace Python files.")
        return path.as_uri()

    def client_uri(self, uri: str) -> str | None:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        decoded = unquote(parsed.path)
        if os.name == "nt" and decoded.startswith("/"):
            decoded = decoded[1:]
        path = Path(decoded).resolve()
        if not path.is_relative_to(self.workspace):
            return None
        return f"qa-workspace://{self.workspace_id}/" + quote(path.relative_to(self.workspace).as_posix(), safe="/")

    def map_uris(self, value, *, incoming=False):
        if isinstance(value, list):
            return [self.map_uris(item, incoming=incoming) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key in {"uri", "targetUri"} and isinstance(item, str):
                result[key] = self.source_uri(item) if incoming else self.client_uri(item)
            else:
                result[key] = self.map_uris(item, incoming=incoming)
        return result

    async def start(self):
        import basedpyright
        import nodejs_wheel.executable

        root = Path(nodejs_wheel.executable.ROOT_DIR)
        executable = root / ("node.exe" if os.name == "nt" else "bin/node")
        script = Path(basedpyright.__file__).parent / "langserver.index.js"
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        self.process = await asyncio.create_subprocess_exec(
            str(executable),
            str(script),
            "--stdio",
            cwd=self.workspace,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            **options,
        )

    async def write(self, message):
        if not self.process or not self.process.stdin:
            raise RuntimeError("Language server is unavailable.")
        payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
        if len(payload) > 1024 * 1024:
            raise ValueError("Language service message exceeds its size limit.")
        async with self._write_lock:
            self.process.stdin.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload)
            await self.process.stdin.drain()

    async def forward(self, message):
        method = message.get("method")
        if method not in ALLOWED_METHODS:
            raise ValueError("Unsupported language service method.")
        mapped = self.map_uris(message, incoming=True)
        if method == "initialize":
            params = mapped.setdefault("params", {})
            params.update(
                {
                    "rootUri": self.workspace.as_uri(),
                    "rootPath": str(self.workspace),
                    "workspaceFolders": [{"uri": self.workspace.as_uri(), "name": self.workspace_id}],
                    "processId": None,
                }
            )
        await self.write(mapped)

    async def read(self):
        if not self.process or not self.process.stdout:
            raise RuntimeError("Language server is unavailable.")
        while True:
            length = None
            while True:
                header = await self.process.stdout.readline()
                if not header:
                    raise EOFError("Language server exited.")
                if header in {b"\r\n", b"\n"}:
                    break
                key, _, value = header.decode("ascii").partition(":")
                if key.lower() == "content-length":
                    length = int(value.strip())
            if length is None or not 0 < length <= 2 * 1024 * 1024:
                raise ValueError("Invalid language server response length.")
            message = json.loads(await self.process.stdout.readexactly(length))
            if "method" in message and "id" in message:
                method = message["method"]
                if method == "workspace/configuration":
                    result = [
                        self.configuration(item.get("section")) for item in message.get("params", {}).get("items", [])
                    ]
                elif method == "workspace/applyEdit":
                    result = {"applied": False, "failureReason": "Source changes require user review."}
                else:
                    result = None
                await self.write({"jsonrpc": "2.0", "id": message["id"], "result": result})
                continue
            return self.map_uris(message)

    def configuration(self, section: str | None):
        """Return the requested configuration section at its actual LSP nesting level."""
        analysis = {"diagnosticMode": "openFilesOnly", "typeCheckingMode": "basic", "autoSearchPaths": True}
        if section == "python":
            candidates = [venv_interpreter(self.workspace / name) for name in (".qa-platform-runtime", ".venv", "venv")]
            interpreter = next((path for path in candidates if path.is_file()), Path(sys.executable))
            return {"pythonPath": str(interpreter)}
        if section in {"basedpyright.analysis", "python.analysis"}:
            return analysis
        if section in {"basedpyright", "pyright"}:
            return {"analysis": analysis}
        return None

    async def close(self):
        process = self.process
        self.process = None
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
