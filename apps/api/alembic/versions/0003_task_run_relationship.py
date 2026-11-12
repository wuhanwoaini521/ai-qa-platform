"""Nullable Task/Run and retry references, with ambiguity-safe legacy backfill."""

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0003_task_run_relationship"
down_revision = "0002_runtime_timestamps"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_columns = {column["name"] for column in inspector.get_columns("test_runs")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("test_runs")}
    for name, target in [
        ("task_id", "agent_tasks"),
        ("parent_run_id", "test_runs"),
        ("origin_failure_id", "failure_records"),
    ]:
        if name not in existing_columns:
            if connection.dialect.name == "sqlite":
                # SQLite supports adding a nullable REFERENCES column directly. This avoids
                # rebuilding test_runs while FK enforcement could cascade-delete its children.
                op.execute(
                    sa.text(
                        f"ALTER TABLE test_runs ADD COLUMN {name} VARCHAR(36) REFERENCES {target}(id) ON DELETE SET NULL"
                    )
                )
            else:
                op.add_column("test_runs", sa.Column(name, sa.String(36), nullable=True))
                op.create_foreign_key(f"fk_test_runs_{name}", "test_runs", target, [name], ["id"], ondelete="SET NULL")
            existing_columns.add(name)
        index_name = f"ix_test_runs_{name}"
        if index_name not in existing_indexes:
            op.create_index(index_name, "test_runs", [name])
            existing_indexes.add(index_name)
    runs = sa.table("test_runs", sa.column("id"), sa.column("project_id"), sa.column("task_id"))
    tasks = sa.table("agent_tasks", sa.column("id"), sa.column("project_id"), sa.column("context"))
    run_projects = {row.id: row.project_id for row in connection.execute(sa.select(runs.c.id, runs.c.project_id))}
    matches = {}
    unmatched = 0
    for row in connection.execute(sa.select(tasks)).mappings():
        try:
            context = json.loads(row["context"] or "{}")
        except (ValueError, TypeError):
            context = {}
        run_id = context.get("run_id") if isinstance(context, dict) else None
        if not isinstance(run_id, str):
            continue
        if run_id not in run_projects or run_projects[run_id] != row["project_id"]:
            unmatched += 1
        else:
            matches.setdefault(run_id, []).append(row["id"])
    matched = conflicted = 0
    for run_id, task_ids in matches.items():
        if len(task_ids) != 1:
            conflicted += 1
            continue
        connection.execute(
            runs.update().where(runs.c.id == run_id, runs.c.task_id.is_(None)).values(task_id=task_ids[0])
        )
        matched += 1
    logging.getLogger("alembic.runtime").warning(
        "Task/Run backfill matched=%d unmatched=%d conflicted=%d", matched, unmatched, conflicted
    )


def downgrade():
    for name in ["origin_failure_id", "parent_run_id", "task_id"]:
        op.drop_index(f"ix_test_runs_{name}", table_name="test_runs")
        if op.get_bind().dialect.name == "sqlite":
            # SQLite cannot drop a REFERENCES column in place. Keep the nullable columns; the
            # downgrade still removes their indexes, and the matching upgrade restores them.
            continue
        op.drop_constraint(f"fk_test_runs_{name}", "test_runs", type_="foreignkey")
        op.drop_column("test_runs", name)
