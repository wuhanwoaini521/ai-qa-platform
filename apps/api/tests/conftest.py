import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from app.main import app
from app.persistence.database import Base, get_db
from app.settings import settings
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db_session(tmp_path: Path):
    db_file = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(db_url, echo=False, connect_args={"check_same_thread": False})
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with async_session() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db] = override_get_db

    yield async_session

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_db_session, tmp_path: Path):
    # Set workspace storage to temporary test directory
    test_ws_dir = tmp_path / "workspaces"
    test_ws_dir.mkdir(parents=True, exist_ok=True)
    settings.workspace_storage_dir = test_ws_dir

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
