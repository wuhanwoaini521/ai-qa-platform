"""Versioned workflow definitions.

A published graph is never updated again: publishing flips the draft row to PUBLISHED, moves the
definition's pointer and opens a fresh draft copy, so a task that ran version N keeps resolving to
exactly the graph it ran.

Revision ID: 0019_workflow_definitions
Revises: 0018_ai_invocation_step
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_workflow_definitions"
down_revision = "0018_ai_invocation_step"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("published_version", sa.Integer(), nullable=True),
        sa.Column("draft_version", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_workflow_definitions_project_name"),
    )
    op.create_index("ix_workflow_definitions_project_id", "workflow_definitions", ["project_id"])
    op.create_table(
        "workflow_definition_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("definition_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("graph", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("issues", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by", sa.String(length=36), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["definition_id"], ["workflow_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "definition_id", "version", name="uq_workflow_definition_versions_definition_version"
        ),
    )
    op.create_index("ix_workflow_definition_versions_definition_id", "workflow_definition_versions", ["definition_id"])
    op.create_index("ix_workflow_definition_versions_project_id", "workflow_definition_versions", ["project_id"])
    op.create_index("ix_workflow_definition_versions_state", "workflow_definition_versions", ["state"])
    op.create_index(
        "ix_workflow_definition_versions_project_state", "workflow_definition_versions", ["project_id", "state"]
    )


def downgrade():
    op.drop_index("ix_workflow_definition_versions_project_state", table_name="workflow_definition_versions")
    op.drop_index("ix_workflow_definition_versions_state", table_name="workflow_definition_versions")
    op.drop_index("ix_workflow_definition_versions_project_id", table_name="workflow_definition_versions")
    op.drop_index("ix_workflow_definition_versions_definition_id", table_name="workflow_definition_versions")
    op.drop_table("workflow_definition_versions")
    op.drop_index("ix_workflow_definitions_project_id", table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
