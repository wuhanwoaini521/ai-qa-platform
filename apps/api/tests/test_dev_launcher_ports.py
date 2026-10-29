"""The dev launcher must not mistake a stopped stack's lingering socket for an occupied port.

Restarting a stack leaves sockets in TIME_WAIT on its port: a plain bind fails there, but nothing
accepts a connection. Treating that as occupied made the restarted stack silently bind another port
(`Port 8010 is occupied; using 8011`), which is what misled the earlier key-rotation drill.
"""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "task.py"


@pytest.fixture(scope="module")
def task_module():
    spec = importlib.util.spec_from_file_location("dev_task_runner", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _listening_port() -> tuple[socket.socket, int]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    return listener, listener.getsockname()[1]


def test_a_listening_port_is_skipped(task_module):
    listener, port = _listening_port()
    try:
        assert task_module._port_is_in_use(port) is True
        listener.settimeout(1)
        probe_connection, _ = listener.accept()
        probe_connection.close()
        assert task_module._available_port(port) != port
    finally:
        listener.close()


def test_a_port_left_by_a_stopped_stack_is_reused(task_module):
    listener, port = _listening_port()
    client = socket.create_connection(("127.0.0.1", port))
    accepted, _ = listener.accept()
    # Hang up on both sides, the way a stopped stack does, so the port may be left lingering.
    client.close()
    accepted.close()
    listener.close()

    assert task_module._port_is_in_use(port) is False
    assert task_module._available_port(port) == port
