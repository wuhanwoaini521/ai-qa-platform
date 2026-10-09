from __future__ import annotations

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.persistence import database
from app.persistence.migrations import migration_config


class SqlAlchemyDatabaseHealthProbe:
    async def check(self) -> dict[str, object]:
        if not await database.check_db_health():
            return {"status": "error", "message": "Database is unreachable."}
        head_revision = ScriptDirectory.from_config(migration_config()).get_current_head()
        async with database.engine.connect() as connection:
            current_revision = await connection.run_sync(
                lambda conn: MigrationContext.configure(conn).get_current_revision()
            )
        pending = current_revision != head_revision
        return {
            "status": "error" if pending else "ok",
            "message": "Database schema update pending." if pending else "Database connected; schema is current.",
            "current_revision": current_revision,
            "head_revision": head_revision,
        }
