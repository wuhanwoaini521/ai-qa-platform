from pathlib import Path

import pytest_asyncio
from app.main import app as fastapi_app
from app.persistence import database as db_module
from app.persistence import models as models_module  # noqa: F401
from app.persistence.database import Base, get_db
from app.settings import settings
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def test_db_session(tmp_path: Path):
    db_file = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(db_url, echo=False, connect_args={"check_same_thread": False})
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    orig_factory = getattr(db_module, "async_session_factory", None)
    orig_get_session = getattr(db_module, "get_session", None)

    db_module.async_session_factory = async_session
    db_module.get_session = async_session

    async def override_get_db():
        async with async_session() as session:
            yield session
            await session.commit()

    fastapi_app.dependency_overrides[get_db] = override_get_db

    yield async_session

    if orig_factory is not None:
        db_module.async_session_factory = orig_factory
    if orig_get_session is not None:
        db_module.get_session = orig_get_session
    fastapi_app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_db_session, tmp_path: Path):
    # Set workspace storage to temporary test directory
    test_ws_dir = tmp_path / "workspaces"
    test_ws_dir.mkdir(parents=True, exist_ok=True)
    settings.workspace_storage_dir = test_ws_dir

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
