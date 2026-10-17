"""Run reviewed, versioned migrations on an existing synchronous connection."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

#: Alembic creates ``alembic_version.version_num`` as ``VARCHAR(32)``. SQLite ignores the
#: declared length, PostgreSQL does not, and revision ids such as
#: ``0005_raise_ai_request_preflight_budget`` are longer, so a fresh PostgreSQL database
#: failed on the third revision.
_VERSION_COLUMN_WIDTH = 128


def ensure_version_column_capacity(connection) -> None:
    """Widen the Alembic version column so long revision ids fit on every backend.

    Idempotent: creates the table with a wide column when missing and rewrites an existing
    narrow column, so both fresh and already-migrated databases are handled.
    """
    if connection.dialect.name != "postgresql":
        # SQLite does not enforce VARCHAR length; other backends do not support this ALTER form.
        return
    width = _VERSION_COLUMN_WIDTH
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            f"version_num VARCHAR({width}) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    connection.execute(text(f"ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR({width})"))


def migration_config(connection=None):
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def upgrade_database(connection, revision="head"):
    ensure_version_column_capacity(connection)
    command.upgrade(migration_config(connection), revision)


def downgrade_database(connection, revision):
    command.downgrade(migration_config(connection), revision)
