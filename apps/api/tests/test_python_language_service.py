from __future__ import annotations

import asyncio

import pytest
from app.services.python_language_service import PythonLanguageService


@pytest.mark.asyncio
async def test_real_language_server_hover_definition_references_and_diagnostics(tmp_path):
    (tmp_path / "helpers.py").write_text(
        'def greet(name: str) -> str:\n    """Return a greeting."""\n    return name\n', encoding="utf-8"
    )
    source = 'from helpers import greet\nmessage = greet("hello")\nunknown = missing_symbol\n'
    (tmp_path / "test_example.py").write_text(source, encoding="utf-8")
    service = PythonLanguageService(tmp_path, "project-lsp")
    uri = "qa-workspace://project-lsp/test_example.py"
    sequence = 0
    notifications = []

    async def request(method, params):
        nonlocal sequence
        sequence += 1
        await service.forward({"jsonrpc": "2.0", "id": sequence, "method": method, "params": params})
        for _ in range(100):
            message = await asyncio.wait_for(service.read(), timeout=20)
            if message.get("id") == sequence:
                assert "error" not in message, message
                return message.get("result")
            notifications.append(message)
        raise AssertionError("No matching LSP response")

    try:
        await service.start()
        initialized = await request("initialize", {"capabilities": {"workspace": {"configuration": True}}})
        assert initialized["capabilities"]["hoverProvider"]
        await service.forward({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        await service.forward(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {"textDocument": {"uri": uri, "version": 1, "languageId": "python", "text": source}},
            }
        )
        at = {"textDocument": {"uri": uri}, "position": {"line": 1, "character": 12}}
        hover = await request("textDocument/hover", at)
        assert "greet" in str(hover)
        definitions = await request("textDocument/definition", at)
        assert (
            definitions
            and definitions[0].get("uri", definitions[0].get("targetUri")) == "qa-workspace://project-lsp/helpers.py"
        )
        references = await request("textDocument/references", {**at, "context": {"includeDeclaration": True}})
        assert len(references) >= 2
        completion = await request(
            "textDocument/completion", {"textDocument": {"uri": uri}, "position": {"line": 1, "character": 12}}
        )
        items = completion if isinstance(completion, list) else completion["items"]
        assert any(item["label"] == "greet" for item in items)
        while not any(
            message.get("method") == "textDocument/publishDiagnostics" and "missing_symbol" in str(message)
            for message in notifications
        ):
            notifications.append(await asyncio.wait_for(service.read(), timeout=20))
        assert any(message.get("params", {}).get("uri") == uri for message in notifications)
    finally:
        process = service.process
        await service.close()
        if process:
            assert process.returncode is not None


def test_language_configuration_uses_requested_section_and_managed_interpreter(tmp_path):
    from qa_core.onboarding.contract import venv_interpreter

    interpreter = venv_interpreter(tmp_path / ".qa-platform-runtime")
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    service = PythonLanguageService(tmp_path, "project-lsp")
    assert service.configuration("python")["pythonPath"] == str(interpreter)
    assert service.configuration("basedpyright.analysis")["typeCheckingMode"] == "basic"
    assert service.configuration("python.analysis")["diagnosticMode"] == "openFilesOnly"
    assert service.configuration("unrelated") is None


def test_language_service_rejects_external_and_traversal_sources(tmp_path):
    service = PythonLanguageService(tmp_path, "project-lsp")
    for uri in (
        "file:///etc/passwd",
        "qa-workspace://other/main.py",
        "qa-workspace://project-lsp/%2e%2e/secret.py",
        "qa-workspace://project-lsp/secrets.env",
    ):
        with pytest.raises(ValueError):
            service.source_uri(uri)
