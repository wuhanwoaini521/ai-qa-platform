"""Persist recorder element evidence with its automation binding.

Revision ID: 0011_recorder_element_evidence
Revises: 0010_locator_repair_state_machine
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_recorder_element_evidence"
down_revision = "0010_locator_repair_state_machine"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("automation_bindings", sa.Column("recorder_evidence_bundle", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("automation_bindings", "recorder_evidence_bundle")
