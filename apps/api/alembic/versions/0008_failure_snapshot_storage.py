"""Store redacted failure snapshots and expiring encrypted browser storage state.

Revision ID: 0008_failure_snapshot_storage
Revises: 0007_quality_discovery_version
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_failure_snapshot_storage"
down_revision = "0007_quality_discovery_version"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("browser_sessions", sa.Column("failure_snapshot_json", sa.Text(), nullable=True))
    op.add_column("browser_sessions", sa.Column("encrypted_storage_state", sa.Text(), nullable=True))
    op.add_column("browser_sessions", sa.Column("storage_state_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_browser_sessions_storage_state_expires_at",
        "browser_sessions",
        ["storage_state_expires_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_browser_sessions_storage_state_expires_at", table_name="browser_sessions")
    op.drop_column("browser_sessions", "storage_state_expires_at")
    op.drop_column("browser_sessions", "encrypted_storage_state")
    op.drop_column("browser_sessions", "failure_snapshot_json")
