"""Record provenance of derived execution times and real TaskStep event identity."""

import json
import math
from datetime import timedelta

import sqlalchemy as sa
from alembic import op

revision = "0002_runtime_timestamps"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("test_executions", sa.Column("timestamp_source", sa.String(20), nullable=True))
    op.add_column("agent_task_events", sa.Column("step_id", sa.String(36), nullable=True))
    op.create_index("ix_task_event_step_cursor", "agent_task_events", ["task_id", "step_id", "id"])
    connection = op.get_bind()
    executions = sa.table(
        "test_executions",
        sa.column("id"),
        sa.column("started_at", sa.DateTime()),
        sa.column("finished_at", sa.DateTime()),
        sa.column("duration_ms", sa.Float()),
        sa.column("timestamp_source"),
    )
    for row in connection.execute(sa.select(executions)).mappings():
        duration = row["duration_ms"]
        if (
            row["finished_at"]
            and row["started_at"] == row["finished_at"]
            and isinstance(duration, (int, float))
            and math.isfinite(duration)
            and duration > 0
        ):
            connection.execute(
                executions.update()
                .where(executions.c.id == row["id"])
                .values(started_at=row["finished_at"] - timedelta(milliseconds=duration), timestamp_source="derived")
            )
    steps = sa.table("agent_task_steps", sa.column("id"), sa.column("task_id"))
    identities = {row.id: row.task_id for row in connection.execute(sa.select(steps))}
    events = sa.table(
        "agent_task_events", sa.column("id"), sa.column("task_id"), sa.column("payload"), sa.column("step_id")
    )
    for row in connection.execute(sa.select(events)).mappings():
        try:
            payload = json.loads(row["payload"] or "{}")
        except (ValueError, TypeError):
            continue
        step_id = payload.get("step_id") if isinstance(payload, dict) else None
        if isinstance(step_id, str) and identities.get(step_id) == row["task_id"]:
            connection.execute(events.update().where(events.c.id == row["id"]).values(step_id=step_id))


def downgrade():
    op.drop_index("ix_task_event_step_cursor", table_name="agent_task_events")
    # SQLite supports DROP COLUMN without rebuilding parent tables (and cascading child rows).
    op.drop_column("agent_task_events", "step_id")
    op.drop_column("test_executions", "timestamp_source")
    # Corrected historical start times remain corrected; no timestamp is invented on reversal.
