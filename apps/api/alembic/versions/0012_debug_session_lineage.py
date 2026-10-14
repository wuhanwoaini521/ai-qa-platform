"""Persist debugger sessions and their originating failure execution.

Revision ID: 0012_debug_session_lineage
Revises: 0011_recorder_element_evidence
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_debug_session_lineage"
down_revision = "0011_recorder_element_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "debug_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("nodeid", sa.String(1000), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("test_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "execution_id", sa.String(36), sa.ForeignKey("test_executions.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("failure_id", sa.String(36), sa.ForeignKey("failure_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="STARTING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("owner_id", "workspace_id", "run_id", "execution_id", "failure_id", "status"):
        op.create_index(f"ix_debug_sessions_{column}", "debug_sessions", [column])


def downgrade():
    for column in ("status", "failure_id", "execution_id", "run_id", "workspace_id", "owner_id"):
        op.drop_index(f"ix_debug_sessions_{column}", table_name="debug_sessions")
    op.drop_table("debug_sessions")
