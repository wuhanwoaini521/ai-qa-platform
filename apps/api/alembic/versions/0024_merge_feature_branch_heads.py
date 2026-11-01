"""Merge the mainline workflow and next-sprint project-SUT migration heads.

Revision ID: 0024_merge_feature_branch_heads
Revises: 0016_project_sut_and_run_identity, 0023_workflow_task_execution
"""

from __future__ import annotations

revision = "0024_merge_feature_branch_heads"
down_revision = ("0016_project_sut_and_run_identity", "0023_workflow_task_execution")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Join the diverged histories; both parent revisions already apply their own schema changes."""
    pass


def downgrade() -> None:
    """No schema changes are introduced by this revision."""
    pass
