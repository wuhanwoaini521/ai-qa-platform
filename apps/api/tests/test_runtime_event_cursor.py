from app.persistence.models import TaskEventORM, TaskORM
from app.repositories.task_repo import TaskRepository


async def test_task_detail_is_bounded_but_cursor_stream_retains_full_history(test_db_session):
    async with test_db_session() as session:
        task = TaskORM(id="cursor-task", owner_id="owner", type="RUN_REGRESSION", goal="Cursor", status="COMPLETED")
        session.add(task)
        await session.flush()
        session.add_all(
            TaskEventORM(task_id=task.id, type="step.progress", payload={"sequence": i}) for i in range(750)
        )
        await session.commit()
        repo = TaskRepository(session)
        detail = await repo.get_detail(task)
        assert len(detail.events) == 500 and detail.events_truncated
        assert detail.events[0].payload["sequence"] == 250
        assert detail.event_cursor == detail.events[-1].id
        cursor = 0
        replay = []
        while events := await repo.events_after(task.id, cursor):
            replay.extend(event.id for event in events)
            cursor = events[-1].id
        assert len(replay) == len(set(replay)) == 750
        assert replay == sorted(replay)
        assert not session.dirty
