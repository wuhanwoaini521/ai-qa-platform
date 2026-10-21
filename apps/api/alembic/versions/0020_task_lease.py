"""Give a running task an owner that a second process can see.

Before this migration the only claim was a conditional status update, which stops two processes from
starting the same task but says nothing about which process owns it afterwards: a startup recovery in
a second replica blocked tasks that the first replica was still executing, and a zombie process could
still write a terminal state after its work was resumed elsewhere. The lease columns answer both
questions in the database, so no in-process lock is involved.

``lease_token`` is a fencing token: every claim increments it, so a writer that lost the lease can be
told apart from the current owner. Historical rows keep ``NULL`` and are treated as unleased.

Revision ID: 0020_task_lease
Revises: 0019_workflow_definitions
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_task_lease"
down_revision = "0019_workflow_definitions"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("agent_tasks") as batch:
        batch.add_column(sa.Column("lease_owner", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("lease_token", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_agent_tasks_lease_expires_at", ["lease_expires_at"])


def downgrade():
    with op.batch_alter_table("agent_tasks") as batch:
        batch.drop_index("ix_agent_tasks_lease_expires_at")
        batch.drop_column("lease_expires_at")
        batch.drop_column("lease_token")
        batch.drop_column("lease_owner")
