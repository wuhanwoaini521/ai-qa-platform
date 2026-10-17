"""PostgreSQL is provisioned by the real Alembic chain, not by ``create_all``.

The API test fixtures build the schema from the SQLAlchemy models, so a broken migration only
surfaces in production startup. This test applies the migrations to a scratch database on the
configured PostgreSQL server and fails on model/migration drift.
"""

from __future__ import annotations

import os
import uuid

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.persistence.database import Base
from app.persistence.migrations import migration_config, upgrade_database
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = [pytest.mark.postgres, pytest.mark.integration]

#: Alembic reports ``Enum(native_enum=False)`` columns as a type change on every run even though
#: the migrated column is the same VARCHAR plus CHECK constraint the model declares.
_KNOWN_ENUM_FALSE_POSITIVE = "modify_type"


def _is_known_false_positive(diff) -> bool:
    entry = repr(diff)
    return _KNOWN_ENUM_FALSE_POSITIVE in entry and "'locator_repairs'" in entry and "'state'" in entry


async def test_migrations_apply_on_fresh_database_and_match_models() -> None:
    url = make_url(os.environ["AI_QA_TEST_DATABASE_URL"])
    scratch = f"aiqa_migrations_{uuid.uuid4().hex[:8]}"

    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{scratch}"'))

    engine = create_async_engine(url.set(database=scratch))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(upgrade_database)

        async with engine.connect() as connection:
            applied = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            drifts = await connection.run_sync(
                lambda sync_connection: compare_metadata(MigrationContext.configure(sync_connection), Base.metadata)
            )

        expected_head = ScriptDirectory.from_config(migration_config()).get_current_head()
        assert applied == expected_head, f"database is at {applied}, expected {expected_head}"
        unexpected = [diff for diff in drifts if not _is_known_false_positive(diff)]
        assert unexpected == [], f"model/migration drift: {unexpected}"
    finally:
        await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
        await admin.dispose()
