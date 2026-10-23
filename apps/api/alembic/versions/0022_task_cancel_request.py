"""Record a cancel request separately from the terminal write it may lead to.

Before this migration a cancel was a single unconditional `UPDATE agent_tasks SET status='CANCELLED'`
from whichever API replica served the request. That write could land on a task another replica was
still executing, overwriting its run state with a status that owner never produced (R18-B2). A
request is now its own fact: anyone allowed to see the task may record it, and only the lease owner
(or the recovery path, once the lease is provably gone) turns it into a terminal status.

Revision ID: 0022_task_cancel_request
Revises: 0021_artifact_actor_width
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_task_cancel_request"
down_revision = "0021_artifact_actor_width"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_tasks", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_tasks", sa.Column("cancel_requested_by", sa.String(120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_tasks") as batch:
        batch.drop_column("cancel_requested_by")
        batch.drop_column("cancel_requested_at")
