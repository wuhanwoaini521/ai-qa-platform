"""Raise the default AI request preflight budget to support long-context models.

Revision ID: 0005_raise_ai_request_preflight_budget
Revises: 0004_one_running_failure_analysis
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_raise_ai_request_preflight_budget"
down_revision = "0004_one_running_failure_analysis"
branch_labels = None
depends_on = None


def upgrade():
    # Existing 16k values were the old application default. Preserve any custom
    # budgets while removing that default ceiling for long-context models.
    op.execute(
        sa.text(
            "UPDATE ai_provider_configs "
            "SET max_request_tokens = 1000000 "
            "WHERE max_request_tokens = 16000"
        )
    )


def downgrade():
    op.execute(
        sa.text(
            "UPDATE ai_provider_configs "
            "SET max_request_tokens = 16000 "
            "WHERE max_request_tokens = 1000000"
        )
    )
