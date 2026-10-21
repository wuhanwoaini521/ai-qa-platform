"""Let an AI invocation say which step of a task it belongs to.

The execution tree shows a provider call under the step that made it. Before this column the only
honest answer was UNKNOWN; the orchestrator already tracks the active step in a context variable,
so the writer needs no call-site changes. Historical rows keep ``NULL`` — an unknown step is not
reconstructed from timings.

Revision ID: 0018_ai_invocation_step
Revises: 0017_discovery_suggestions
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_ai_invocation_step"
down_revision = "0017_discovery_suggestions"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_invocations") as batch:
        batch.add_column(sa.Column("step_id", sa.String(length=36), nullable=True))
        batch.create_index("ix_ai_invocations_step", ["step_id"])


def downgrade():
    with op.batch_alter_table("ai_invocations") as batch:
        batch.drop_index("ix_ai_invocations_step")
        batch.drop_column("step_id")
