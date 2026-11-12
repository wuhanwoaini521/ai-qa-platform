"""Project SUT address, overview visibility, and requirement/case identity on runs and failures.

Three gaps this closes:

1. A project had no place to record the system-under-test address, so every recording and generated
   test had to be told a URL by hand.
2. Local probe/demo projects could only be removed from dashboard statistics by deleting data; a
   reversible flag lets them stay in the database but out of the overview.
3. Test runs and failure records carried only a project, so the UI had to pass requirementId/caseId
   through URLs manually and the identity was lost after a reload.

Revision ID: 0016_project_sut_and_run_identity
Revises: 0015_artifact_ownership
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_project_sut_and_run_identity"
down_revision = "0015_artifact_ownership"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table)}


def upgrade():
    is_sqlite = op.get_bind().dialect.name == "sqlite"

    project_columns = _columns("projects")
    if "sut_base_url" not in project_columns:
        op.add_column("projects", sa.Column("sut_base_url", sa.String(500), nullable=True))
    if "hidden_from_overview" not in project_columns:
        op.add_column(
            "projects",
            sa.Column("hidden_from_overview", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    for table, column, target in (
        ("test_runs", "requirement_id", "requirements"),
        ("test_runs", "case_id", "test_cases"),
        ("failure_records", "requirement_id", "requirements"),
        ("failure_records", "case_id", "test_cases"),
    ):
        index_name = f"ix_{table}_{column}"
        if column not in _columns(table):
            if is_sqlite:
                op.execute(
                    sa.text(
                        f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR(36) "
                        f"REFERENCES {target}(id) ON DELETE SET NULL"
                    )
                )
            else:
                op.add_column(
                    table,
                    sa.Column(
                        column,
                        sa.String(36),
                        sa.ForeignKey(f"{target}.id", ondelete="SET NULL"),
                        nullable=True,
                    ),
                )
        if index_name not in _indexes(table):
            op.create_index(index_name, table, [column])


def downgrade():
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    for table, index_name, column in (
        ("test_runs", "ix_test_runs_case_id", "case_id"),
        ("test_runs", "ix_test_runs_requirement_id", "requirement_id"),
        ("failure_records", "ix_failure_records_case_id", "case_id"),
        ("failure_records", "ix_failure_records_requirement_id", "requirement_id"),
    ):
        if index_name in _indexes(table):
            op.drop_index(index_name, table_name=table)
        if column in _columns(table) and not is_sqlite:
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)

    project_columns = _columns("projects")
    if "hidden_from_overview" in project_columns and not is_sqlite:
        with op.batch_alter_table("projects") as batch:
            batch.drop_column("hidden_from_overview")
    if "sut_base_url" in project_columns and not is_sqlite:
        with op.batch_alter_table("projects") as batch:
            batch.drop_column("sut_base_url")
    # SQLite batch rebuilds can cascade-delete executions and other children when rebuilding
    # referenced parent tables. Keep the nullable legacy columns on downgrade; older code
    # safely ignores extra columns, and upgrade() recreates any indexes that were removed.
