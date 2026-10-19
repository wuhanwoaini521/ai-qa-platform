"""Shared API test harness.

The suite runs on SQLite by default (fast, file-per-test). Setting
``AI_QA_TEST_DATABASE_URL`` to a PostgreSQL URL runs the **same** tests against
PostgreSQL, which is the production backend. Any behavioural difference between
the two backends is a platform bug, not a test-environment quirk.

No test may touch the developer database configured in ``settings.database_url``
(``./runtime/ai_qa_platform.db``): every database reference is redirected to the
per-test engine by :func:`redirect_database`.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest
import pytest_asyncio
from app.main import app as fastapi_app
from app.persistence import database as db_module
from app.persistence import models as models_module  # noqa: F401
from app.persistence.database import Base, get_db
from app.settings import settings
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

POSTGRES_TEST_URL = os.environ.get("AI_QA_TEST_DATABASE_URL", "").strip()

# Module-level database references that code binds with ``from ... import``.
_REDIRECTED_NAMES = ("engine", "async_session_factory", "get_session")
_APP_MODULE_PREFIXES = ("app", "worker")


def using_postgres() -> bool:
    return POSTGRES_TEST_URL.startswith("postgresql")


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """PostgreSQL-only expectations must not silently pass on SQLite."""
    if using_postgres():
        return
    skip = pytest.mark.skip(reason="requires AI_QA_TEST_DATABASE_URL pointing at PostgreSQL")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip)


def configure_sqlite_connection(engine) -> None:
    """Apply the pragmas the application relies on so tests match production."""
    db_module.configure_sqlite_connection(engine)


def create_test_engine(tmp_path: Path):
    if using_postgres():
        return create_async_engine(POSTGRES_TEST_URL, echo=False)
    db_file = tmp_path / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    configure_sqlite_connection(engine)
    return engine


def _app_modules() -> list[Any]:
    """Every loaded module of the application packages."""
    modules = []
    for module in list(sys.modules.values()):
        name = getattr(module, "__name__", "")
        if name.split(".")[0] in _APP_MODULE_PREFIXES:
            modules.append(module)
    return modules


def redirect_database(engine, session_factory) -> dict[str, Any]:
    """Point every module-level database reference at the test database.

    Repositories and routers bind ``engine`` / ``async_session_factory`` /
    ``get_session`` with ``from ... import`` at import time, so patching the
    ``database`` module alone would leave most of the app on the real engine.

    Returns the state needed by :func:`restore_database`.
    """
    replacements = {"engine": engine, "async_session_factory": session_factory, "get_session": session_factory}
    originals = {name: getattr(db_module, name) for name in _REDIRECTED_NAMES}
    for module in _app_modules():
        for name, replacement in replacements.items():
            if module.__dict__.get(name) is originals[name]:
                setattr(module, name, replacement)
    return {"originals": originals, "replacements": replacements}


def restore_database(state: dict[str, Any]) -> None:
    """Undo :func:`redirect_database`, including modules imported meanwhile."""
    originals = state["originals"]
    redirected_ids = {id(value) for value in state["replacements"].values()}
    for module in _app_modules():
        for name, original in originals.items():
            if id(module.__dict__.get(name)) in redirected_ids:
                setattr(module, name, original)


async def reset_test_schema(connection) -> None:
    """Create an empty schema for the next test.

    PostgreSQL cannot ``DROP TABLE`` the ``test_runs``/``failure_records`` pair because their
    foreign keys reference each other, so the schema is replaced instead of sorting tables.
    """
    if using_postgres():
        database = make_url(POSTGRES_TEST_URL).database or ""
        if "test" not in database.lower():
            raise RuntimeError(
                f"Refusing to drop the schema of non-test database {database!r}; "
                "AI_QA_TEST_DATABASE_URL must point at a throwaway test database."
            )
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
        return
    await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
def local_html_url():
    """Serve HTML on a loopback port for a single test; returns a serve() factory."""
    servers = []

    def serve(html: str) -> str:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}/"

    yield serve
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest_asyncio.fixture
async def test_db_session(tmp_path: Path):
    engine = create_test_engine(tmp_path)

    async with engine.begin() as conn:
        await reset_test_schema(conn)
        await conn.run_sync(Base.metadata.create_all)
        # The schema is created from the models, which the migration-drift test keeps equal to
        # Alembic head; stamping keeps the readiness probe (schema-current check) meaningful.
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from app.persistence.migrations import migration_config

        script_directory = ScriptDirectory.from_config(migration_config())
        await conn.run_sync(
            lambda sync_connection: MigrationContext.configure(sync_connection).stamp(
                script_directory, script_directory.get_current_head()
            )
        )

    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    redirect_state = redirect_database(engine, async_session)

    async def override_get_db():
        async with async_session() as session:
            yield session
            await session.commit()

    fastapi_app.dependency_overrides[get_db] = override_get_db

    yield async_session

    fastapi_app.dependency_overrides.clear()
    restore_database(redirect_state)
    await engine.dispose()


#: Credentials seeded by ``AuthService.ensure_default_users`` on first login.
ROLE_CREDENTIALS: dict[str, tuple[str, str]] = {
    "ADMIN": ("admin@ai-qa.local", "adminpassword"),
    "QA_LEAD": ("lead@ai-qa.local", "password123"),
    "QA_ENGINEER": ("engineer@ai-qa.local", "password123"),
}


async def login_token(ac: AsyncClient, email: str, password: str) -> str:
    """Authenticate against the real login endpoint and return the bearer token."""
    response = await ac.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def bearer_client(token: str | None) -> AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test", headers=headers)


@pytest_asyncio.fixture
async def client(test_db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Keep workspace data isolated and restore the process-wide setting after each test.
    test_ws_dir = tmp_path / "workspaces"
    test_ws_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "workspace_storage_dir", test_ws_dir)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Route authorization is enforced for real: authenticate as the seeded administrator so
        # every test exercises the same guarded path production uses.
        email, password = ROLE_CREDENTIALS["ADMIN"]
        ac.headers["Authorization"] = f"Bearer {await login_token(ac, email, password)}"
        yield ac


@pytest_asyncio.fixture
async def role_client(client):
    """Async context manager yielding a client authenticated as a seeded role.

    ``async with role_client("QA_LEAD") as lead: ...`` — used by the authorization tests to prove
    denial paths instead of only the happy path.
    """

    @asynccontextmanager
    async def _open(role: str):
        email, password = ROLE_CREDENTIALS[role]
        token = await login_token(client, email, password)
        async with bearer_client(token) as ac:
            yield ac

    return _open


@pytest_asyncio.fixture
async def credentials_client(client):
    """Async context manager yielding a client authenticated with explicit credentials.

    For roles that are not seeded (VIEWER, or an operator-created account).
    """

    @asynccontextmanager
    async def _open(email: str, password: str):
        token = await login_token(client, email, password)
        async with bearer_client(token) as ac:
            yield ac

    return _open


@pytest_asyncio.fixture
async def anonymous_client(test_db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A client that never sends credentials."""
    test_ws_dir = tmp_path / "workspaces"
    test_ws_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "workspace_storage_dir", test_ws_dir)

    async with bearer_client(None) as ac:
        yield ac
