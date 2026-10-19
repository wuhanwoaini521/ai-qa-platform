"""Backend parity: SQLite and PostgreSQL must behave identically.

Every test in this module runs on both backends (SQLite by default, PostgreSQL
when ``AI_QA_TEST_DATABASE_URL`` is set). Each one targets a place where the two
engines used to disagree:

* ``ON DELETE CASCADE`` is silently ignored by SQLite unless ``PRAGMA
  foreign_keys=ON`` is issued on every connection.
* ``DateTime(timezone=True)`` returns naive datetimes on SQLite and aware
  datetimes on PostgreSQL.
* ``ORDER BY`` on a nullable column puts ``NULL`` first on SQLite (both
  directions) and last for ``ASC`` / first for ``DESC`` on PostgreSQL.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from app.persistence.database import Base, build_engine
from app.persistence.migrations import upgrade_database
from app.persistence.models import (
    ProjectORM,
    RequirementORM,
    TestDesignORM,
    TestExecutionORM,
    TestRunORM,
    utc_now,
)
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.test_run_repo import TestRunRepository
from conftest import using_postgres
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def _seed_project_graph(session, project_id: str) -> None:
    session.add(
        ProjectORM(
            id=project_id,
            name=f"Parity {project_id}",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )


async def _insert_cascade_graph(session) -> None:
    await _seed_project_graph(session, "proj_cascade")
    session.add(RequirementORM(id="req_cascade", project_id="proj_cascade", title="Cascade requirement"))
    session.add(TestDesignORM(id="des_cascade", requirement_id="req_cascade", title="Cascade design"))
    session.add(
        TestRunORM(
            id="run_cascade",
            project_id="proj_cascade",
            workspace_id="ws_cascade",
            created_at=utc_now(),
        )
    )
    session.add(TestExecutionORM(id="exec_cascade", run_id="run_cascade", nodeid="tests/cascade.py::test_x"))


async def _assert_cascade_graph_deleted(session) -> None:
    assert (await session.execute(select(RequirementORM))).scalars().all() == []
    assert (await session.execute(select(TestDesignORM))).scalars().all() == []
    assert (await session.execute(select(TestRunORM))).scalars().all() == []
    assert (await session.execute(select(TestExecutionORM))).scalars().all() == []


async def test_datetimes_are_utc_aware_after_round_trip(test_db_session) -> None:
    project_id = "proj_parity_tz"
    async with test_db_session() as session:
        await _seed_project_graph(session, project_id)
        await session.commit()

    async with test_db_session() as session:
        loaded = (await session.execute(select(ProjectORM).where(ProjectORM.id == project_id))).scalar_one()
        assert loaded.created_at.tzinfo is not None
        assert loaded.created_at.utcoffset() == timedelta(0)
        assert loaded.updated_at.utcoffset() == timedelta(0)
        # Comparing a naive value against an aware one raises TypeError, which is
        # exactly the failure mode SQLite used to leak into the platform.
        assert loaded.created_at <= datetime.now(timezone.utc) + timedelta(seconds=5)


async def test_api_datetime_payloads_are_utc_aware(client: AsyncClient) -> None:
    created = await client.post("/api/projects", json={"name": "Parity API TZ", "bootstrap_workspace": False})
    assert created.status_code == 201

    # Read the project back so the payload is serialised from a database row.
    fetched = await client.get(f"/api/projects/{created.json()['id']}")
    assert fetched.status_code == 200

    for field in ("created_at", "updated_at"):
        parsed = datetime.fromisoformat(fetched.json()[field])
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)


async def test_on_delete_cascade_is_enforced_by_the_database(test_db_session) -> None:
    async with test_db_session() as session:
        await _insert_cascade_graph(session)
        await session.commit()

    async with test_db_session() as session:
        await session.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": "proj_cascade"})
        await session.commit()

    async with test_db_session() as session:
        await _assert_cascade_graph_deleted(session)


async def test_platform_sqlite_engine_enforces_foreign_keys(tmp_path) -> None:
    """The engine the platform builds for SQLite must enforce ON DELETE CASCADE.

    Skipped on a PostgreSQL test run: SQLAlchemy decides once per ``MetaData`` whether a circular
    foreign key must be added with ``ALTER TABLE``, and SQLite cannot do that, so a schema built
    with ``create_all`` *after* the same metadata was created for PostgreSQL silently loses those
    constraints. Production SQLite schemas come from the migrations, which
    :func:`test_migrated_sqlite_schema_enforces_project_cascade` covers on both backends.
    """
    if using_postgres():
        pytest.skip("SQLAlchemy cannot build the cyclic metadata for SQLite after a PostgreSQL run")

    engine = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}")
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            await _insert_cascade_graph(session)
            await session.commit()

        async with session_factory() as session:
            await session.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": "proj_cascade"})
            await session.commit()

        async with session_factory() as session:
            await _assert_cascade_graph_deleted(session)
    finally:
        await engine.dispose()


async def test_migrated_sqlite_schema_enforces_project_cascade(tmp_path) -> None:
    """A migrated SQLite database (what production runs) must cascade the same way."""
    engine = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'migrated.db'}")
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(upgrade_database)
            foreign_keys = (await conn.execute(text("PRAGMA foreign_key_list(test_runs)"))).all()

        assert ("projects", "project_id", "CASCADE") in {(fk[2], fk[3], fk[6]) for fk in foreign_keys}

        async with session_factory() as session:
            await _insert_cascade_graph(session)
            await session.commit()
        async with session_factory() as session:
            await session.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": "proj_cascade"})
            await session.commit()
        async with session_factory() as session:
            await _assert_cascade_graph_deleted(session)
    finally:
        await engine.dispose()


async def test_wal_keeps_a_long_reader_from_blocking_a_writer(tmp_path) -> None:
    """A long-lived SSE response holds a read transaction for the whole analysis or run.

    With the default rollback journal that read transaction blocked every writer until
    ``sqlite_timeout_seconds`` expired, so a healthy analysis failed with "database is
    locked". WAL lets the single writer proceed next to open readers.
    """
    if using_postgres():
        pytest.skip("SQLite-specific journal behaviour")

    db_file = tmp_path / "wal.db"
    engine = build_engine(f"sqlite+aiosqlite:///{db_file}")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY)"))
            journal_mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
        assert journal_mode == "wal"

        reader = sqlite3.connect(db_file)
        try:
            reader.execute("BEGIN")
            reader.execute("SELECT count(*) FROM probe")
            # A short busy timeout keeps the assertion fast: without WAL the insert waits
            # for the reader instead of failing immediately.
            writer = sqlite3.connect(db_file, timeout=0.5)
            try:
                writer.execute("INSERT INTO probe (id) VALUES (1)")
                writer.commit()
            finally:
                writer.close()
        finally:
            reader.close()
    finally:
        await engine.dispose()


async def test_execution_ordering_is_stable_with_null_started_at(test_db_session) -> None:
    started_early = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    started_late = started_early + timedelta(minutes=5)
    nodeid = "tests/order.py::test_ordering"

    async with test_db_session() as session:
        await _seed_project_graph(session, "proj_order")
        session.add(TestRunORM(id="run_order", project_id="proj_order", workspace_id="ws_order", created_at=utc_now()))
        session.add(TestExecutionORM(id="exec_null", run_id="run_order", nodeid=nodeid, started_at=None))
        session.add(TestExecutionORM(id="exec_early", run_id="run_order", nodeid=nodeid, started_at=started_early))
        session.add(TestExecutionORM(id="exec_late", run_id="run_order", nodeid=nodeid, started_at=started_late))
        await session.commit()

    async with test_db_session() as session:
        oldest_first = await TestRunRepository(session).list_executions("run_order")
        assert [execution.id for execution in oldest_first] == ["exec_null", "exec_early", "exec_late"]

    history_repo = RunHistoryRepository(test_db_session)
    newest_first = await history_repo.get_test_executions(nodeid, project_id="proj_order")
    assert [execution.id for execution in newest_first] == ["exec_late", "exec_early", "exec_null"]
