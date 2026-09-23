import os
from pathlib import Path

import pytest
from app.services.workspace_service import SecurityException, WorkspaceService
from httpx import AsyncClient

pytestmark = pytest.mark.security


@pytest.mark.asyncio
@pytest.mark.integration
async def test_workspace_path_traversal_prevention(client: AsyncClient):
    # Create project
    proj_res = await client.post(
        "/api/projects",
        json={"name": "Security Test Project", "bootstrap_workspace": True},
    )
    proj_id = proj_res.json()["id"]

    # 1. Traversal in file read
    malicious_paths = [
        "../../etc/passwd",
        "/etc/passwd",
        "../../.ssh/id_rsa",
        "../..",
        "tests/../../..",
    ]

    for bad_path in malicious_paths:
        res = await client.get(f"/api/workspaces/{proj_id}/file?path={bad_path}")
        assert res.status_code in (400, 404), f"Path {bad_path} should be rejected or not found"

    # 2. Traversal in file write
    bad_write = await client.put(
        f"/api/workspaces/{proj_id}/file",
        json={"path": "../../escape.txt", "content": "malicious content"},
    )
    assert bad_write.status_code == 400

    # 3. Traversal in workspace ID
    bad_ws_id = "../../escaped_ws"
    bad_ws_res = await client.get(f"/api/workspaces/{bad_ws_id}/files")
    # Base dir validation handles this safely (either rejects 400/404 or isolates to empty dir)
    assert bad_ws_res.status_code in (400, 404)


@pytest.mark.unit
def test_workspace_id_never_resolves_to_prefix_sibling_directory(tmp_path: Path):
    """A workspace id must never resolve to a directory outside the base dir.

    Note ``Path(workspace_id).name`` already strips directory components such as ``..``,
    so a plain string id is confined to a direct child of the base dir; the boundary
    check below is what makes that a guarantee rather than a coincidence.
    """
    base_dir = tmp_path / "workspaces"
    sibling = tmp_path / "workspaces-evil"
    sibling.mkdir()
    service = WorkspaceService(base_dir=base_dir)

    for candidate in ("../workspaces-evil", "..", "nested/../../workspaces-evil", "/etc"):
        try:
            resolved = service.get_workspace_dir(candidate)
        except SecurityException:
            continue
        assert resolved != sibling
        assert str(resolved) == str(service.base_dir) or str(resolved).startswith(str(service.base_dir) + os.sep)


@pytest.mark.unit
def test_workspace_id_symlink_to_sibling_prefix_directory_rejected(tmp_path: Path):
    """A symlink inside the base dir pointing at a prefix-sibling directory must not be reachable."""
    base_dir = tmp_path / "workspaces"
    sibling = tmp_path / "workspaces-evil"
    base_dir.mkdir(parents=True, exist_ok=True)
    sibling.mkdir()
    os.symlink(sibling, base_dir / "evil")

    service = WorkspaceService(base_dir=base_dir)
    with pytest.raises(SecurityException):
        service.get_workspace_dir("evil")


@pytest.mark.unit
def test_workspace_id_parent_traversal_rejected(tmp_path: Path):
    service = WorkspaceService(base_dir=tmp_path / "workspaces")

    for bad_id in ("..", "../..", "../workspaces/../.."):
        with pytest.raises(SecurityException):
            service.get_workspace_dir(bad_id)


@pytest.mark.unit
def test_legit_workspace_id_resolves_inside_base_dir(tmp_path: Path):
    base_dir = tmp_path / "workspaces"
    service = WorkspaceService(base_dir=base_dir)

    ws_dir = service.get_workspace_dir("ws-alpha")
    assert ws_dir == base_dir / "ws-alpha"
    assert str(ws_dir).startswith(str(base_dir.resolve()))


@pytest.mark.asyncio
@pytest.mark.unit
async def test_symlink_inside_workspace_cannot_escape_on_read_or_write(tmp_path: Path):
    base_dir = tmp_path / "workspaces"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret", encoding="utf-8")

    service = WorkspaceService(base_dir=base_dir)
    ws_dir = service.get_workspace_dir("ws-link")
    ws_dir.mkdir(parents=True, exist_ok=True)
    os.symlink(outside, ws_dir / "link")

    with pytest.raises(SecurityException):
        await service.read_file("ws-link", "link/secret.txt")

    with pytest.raises(SecurityException):
        await service.write_file("ws-link", "link/escaped.txt", "pwned")

    assert not (outside / "escaped.txt").exists()
