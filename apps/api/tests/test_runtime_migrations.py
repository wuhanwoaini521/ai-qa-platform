from alembic.script import ScriptDirectory
from app.persistence.migrations import downgrade_database, migration_config, upgrade_database
from sqlalchemy import create_engine, inspect, text


def _head_revision() -> str:
    """The migration head moves whenever a revision lands: assert the chain, not a remembered id."""
    return ScriptDirectory.from_config(migration_config()).get_current_head()


def test_new_database_upgrade_and_non_destructive_baseline_rollback(tmp_path):
    from app.persistence.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'new.db'}")
    with engine.begin() as connection:
        upgrade_database(connection)
        tables = set(inspect(connection).get_table_names())
        # Derive the expected table set from the ORM instead of baking a number that every new
        # revision would have to update: the only table alembic adds is its own bookkeeping one.
        assert len(tables) == len(Base.metadata.tables) + 1
        assert {"discovery_evidence", "discovery_scenarios"} <= tables
        connection.execute(
            text(
                "INSERT INTO projects (id,name,description,framework_type,default_branch,created_at,updated_at) VALUES ('p','Retain','','playwright_python','main',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        downgrade_database(connection, "base")
        assert connection.scalar(text("SELECT name FROM projects WHERE id='p'")) == "Retain"
        upgrade_database(connection)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == _head_revision()
        assert {"decision_value", "locator_repair_id"} <= {
            column["name"] for column in inspect(connection).get_columns("ai_invocations")
        }
        assert "version" in {column["name"] for column in inspect(connection).get_columns("quality_discovery_runs")}
        assert {"failure_snapshot_json", "encrypted_storage_state", "storage_state_expires_at"} <= {
            column["name"] for column in inspect(connection).get_columns("browser_sessions")
        }
        assert "recorder_evidence_bundle" in {
            column["name"] for column in inspect(connection).get_columns("automation_bindings")
        }
        assert {"run_id", "execution_id", "failure_id", "status"} <= {
            column["name"] for column in inspect(connection).get_columns("debug_sessions")
        }
        # The two revisions after 0013 must also come back down on SQLite, not only up.
        assert {"source_file", "source_line"} <= {
            column["name"] for column in inspect(connection).get_columns("failure_records")
        }
        assert {"project_id", "created_by"} <= {
            column["name"] for column in inspect(connection).get_columns("stored_artifacts")
        }
        downgrade_database(connection, "0013_project_ownership")
        assert not {"source_file", "source_line"} & {
            column["name"] for column in inspect(connection).get_columns("failure_records")
        }
        assert not {"project_id", "created_by"} & {
            column["name"] for column in inspect(connection).get_columns("stored_artifacts")
        }
        upgrade_database(connection)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == _head_revision()
        assert {"source_file", "source_line"} <= {
            column["name"] for column in inspect(connection).get_columns("failure_records")
        }
        assert {"project_id", "created_by"} <= {
            column["name"] for column in inspect(connection).get_columns("stored_artifacts")
        }
        # Workflow task identity and its cross-version idempotency key are reversible on SQLite.
        workflow_task_columns = {
            "workflow_execution_id",
            "workflow_definition_id",
            "workflow_version_id",
            "workflow_version",
            "workflow_checksum",
            "workflow_idempotency_key",
            "workflow_request_fingerprint",
        }
        assert workflow_task_columns <= {column["name"] for column in inspect(connection).get_columns("agent_tasks")}
        workflow_idempotency = next(
            constraint
            for constraint in inspect(connection).get_unique_constraints("agent_tasks")
            if constraint["name"] == "uq_agent_tasks_workflow_idempotency"
        )
        assert workflow_idempotency["column_names"] == [
            "workflow_definition_id",
            "owner_id",
            "workflow_idempotency_key",
        ]
        downgrade_database(connection, "0022_task_cancel_request")
        assert not workflow_task_columns & {column["name"] for column in inspect(connection).get_columns("agent_tasks")}
        upgrade_database(connection)
        assert workflow_task_columns <= {column["name"] for column in inspect(connection).get_columns("agent_tasks")}
        # The evidence index must come back down on SQLite too, not only up.
        assert {"discovery_evidence", "discovery_scenarios"} <= set(inspect(connection).get_table_names())
        # Versioned workflow definitions: additive tables that must also go down on SQLite.
        workflow_tables = {"workflow_definitions", "workflow_definition_versions"}
        assert workflow_tables <= set(inspect(connection).get_table_names())
        assert {"definition_id", "version", "state", "checksum", "graph"} <= {
            column["name"] for column in inspect(connection).get_columns("workflow_definition_versions")
        }
        downgrade_database(connection, "0018_ai_invocation_step")
        assert not workflow_tables & set(inspect(connection).get_table_names())
        upgrade_database(connection)
        assert workflow_tables <= set(inspect(connection).get_table_names())
        # An invocation names its step; the column is additive and goes away again on downgrade.
        assert "step_id" in {column["name"] for column in inspect(connection).get_columns("ai_invocations")}
        downgrade_database(connection, "0015_artifact_ownership")
        assert not {"discovery_evidence", "discovery_scenarios"} & set(inspect(connection).get_table_names())
        assert "step_id" not in {column["name"] for column in inspect(connection).get_columns("ai_invocations")}
        upgrade_database(connection)
        assert {"discovery_evidence", "discovery_scenarios"} <= set(inspect(connection).get_table_names())
        assert "step_id" in {column["name"] for column in inspect(connection).get_columns("ai_invocations")}
    engine.dispose()


def test_relationship_backfill_rejects_ambiguous_links_and_fk_rollback_keeps_executions(tmp_path, caplog):
    from app.persistence.models import ProjectORM, TaskORM, TestExecutionORM, TestRunORM
    from sqlalchemy import event

    engine = create_engine(f"sqlite:///{tmp_path / 'relationships.db'}")

    @event.listens_for(engine, "connect")
    def enforce(dbapi, _):
        dbapi.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        upgrade_database(connection, "0002_runtime_timestamps")
        connection.execute(ProjectORM.__table__.insert().values(id="p", name="FK"))
        connection.execute(TestRunORM.__table__.insert().values(id="run", project_id="p", workspace_id="p"))
        for task_id in ["a", "b"]:
            connection.execute(
                TaskORM.__table__.insert().values(
                    id=task_id,
                    owner_id="owner",
                    project_id="p",
                    type="RUN_REGRESSION",
                    goal="Run",
                    context={"run_id": "run"},
                )
            )
        connection.execute(TestExecutionORM.__table__.insert().values(id="e", run_id="run", nodeid="test.py"))
        upgrade_database(connection)
        assert connection.scalar(text("SELECT task_id FROM test_runs")) is None
        assert "conflicted=1" in caplog.text
        assert len(inspect(connection).get_foreign_keys("test_runs")) >= 4
        downgrade_database(connection, "0002_runtime_timestamps")
        assert connection.scalar(text("SELECT COUNT(*) FROM test_executions")) == 1
        assert connection.scalar(text("SELECT COUNT(*) FROM test_runs")) == 1
        upgrade_database(connection)
    engine.dispose()


def test_existing_database_adoption_repairs_legacy_fields_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        upgrade_database(connection, "0001_baseline")
        connection.execute(text("DROP TABLE alembic_version"))
        connection.execute(text("ALTER TABLE projects DROP COLUMN demo_kind"))
        connection.execute(
            text(
                "INSERT INTO projects (id,name,description,framework_type,default_branch,created_at,updated_at) VALUES ('p','Legacy','','playwright_python','main',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        upgrade_database(connection)
        upgrade_database(connection)
        assert "demo_kind" in {column["name"] for column in inspect(connection).get_columns("projects")}
        assert connection.scalar(text("SELECT name FROM projects WHERE id='p'")) == "Legacy"
    engine.dispose()


def test_time_and_step_backfill_uses_real_records_and_preserves_children_on_downgrade(tmp_path):
    from datetime import timedelta

    from app.persistence.models import (
        ProjectORM,
        TaskEventORM,
        TaskORM,
        TaskStepORM,
        TestExecutionORM,
        TestRunORM,
        utc_now,
    )

    engine = create_engine(f"sqlite:///{tmp_path / 'timing.db'}")
    now = utc_now()
    with engine.begin() as connection:
        upgrade_database(connection, "0001_baseline")
        connection.execute(ProjectORM.__table__.insert().values(id="p", name="Timing"))
        connection.execute(
            TaskORM.__table__.insert().values(id="task", owner_id="owner", type="EXPLORE_PAGE", goal="Timing")
        )
        connection.execute(
            TaskStepORM.__table__.insert().values(
                id="s", task_id="task", key="inspect", name="Inspect", tool="browser.inspect"
            )
        )
        connection.execute(
            TaskEventORM.__table__.insert().values(task_id="task", type="step.started", payload={"step_id": "s"})
        )
        connection.execute(
            TaskEventORM.__table__.insert().values(task_id="task", type="ai.trace", payload={"step_id": "task:fake"})
        )
        connection.execute(TestRunORM.__table__.insert().values(id="run", project_id="p", workspace_id="p"))
        connection.execute(
            TestExecutionORM.__table__.insert().values(
                id="e", run_id="run", nodeid="test.py::test_a", started_at=now, finished_at=now, duration_ms=2000
            )
        )
        upgrade_database(connection)
        row = connection.execute(text("SELECT started_at,finished_at,timestamp_source FROM test_executions")).one()
        assert row.timestamp_source == "derived"
        from datetime import datetime

        assert datetime.fromisoformat(row.finished_at) - datetime.fromisoformat(row.started_at) == timedelta(seconds=2)
        assert connection.execute(text("SELECT step_id FROM agent_task_events ORDER BY id")).scalars().all() == [
            "s",
            None,
        ]
        downgrade_database(connection, "0001_baseline")
        assert connection.scalar(text("SELECT COUNT(*) FROM test_executions")) == 1
        assert connection.scalar(text("SELECT COUNT(*) FROM agent_task_events")) == 2
        upgrade_database(connection)
    engine.dispose()


def test_locator_repair_migration_backfills_legacy_state_and_downgrades_cleanly(tmp_path):
    import json

    from app.persistence.models import (
        AIInvocationORM,
        FailureAnalysisORM,
        FailureRecordORM,
        ProjectORM,
        TestExecutionORM,
        TestRunORM,
    )

    engine = create_engine(f"sqlite:///{tmp_path / 'locator-repair.db'}")
    legacy_result = {
        "repair_state": "BLOCKED",
        "block_reason": "AI_BUDGET_EXHAUSTED",
        "selection": {"candidate_id": "candidate-1"},
    }
    applied_proposal = {
        "candidate_id": "candidate-applied",
        "proposed_locator": 'get_by_test_id("new")',
        "applied": True,
    }
    with engine.begin() as connection:
        upgrade_database(connection, "0009_decision_signal_values")
        connection.execute(
            AIInvocationORM.__table__.insert().values(
                id="legacy-invocation",
                task="locator_choice",
                provider="jev",
                model="jev-test",
            )
        )
        connection.execute(ProjectORM.__table__.insert().values(id="p", name="Legacy"))
        connection.execute(TestRunORM.__table__.insert().values(id="run", project_id="p", workspace_id="p"))
        connection.execute(
            TestExecutionORM.__table__.insert().values(
                id="execution", run_id="run", nodeid="tests/test_locator.py::test_button"
            )
        )
        connection.execute(
            FailureRecordORM.__table__.insert().values(
                id="failure",
                run_id="run",
                execution_id="execution",
                test_nodeid="tests/test_locator.py::test_button",
                test_name="test_button",
                repair_proposal=applied_proposal,
            )
        )
        connection.execute(
            FailureAnalysisORM.__table__.insert().values(
                id="analysis",
                failure_id="failure",
                status="COMPLETED",
                result=legacy_result,
                events=[],
            )
        )
        connection.execute(
            FailureAnalysisORM.__table__.insert().values(
                id="analysis-applied",
                failure_id="failure",
                status="COMPLETED",
                result={"repair_state": "PATCH_READY", "repair_proposal": applied_proposal},
                events=[],
            )
        )
        connection.execute(
            FailureAnalysisORM.__table__.insert().values(
                id="analysis-from-event",
                failure_id="failure",
                status="RUNNING",
                result={},
                events=[
                    {
                        "type": "repair.started",
                        "stage": "repair",
                        "metadata": {"state": "DECIDING"},
                    }
                ],
            )
        )
        connection.execute(
            FailureAnalysisORM.__table__.insert().values(
                id="analysis-without-repair",
                failure_id="failure",
                status="COMPLETED",
                result={},
                events=[{"type": "workflow.plan", "stage": "workflow", "metadata": {}}],
            )
        )

        upgrade_database(connection)
        repair = connection.execute(
            text(
                "SELECT failure_id, analysis_id, state, block_reason, candidate_id "
                "FROM locator_repairs WHERE analysis_id='analysis'"
            )
        ).one()
        assert repair == (
            "failure",
            "analysis",
            "BLOCKED",
            "AI_BUDGET_EXHAUSTED",
            "candidate-1",
        )
        assert "locator_repair_id" in {column["name"] for column in inspect(connection).get_columns("ai_invocations")}
        assert (
            connection.scalar(text("SELECT state FROM locator_repairs WHERE analysis_id='analysis-from-event'"))
            == "DECIDING"
        )
        assert connection.scalar(text("SELECT COUNT(*) FROM locator_repairs")) == 3
        assert (
            connection.scalar(text("SELECT state FROM locator_repairs WHERE analysis_id='analysis-applied'"))
            == "PATCH_APPLIED"
        )
        assert (
            connection.scalar(text("SELECT locator_repair_id FROM ai_invocations WHERE id='legacy-invocation'")) is None
        )

        downgrade_database(connection, "0009_decision_signal_values")
        assert "locator_repairs" not in inspect(connection).get_table_names()
        assert "locator_repair_id" not in {
            column["name"] for column in inspect(connection).get_columns("ai_invocations")
        }
        assert (
            json.loads(connection.scalar(text("SELECT result FROM failure_analyses WHERE id='analysis'")))
            == legacy_result
        )
        assert connection.scalar(text("SELECT COUNT(*) FROM ai_invocations WHERE id='legacy-invocation'")) == 1

        upgrade_database(connection)
        assert connection.scalar(text("SELECT COUNT(*) FROM locator_repairs")) == 3
        assert connection.scalar(text("SELECT COUNT(*) FROM locator_repairs WHERE analysis_id='analysis'")) == 1
    engine.dispose()


def test_project_ownership_migration_survives_a_previously_unaltered_column(tmp_path):
    """A database altered outside alembic must still start.

    Real incident: runtime/ai_qa_platform.db already had projects.owner_id (added by hand) while
    alembic_version still said 0012, so `ALTER TABLE projects ADD COLUMN owner_id` failed with
    "duplicate column name" and the whole API refused to boot.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'drift.db'}")
    with engine.begin() as connection:
        upgrade_database(connection, "0012_debug_session_lineage")
        connection.execute(
            text("ALTER TABLE projects ADD COLUMN owner_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL")
        )
        upgrade_database(connection)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == _head_revision()
        columns = {column["name"] for column in inspect(connection).get_columns("projects")}
        indexes = {index["name"] for index in inspect(connection).get_indexes("projects")}
        assert {"owner_id", "team_id"} <= columns
        assert {"ix_projects_owner_id", "ix_projects_team_id"} <= indexes
        # Re-running the head revision must stay a no-op rather than raising again.
        upgrade_database(connection)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == _head_revision()
    engine.dispose()
