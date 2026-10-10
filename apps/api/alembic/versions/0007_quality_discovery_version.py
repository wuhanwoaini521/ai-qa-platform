"""Add optimistic concurrency control for Quality Discovery result writes.

Revision ID: 0007_quality_discovery_version
Revises: 0006_quality_discovery_runs
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_quality_discovery_version"
down_revision = "0006_quality_discovery_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "quality_discovery_runs",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade():
    op.drop_column("quality_discovery_runs", "version")
