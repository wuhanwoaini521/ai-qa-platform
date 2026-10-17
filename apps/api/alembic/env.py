"""Alembic CLI and application startup share the same migration runner."""

import asyncio

import app.persistence.models  # noqa: F401
from alembic import context
from app.persistence.database import Base
from app.settings import settings
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config


def migrate(connection):
    from app.persistence.migrations import ensure_version_column_capacity

    ensure_version_column_capacity(connection)
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async():
    engine = create_async_engine(config.get_main_option("sqlalchemy.url") or settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migration is unavailable: historical schema adoption requires inspection.")
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    asyncio.run(run_async())
