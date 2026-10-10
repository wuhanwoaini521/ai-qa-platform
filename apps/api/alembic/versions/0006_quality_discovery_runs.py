"""Persist Quality Discovery runs and their linked quality map.

Revision ID: 0006_quality_discovery_runs
Revises: 0005_raise_ai_request_preflight_budget
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_quality_discovery_runs"
down_revision = "0005_raise_ai_request_preflight_budget"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quality_discovery_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("start_url", sa.String(length=2048), nullable=False),
        sa.Column("requirement_id", sa.String(length=36), nullable=True),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("allowed_domains", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("progress", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_discovery_runs_project_id", "quality_discovery_runs", ["project_id"])
    op.create_index("ix_quality_discovery_runs_requirement_id", "quality_discovery_runs", ["requirement_id"])
    op.create_index("ix_quality_discovery_runs_status", "quality_discovery_runs", ["status"])
    op.create_index("ix_quality_discovery_runs_created_at", "quality_discovery_runs", ["created_at"])


def downgrade():
    op.drop_index("ix_quality_discovery_runs_created_at", table_name="quality_discovery_runs")
    op.drop_index("ix_quality_discovery_runs_status", table_name="quality_discovery_runs")
    op.drop_index("ix_quality_discovery_runs_requirement_id", table_name="quality_discovery_runs")
    op.drop_index("ix_quality_discovery_runs_project_id", table_name="quality_discovery_runs")
    op.drop_table("quality_discovery_runs")
