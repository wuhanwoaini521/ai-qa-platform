"""Widen stored_artifacts.created_by to the width of the label it actually stores.

A run's `requested_by` is a human label ("Recorder · checkout", "repair-verification:<id>"), and
artifacts are stamped with it so the artifact audit names the same actor as the run. The column was
declared 36 wide (a user-id width), which PostgreSQL rejects for those labels while SQLite silently
accepted them.

Revision ID: 0021_artifact_actor_width
Revises: 0020_task_lease
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_artifact_actor_width"
down_revision = "0020_task_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite does not enforce a VARCHAR length and rebuilding the table there would break the
    # later downgrade of 0015 (a rebuilt table cannot drop its own foreign-key column).
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column("stored_artifacts", "created_by", existing_type=sa.String(36), type_=sa.String(100))


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column("stored_artifacts", "created_by", existing_type=sa.String(100), type_=sa.String(36))
