"""Persist LocatorRepair state and correlate AI invocations.

Revision ID: 0010_locator_repair_state_machine
Revises: 0009_decision_signal_values
"""

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0010_locator_repair_state_machine"
down_revision = "0009_decision_signal_values"
branch_labels = None
depends_on = None

_STATES = (
    "CREATED",
    "ANALYZING",
    "DECIDING",
    "VERIFYING_CANDIDATE",
    "PATCH_READY",
    "APPLYING",
    "PATCH_APPLIED",
    "VERIFYING_FIX",
    "VERIFIED",
    "FAILED",
    "BLOCKED",
    "NOT_APPLICABLE",
    "ROLLED_BACK",
)
_TERMINAL_STATES = {"BLOCKED", "FAILED", "NOT_APPLICABLE", "VERIFIED", "ROLLED_BACK"}
_REASON_CODE = re.compile(r"^[A-Z0-9_:-]{1,128}$")


def _json_value(value):
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def _datetime_value(value):
    if isinstance(value, datetime) or value is None:
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _legacy_state(result, events, status, failure_proposal):
    state = result.get("repair_state")
    if state in _STATES:
        selected_proposal = result.get("repair_proposal") or {}
        if (
            state in {"PATCH_READY", "APPLYING"}
            and isinstance(failure_proposal, dict)
            and failure_proposal.get("applied") is True
            and selected_proposal.get("proposed_locator") == failure_proposal.get("proposed_locator")
        ):
            return "PATCH_APPLIED"
        return state

    if isinstance(events, list):
        for event in reversed(events):
            if not isinstance(event, dict):
                continue
            metadata = event.get("metadata") or {}
            event_state = metadata.get("state") or metadata.get("repair_state")
            if event_state in _STATES and (
                event.get("stage") == "repair" or str(event.get("type", "")).startswith("repair.")
            ):
                return event_state

    proposal = result.get("repair_proposal")
    if isinstance(proposal, dict):
        if proposal.get("applied") is True:
            return "PATCH_APPLIED"
        return "PATCH_READY"
    if status == "RUNNING" and any(isinstance(event, dict) and event.get("stage") == "repair" for event in events):
        return "ANALYZING"
    return None


def _reason_code(result, state):
    raw = result.get("block_reason") or result.get("reason")
    if isinstance(raw, str) and _REASON_CODE.fullmatch(raw):
        return raw
    if state == "BLOCKED":
        return "LEGACY_BLOCKED"
    if state == "FAILED":
        return "LEGACY_FAILURE"
    return None


def upgrade():
    op.create_table(
        "locator_repairs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("failure_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("block_reason", sa.String(length=128), nullable=True),
        sa.Column("candidate_id", sa.String(length=128), nullable=True),
        sa.Column("verification_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN (" + ", ".join(repr(state) for state in _STATES) + ")",
            name="ck_locator_repairs_state",
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["failure_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["failure_id"], ["failure_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verification_run_id"], ["test_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", name="uq_locator_repairs_analysis_id"),
    )
    op.create_index("ix_locator_repairs_failure_id", "locator_repairs", ["failure_id"], unique=False)
    op.create_index("ix_locator_repairs_state", "locator_repairs", ["state"], unique=False)
    op.create_index("ix_locator_repairs_verification_run_id", "locator_repairs", ["verification_run_id"], unique=False)
    op.create_index("ix_locator_repairs_created_at", "locator_repairs", ["created_at"], unique=False)

    op.add_column("ai_invocations", sa.Column("locator_repair_id", sa.String(length=36), nullable=True))
    with op.batch_alter_table("ai_invocations") as batch_op:
        batch_op.create_foreign_key(
            "fk_ai_invocations_locator_repair_id_locator_repairs",
            "locator_repairs",
            ["locator_repair_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_ai_invocations_locator_repair_id", "ai_invocations", ["locator_repair_id"], unique=False)

    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.text(
                "SELECT fa.id, fa.failure_id, fa.status, fa.result, fa.events, fa.created_at, fa.finished_at, "
                "fr.repair_proposal AS failure_proposal "
                "FROM failure_analyses AS fa "
                "LEFT JOIN failure_records AS fr ON fr.id = fa.failure_id "
                "ORDER BY fa.created_at, fa.id"
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        result = _json_value(row["result"])
        if not isinstance(result, dict):
            result = {}
        events = _json_value(row["events"])
        if not isinstance(events, list):
            events = []
        failure_proposal = _json_value(row["failure_proposal"])
        if not isinstance(failure_proposal, dict):
            failure_proposal = {}
        state = _legacy_state(result, events, row["status"], failure_proposal)
        if state is None:
            continue
        proposal = result.get("repair_proposal") or {}
        if not isinstance(proposal, dict):
            proposal = {}
        selection = result.get("selection") or {}
        if not isinstance(selection, dict):
            selection = {}
        created_at = _datetime_value(row["created_at"])
        finished_at = _datetime_value(row["finished_at"])
        now = finished_at or created_at or datetime.now(timezone.utc)
        terminal = finished_at if state in _TERMINAL_STATES else None
        verification_run_id = result.get("verification_run_id")
        if verification_run_id and not connection.scalar(
            sa.text("SELECT 1 FROM test_runs WHERE id = :id"), {"id": verification_run_id}
        ):
            verification_run_id = None
        candidate_id = (
            proposal.get("candidate_id") or selection.get("candidate_id") or failure_proposal.get("candidate_id")
        )
        candidate_id = str(candidate_id) if candidate_id and len(str(candidate_id)) <= 128 else None
        connection.execute(
            sa.text(
                "INSERT INTO locator_repairs "
                "(id, failure_id, analysis_id, state, block_reason, candidate_id, verification_run_id, "
                "created_at, updated_at, finished_at) "
                "VALUES (:id, :failure_id, :analysis_id, :state, :block_reason, :candidate_id, "
                ":verification_run_id, :created_at, :updated_at, :finished_at)"
            ),
            {
                "id": str(uuid4()),
                "failure_id": row["failure_id"],
                "analysis_id": row["id"],
                "state": state,
                "block_reason": _reason_code(result, state),
                "candidate_id": candidate_id,
                "verification_run_id": verification_run_id,
                "created_at": created_at or now,
                "updated_at": now,
                "finished_at": terminal,
            },
        )


def downgrade():
    op.drop_index("ix_ai_invocations_locator_repair_id", table_name="ai_invocations")
    with op.batch_alter_table("ai_invocations") as batch_op:
        batch_op.drop_constraint("fk_ai_invocations_locator_repair_id_locator_repairs", type_="foreignkey")
    op.drop_column("ai_invocations", "locator_repair_id")
    op.drop_index("ix_locator_repairs_created_at", table_name="locator_repairs")
    op.drop_index("ix_locator_repairs_verification_run_id", table_name="locator_repairs")
    op.drop_index("ix_locator_repairs_state", table_name="locator_repairs")
    op.drop_index("ix_locator_repairs_failure_id", table_name="locator_repairs")
    op.drop_table("locator_repairs")
