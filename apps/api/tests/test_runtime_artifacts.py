from app.persistence.models import TaskArtifactORM, TaskORM
from app.services.runtime_projection import RuntimeProjection


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
