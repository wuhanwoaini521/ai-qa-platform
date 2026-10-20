"""Give discovery runs a queryable evidence index instead of only a JSON projection.

Evidence used to live in three unrelated places (the run's `result` JSON, the event log and
artifact binaries), so nothing could answer "which elements, requests and actions did this run
capture, and with what confidence". The new tables store one row per structured fact plus the
candidate scenarios derived from them, keeping binary payloads in `stored_artifacts` by reference.

Revision ID: 0016_discovery_evidence
Revises: 0015_artifact_ownership
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_discovery_evidence"
down_revision = "0015_artifact_ownership"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discovery_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("evidence_id", sa.String(length=120), nullable=False),
        sa.Column("dedupe_key", sa.String(length=600), nullable=False),
        sa.Column("state_id", sa.String(length=64), nullable=True),
        sa.Column("step_id", sa.String(length=120), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("redacted", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["quality_discovery_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "evidence_id", name="uq_discovery_evidence_run_evidence"),
    )
    op.create_index("ix_discovery_evidence_project_id", "discovery_evidence", ["project_id"])
    op.create_index("ix_discovery_evidence_run_id", "discovery_evidence", ["run_id"])
    op.create_index("ix_discovery_evidence_kind", "discovery_evidence", ["kind"])
    op.create_index("ix_discovery_evidence_state_id", "discovery_evidence", ["state_id"])
    op.create_index("ix_discovery_evidence_created_at", "discovery_evidence", ["created_at"])
    op.create_index("ix_discovery_evidence_run_kind", "discovery_evidence", ["run_id", "kind"])
    op.create_index("ix_discovery_evidence_run_dedupe", "discovery_evidence", ["run_id", "dedupe_key"])
    op.create_index("ix_discovery_evidence_project_kind", "discovery_evidence", ["project_id", "kind"])

    op.create_table(
        "discovery_scenarios",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("url_template", sa.String(length=600), nullable=False),
        sa.Column("evidence_ids", sa.Text(), nullable=False),
        sa.Column("test_case_ids", sa.Text(), nullable=False),
        sa.Column("coverage_status", sa.String(length=30), nullable=False),
        sa.Column("match_method", sa.String(length=40), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["quality_discovery_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "scenario_id", name="uq_discovery_scenarios_run_scenario"),
    )
    op.create_index("ix_discovery_scenarios_project_id", "discovery_scenarios", ["project_id"])
    op.create_index("ix_discovery_scenarios_run_id", "discovery_scenarios", ["run_id"])
    op.create_index("ix_discovery_scenarios_coverage_status", "discovery_scenarios", ["coverage_status"])
    op.create_index("ix_discovery_scenarios_run_status", "discovery_scenarios", ["run_id", "coverage_status"])


def downgrade():
    for index in (
        "ix_discovery_scenarios_run_status",
        "ix_discovery_scenarios_coverage_status",
        "ix_discovery_scenarios_run_id",
        "ix_discovery_scenarios_project_id",
    ):
        op.drop_index(index, table_name="discovery_scenarios")
    op.drop_table("discovery_scenarios")

    for index in (
        "ix_discovery_evidence_project_kind",
        "ix_discovery_evidence_run_dedupe",
        "ix_discovery_evidence_run_kind",
        "ix_discovery_evidence_created_at",
        "ix_discovery_evidence_state_id",
        "ix_discovery_evidence_kind",
        "ix_discovery_evidence_run_id",
        "ix_discovery_evidence_project_id",
    ):
        op.drop_index(index, table_name="discovery_evidence")
    op.drop_table("discovery_evidence")
