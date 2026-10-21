"""Keep model-assisted readings of uncovered scenarios beside, never on top of, the rule verdict.

A suggestion is a separate, reviewable row: it records which evidence the model read, what it
proposed, the grading source and the human decision. `discovery_scenarios` keeps the deterministic
coverage verdict, so re-running the rules can never be overwritten by a model.

Revision ID: 0017_discovery_suggestions
Revises: 0016_discovery_evidence
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_discovery_suggestions"
down_revision = "0016_discovery_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discovery_suggestions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("suggestion_id", sa.String(length=120), nullable=False),
        sa.Column("scenario_id", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("analysis_status", sa.String(length=30), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("invocation_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_ids", sa.Text(), nullable=False),
        sa.Column("related_case_ids", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("jev", sa.Text(), nullable=False),
        sa.Column("review", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("token_source", sa.String(length=20), nullable=False),
        sa.Column("error_type", sa.String(length=60), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["quality_discovery_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "scenario_id", "input_hash", name="uq_discovery_suggestions_input"),
    )
    op.create_index("ix_discovery_suggestions_project_id", "discovery_suggestions", ["project_id"])
    op.create_index("ix_discovery_suggestions_run_id", "discovery_suggestions", ["run_id"])
    op.create_index("ix_discovery_suggestions_scenario_id", "discovery_suggestions", ["scenario_id"])
    op.create_index("ix_discovery_suggestions_input_hash", "discovery_suggestions", ["input_hash"])
    op.create_index("ix_discovery_suggestions_analysis_status", "discovery_suggestions", ["analysis_status"])
    op.create_index("ix_discovery_suggestions_review_status", "discovery_suggestions", ["review_status"])
    op.create_index("ix_discovery_suggestions_run_review", "discovery_suggestions", ["run_id", "review_status"])
    op.create_index("ix_discovery_suggestions_run_status", "discovery_suggestions", ["run_id", "analysis_status"])


def downgrade():
    op.drop_index("ix_discovery_suggestions_run_status", table_name="discovery_suggestions")
    op.drop_index("ix_discovery_suggestions_run_review", table_name="discovery_suggestions")
    op.drop_index("ix_discovery_suggestions_review_status", table_name="discovery_suggestions")
    op.drop_index("ix_discovery_suggestions_analysis_status", table_name="discovery_suggestions")
    op.drop_index("ix_discovery_suggestions_input_hash", table_name="discovery_suggestions")
    op.drop_index("ix_discovery_suggestions_scenario_id", table_name="discovery_suggestions")
    op.drop_index("ix_discovery_suggestions_run_id", table_name="discovery_suggestions")
    op.drop_index("ix_discovery_suggestions_project_id", table_name="discovery_suggestions")
    op.drop_table("discovery_suggestions")
