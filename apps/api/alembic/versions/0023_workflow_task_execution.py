"""Bind Task Runtime tasks to immutable Workflow executions.

Revision ID: 0023_workflow_task_execution
Revises: 0022_task_cancel_request
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_workflow_task_execution"
down_revision = "0022_task_cancel_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_tasks") as batch:
        batch.add_column(sa.Column("workflow_execution_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("workflow_definition_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("workflow_version_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("workflow_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("workflow_checksum", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("workflow_idempotency_key", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("workflow_request_fingerprint", sa.String(length=64), nullable=True))
        batch.create_index("ix_agent_tasks_workflow_execution_id", ["workflow_execution_id"], unique=True)
        batch.create_index("ix_agent_tasks_workflow_definition_id", ["workflow_definition_id"])
        batch.create_index("ix_agent_tasks_workflow_version_id", ["workflow_version_id"])
        batch.create_unique_constraint(
            "uq_agent_tasks_workflow_idempotency",
            ["workflow_definition_id", "owner_id", "workflow_idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_tasks") as batch:
        batch.drop_constraint("uq_agent_tasks_workflow_idempotency", type_="unique")
        batch.drop_index("ix_agent_tasks_workflow_version_id")
        batch.drop_index("ix_agent_tasks_workflow_definition_id")
        batch.drop_index("ix_agent_tasks_workflow_execution_id")
        batch.drop_column("workflow_request_fingerprint")
        batch.drop_column("workflow_idempotency_key")
        batch.drop_column("workflow_checksum")
        batch.drop_column("workflow_version")
        batch.drop_column("workflow_version_id")
        batch.drop_column("workflow_definition_id")
        batch.drop_column("workflow_execution_id")
