from app.persistence.migrations import downgrade_database, upgrade_database
from sqlalchemy import create_engine, inspect, text


def test_new_database_upgrade_and_non_destructive_baseline_rollback(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'new.db'}")
    with engine.begin() as connection:
        upgrade_database(connection)
        assert len(inspect(connection).get_table_names()) == 36
        connection.execute(
            text(
                "INSERT INTO projects (id,name,description,framework_type,default_branch,created_at,updated_at) VALUES ('p','Retain','','playwright_python','main',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        downgrade_database(connection, "base")
        assert connection.scalar(text("SELECT name FROM projects WHERE id='p'")) == "Retain"
        upgrade_database(connection)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003_task_run_relationship"
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
