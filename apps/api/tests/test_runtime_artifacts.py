import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.persistence.models import TaskArtifactORM, TaskORM
from app.services.artifact_storage_service import ArtifactStorageService
from app.services.runtime_projection import RuntimeProjection
from sqlalchemy import select


async def test_artifact_cleanup_is_scoped_to_the_request(tmp_path):
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()
    release_first = asyncio.Event()
    release_second = asyncio.Event()
    calls = 0
    second_path: Path | None = None

    class GatedRepository:
        async def create(self, **values):
            nonlocal calls
            calls += 1
            current = calls
            path = Path(values["storage_path"])
            if current == 2:
                nonlocal second_path
                second_path = path
            if current == 1:
                first_entered.set()
                await release_first.wait()
                raise RuntimeError("first database write failed")
            second_entered.set()
            await release_second.wait()
            return SimpleNamespace(
                id="second",
                filename=values["filename"],
                size_bytes=values["size_bytes"],
                content_type=values["content_type"],
                storage_type=values["storage_type"],
                storage_path=str(path),
            )

    storage = ArtifactStorageService(artifact_repo=GatedRepository(), base_dir=tmp_path / "artifacts")
    first = asyncio.create_task(storage.save_artifact("first.txt", b"first"))
    await first_entered.wait()
    second = asyncio.create_task(storage.save_artifact("second.txt", b"second"))
    await second_entered.wait()
    release_first.set()
    with pytest.raises(RuntimeError, match="first database write failed"):
        await first
    assert second_path is not None and second_path.exists(), (
        "failure cleanup for one request deleted another request's file"
    )
    release_second.set()
    await second


async def test_artifact_database_failure_removes_unreferenced_file(tmp_path):
    class FailingRepository:
        async def create(self, **_values):
            raise RuntimeError("database write failed")

        async def storage_path_is_referenced(self, _path: str) -> bool:
            return False

    artifact_dir = tmp_path / "artifacts"
    storage = ArtifactStorageService(artifact_repo=FailingRepository(), base_dir=artifact_dir)
    with pytest.raises(RuntimeError, match="database write failed"):
        await storage.save_artifact("orphan.txt", b"uncommitted")

    assert list(artifact_dir.iterdir()) == []


async def test_artifact_commit_then_refresh_error_keeps_referenced_file(test_db_session, tmp_path, monkeypatch):
    from app.repositories.artifact_repo import ArtifactRepository

    artifact_dir = tmp_path / "artifacts"
    storage = ArtifactStorageService(artifact_repo=ArtifactRepository(test_db_session), base_dir=artifact_dir)
    original_create = storage.artifact_repo.create

    async def commit_then_fail_refresh(*args, **kwargs):
        await original_create(*args, **kwargs)
        raise RuntimeError("refresh failed after commit")

    monkeypatch.setattr(storage.artifact_repo, "create", commit_then_fail_refresh)
    with pytest.raises(RuntimeError, match="refresh failed"):
        await storage.save_artifact("kept.txt", b"committed")
    async with test_db_session() as session:
        from app.persistence.models import ArtifactORM

        artifact = await session.scalar(select(ArtifactORM).where(ArtifactORM.filename == "kept.txt"))
    assert artifact is not None
    assert Path(artifact.storage_path).exists(), "a file referenced by a committed row was removed during cleanup"


async def test_artifact_database_check_failure_preserves_file(tmp_path, caplog):
    class UnavailableRepository:
        async def create(self, **_values):
            raise RuntimeError("database write outcome unknown")

        async def storage_path_is_referenced(self, _path: str) -> bool:
            raise RuntimeError("database unavailable")

    artifact_dir = tmp_path / "artifacts"
    storage = ArtifactStorageService(artifact_repo=UnavailableRepository(), base_dir=artifact_dir)
    with pytest.raises(RuntimeError, match="outcome unknown"):
        await storage.save_artifact("uncertain.txt", b"preserve")

    files = list(artifact_dir.iterdir())
    assert len(files) == 1 and files[0].read_bytes() == b"preserve"
    assert "Could not verify whether artifact file" in caplog.text


async def test_artifact_cleanup_error_does_not_mask_database_failure(tmp_path, monkeypatch, caplog):
    class FailingRepository:
        async def create(self, **_values):
            raise RuntimeError("database write failed")

        async def storage_path_is_referenced(self, _path: str) -> bool:
            return False

    artifact_dir = tmp_path / "artifacts"
    storage = ArtifactStorageService(artifact_repo=FailingRepository(), base_dir=artifact_dir)
    original_unlink = Path.unlink

    def fail_unlink(_path, *args, **kwargs):
        raise OSError("filesystem denied cleanup")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(RuntimeError, match="database write failed"):
        await storage.save_artifact("uncleanable.txt", b"orphan")
    assert "Failed to remove uncommitted artifact file" in caplog.text
    monkeypatch.setattr(Path, "unlink", original_unlink)


async def test_runtime_artifact_points_to_actual_authenticated_download_without_raw_contents(client, test_db_session):
    content = b"def test_generated():\n    assert 2 + 2 == 4\n"
    response = await client.post("/api/artifacts/upload", files={"file": ("generated.py", content, "text/x-python")})
    assert response.status_code == 201
    artifact_id = response.json()["artifact_id"]
    async with test_db_session() as session:
        session.add(TaskORM(id="task", owner_id="owner", type="GENERATE_TEST", goal="Generated"))
        await session.flush()
        session.add(
            TaskArtifactORM(
                id="ref", task_id="task", artifact_id=artifact_id, name="generated.py", kind="GENERATED_TEST"
            )
        )
        await session.commit()
        snapshot = await RuntimeProjection(session).task("task", "owner")
        artifact = snapshot.artifacts[0]
        assert artifact.artifact_id == artifact_id and artifact.size_bytes == len(content)
        assert "def test_generated" not in snapshot.model_dump_json()
        assert not session.dirty
    downloaded = await client.get(f"/api/artifacts/{artifact_id}/download")
    assert downloaded.status_code == 200 and downloaded.content == content
