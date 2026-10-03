"""Run reviewed, versioned migrations on an existing synchronous connection."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_config(connection=None):
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def upgrade_database(connection, revision="head"):
    command.upgrade(migration_config(connection), revision)


def downgrade_database(connection, revision):
    command.downgrade(migration_config(connection), revision)
