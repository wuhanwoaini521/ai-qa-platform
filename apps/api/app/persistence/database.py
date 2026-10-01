import logging
from typing import AsyncGenerator

from app.settings import settings
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


def build_engine(database_url: str = settings.database_url) -> AsyncEngine:
    """Create an engine for ``database_url`` with the backend-specific setup.

    Kept as a factory so tests can build an engine with the exact same
    configuration the application uses.
    """
    is_sqlite = "sqlite" in database_url.lower()

    engine_kwargs: dict = {}
    if is_sqlite:
        # Concurrent API polling and local pytest result writes can overlap. Give SQLite
        # time to release its single-writer lock instead of failing a healthy request.
        engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        # PostgreSQL pooling parameters
        engine_kwargs["pool_size"] = 20
        engine_kwargs["max_overflow"] = 10
        engine_kwargs["pool_pre_ping"] = True

    engine = create_async_engine(
        database_url,
        echo=False,
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
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


#: Columns added after the first release. `create_all` creates missing tables but never alters an
#: existing one, so an already-deployed database needs these added explicitly. This is a stopgap
#: until the platform adopts a migration framework; the names are code constants, never user input.
ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("test_runs", "log_output", "TEXT"),
    ("test_runs", "parallel_workers", "INTEGER NOT NULL DEFAULT 1"),
    ("browser_sessions", "page_evidence_json", "TEXT"),
    ("ai_invocations", "decision_name", "VARCHAR(128)"),
    ("ai_invocations", "decision_choice", "VARCHAR(128)"),
    ("ai_invocations", "decision_confidence", "FLOAT"),
    ("agent_tasks", "max_ai_calls", "INTEGER NOT NULL DEFAULT 8"),
)


async def apply_additive_columns(conn) -> list[str]:
    """Add columns that exist in the models but not yet in the database. Returns what it added."""
    added: list[str] = []
    sqlite = "sqlite" in settings.database_url.lower()
    for table, column, ddl_type in ADDITIVE_COLUMNS:
        if sqlite:
            result = await conn.execute(text(f"PRAGMA table_info({table})"))
            existing = {row[1] for row in result.fetchall()}
        else:
            result = await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = :table"),
                {"table": table},
            )
            existing = {row[0] for row in result.fetchall()}
        if not existing or column in existing:
            continue
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
        added.append(f"{table}.{column}")
    return added


async def init_db() -> None:
    import app.persistence.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for added in await apply_additive_columns(conn):
            logger.warning("Added missing column %s (no migration framework yet)", added)


async def check_db_health() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            return True
    except Exception:
        return False
