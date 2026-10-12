"""Persist scalar Jev signals with decision invocation telemetry.

Revision ID: 0009_decision_signal_values
Revises: 0008_failure_snapshot_storage
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_decision_signal_values"
down_revision = "0008_failure_snapshot_storage"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_invocations", sa.Column("decision_value", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("ai_invocations", "decision_value")
