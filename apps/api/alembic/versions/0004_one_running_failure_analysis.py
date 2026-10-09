"""Allow only one active failure analysis per failure.

Revision ID: 0004_one_running_failure_analysis
Revises: 0003_task_run_relationship
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_one_running_failure_analysis"
down_revision = "0003_task_run_relationship"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve the newest in-flight record when upgrading databases that already
    # contain duplicate active analyses. Older active records become recoverable
    # history instead of preventing the invariant from being installed.
    op.execute(
        sa.text(
            """
            UPDATE failure_analyses
            SET status = 'INTERRUPTED', finished_at = CURRENT_TIMESTAMP
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY failure_id
                               ORDER BY created_at DESC, id DESC
                           ) AS position
                    FROM failure_analyses
                    WHERE status = 'RUNNING'
                ) AS ranked
                WHERE position > 1
            )
            """
        )
    )
    op.create_index(
        "uq_failure_analyses_one_running_per_failure",
        "failure_analyses",
        ["failure_id"],
        unique=True,
        sqlite_where=sa.text("status = 'RUNNING'"),
        postgresql_where=sa.text("status = 'RUNNING'"),
    )


def downgrade():
    op.drop_index("uq_failure_analyses_one_running_per_failure", table_name="failure_analyses")
