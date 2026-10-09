import logging
from typing import AsyncGenerator

import anyio
from app.settings import get_config
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("app.persistence")


class Base(DeclarativeBase):
    pass


def enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """SQLite ignores ``ON DELETE CASCADE`` unless foreign keys are enforced.

    PostgreSQL enforces them unconditionally, so without this pragma the same
    code path behaves differently on the two backends.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def build_engine(database_url: str | None = None) -> AsyncEngine:
    """Create an engine for ``database_url`` with the backend-specific setup.

    Kept as a factory so tests can build an engine with the exact same
    configuration the application uses.
    """
    config = get_config().database
    database_url = database_url or config.url
    is_sqlite = "sqlite" in database_url.lower()

    engine_kwargs: dict = {}
    if is_sqlite:
        # Concurrent API polling and local pytest result writes can overlap. Give SQLite
        # time to release its single-writer lock instead of failing a healthy request.
        engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": config.sqlite_timeout_seconds}
    else:
        # PostgreSQL pooling parameters
        engine_kwargs["pool_size"] = config.pool_size
        engine_kwargs["max_overflow"] = config.max_overflow
        engine_kwargs["pool_pre_ping"] = True

    engine = create_async_engine(
        database_url,
        echo=config.echo,
        **engine_kwargs,
    )
    if is_sqlite:
        enable_sqlite_foreign_keys(engine)
    return engine


# SQLite / PostgreSQL compatible engine
engine = build_engine()

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

get_session = async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = async_session_factory()
    try:
        try:
            yield session
            await session.commit()
        except BaseException:
            with anyio.CancelScope(shield=True):
                try:
                    await session.rollback()
                except BaseException:
                    # Keep the request's original failure visible if cleanup also fails.
                    logger.exception("Database rollback failed while handling a request error")
            raise
    finally:
        # Request cancellation must not interrupt SQLAlchemy's async connection return.
        with anyio.CancelScope(shield=True):
            await session.close()


async def init_db() -> None:
    import app.persistence.models  # noqa: F401
    from app.persistence.migrations import upgrade_database

    async with engine.begin() as conn:
        await conn.run_sync(upgrade_database)


async def check_db_health() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            return True
    except Exception:
        return False
