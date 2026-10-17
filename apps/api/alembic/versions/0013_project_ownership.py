"""Add project ownership (owner_id, team_id) for project-scoped access control.

Revision ID: 0013_project_ownership
Revises: 0012_debug_session_lineage
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_project_ownership"
down_revision = "0012_debug_session_lineage"
branch_labels = None
depends_on = None

_COLUMNS = [("owner_id", "users"), ("team_id", "teams")]


def upgrade():
    # Nullable on purpose: pre-existing projects stay admin-only until a security admin claims them,
    # so this migration never grants access that was not explicitly recorded.
    connection = op.get_bind()
    for name, target in _COLUMNS:
        if connection.dialect.name == "sqlite":
            # SQLite can add a nullable REFERENCES column directly. Rebuilding `projects` instead
            # would cascade-delete every child row while FK enforcement is on (same reason as 0003).
            op.execute(
                sa.text(f"ALTER TABLE projects ADD COLUMN {name} VARCHAR(36) REFERENCES {target}(id) ON DELETE SET NULL")
            )
        else:
            op.add_column("projects", sa.Column(name, sa.String(36), nullable=True))
            op.create_foreign_key(f"fk_projects_{name}", "projects", target, [name], ["id"], ondelete="SET NULL")
        op.create_index(f"ix_projects_{name}", "projects", [name])


def downgrade():
    for name, _target in reversed(_COLUMNS):
        op.drop_index(f"ix_projects_{name}", table_name="projects")
        if op.get_bind().dialect.name != "sqlite":
            op.drop_constraint(f"fk_projects_{name}", "projects", type_="foreignkey")
        op.drop_column("projects", name)
