import anyio
import pytest
from app.persistence import database
from sqlalchemy import text


@pytest.mark.asyncio
async def test_get_db_returns_connection_when_request_is_cancelled(test_db_session):
    request_started = anyio.Event()

    async def request_scope():
        dependency = database.get_db()
        try:
            session = await anext(dependency)
            await session.execute(text("SELECT 1"))
            request_started.set()
            await anyio.sleep_forever()
        finally:
            await dependency.aclose()

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(request_scope)
        await request_started.wait()
        tasks.cancel_scope.cancel()

    assert database.engine.sync_engine.pool.checkedout() == 0
    async with database.engine.connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1
