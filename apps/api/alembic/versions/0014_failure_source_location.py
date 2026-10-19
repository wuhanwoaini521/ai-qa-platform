"""Store the source file and line a failure came from.

The run finaliser already resolves the failing frame to place a Studio breakpoint; persisting it on
the failure record lets the UI show and open the exact location without re-parsing the stack trace.

Revision ID: 0014_failure_source_location
Revises: 0013_project_ownership
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_failure_source_location"
down_revision = "0013_project_ownership"
branch_labels = None
depends_on = None

_COLUMNS = [("source_file", sa.String(500)), ("source_line", sa.Integer())]


def upgrade():
    connection = op.get_bind()
    existing = {column["name"] for column in sa.inspect(connection).get_columns("failure_records")}
    for name, column_type in _COLUMNS:
        # Tolerant of drift: a database already carrying the column (or a previous run that failed
        # halfway) must still start instead of raising "duplicate column name".
        if name in existing:
            continue
        op.add_column("failure_records", sa.Column(name, column_type, nullable=True))


def downgrade():
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("failure_records")}
    for name, _column_type in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("failure_records", name)
