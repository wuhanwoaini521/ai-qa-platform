"""Give every stored artifact an owner: the project it belongs to and who created it.

Artifacts were addressed by opaque id only, and the artifact routes enforced no project scope, so a
stored screenshot or evidence bundle was reachable by any authenticated caller. Persisting the
project and the creating actor lets the existing project ACL guard those routes and leaves an audit
trail on the row itself.

Revision ID: 0015_artifact_ownership
Revises: 0014_failure_source_location
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_artifact_ownership"
down_revision = "0014_failure_source_location"
branch_labels = None
depends_on = None

_INDEX = "ix_stored_artifacts_project_id"
_FK = "fk_stored_artifacts_project_id"


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {column["name"] for column in inspector.get_columns("stored_artifacts")}
    indexes = {index["name"] for index in inspector.get_indexes("stored_artifacts")}
    if "project_id" not in columns:
        if connection.dialect.name == "sqlite":
            # SQLite cannot add a named constraint in place. A REFERENCES column carries the same
            # delete behaviour without rebuilding a table that already holds artifacts (as in 0013).
            op.execute(
                sa.text(
                    "ALTER TABLE stored_artifacts ADD COLUMN project_id VARCHAR(36) "
                    "REFERENCES projects(id) ON DELETE SET NULL"
                )
            )
        else:
            op.add_column("stored_artifacts", sa.Column("project_id", sa.String(36), nullable=True))
            op.create_foreign_key(_FK, "stored_artifacts", "projects", ["project_id"], ["id"], ondelete="SET NULL")
    # Guarded separately so a database stamped by an interrupted run still gets its lookup index.
    if _INDEX not in indexes:
        op.create_index(_INDEX, "stored_artifacts", ["project_id"])
    if "created_by" not in columns:
        op.add_column("stored_artifacts", sa.Column("created_by", sa.String(36), nullable=True))


def downgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {column["name"] for column in inspector.get_columns("stored_artifacts")}
    indexes = {index["name"] for index in inspector.get_indexes("stored_artifacts")}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name="stored_artifacts")
    if "project_id" in columns:
        if connection.dialect.name != "sqlite":
            op.drop_constraint(_FK, "stored_artifacts", type_="foreignkey")
        op.drop_column("stored_artifacts", "project_id")
    if "created_by" in columns:
        op.drop_column("stored_artifacts", "created_by")
