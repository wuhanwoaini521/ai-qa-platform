from __future__ import annotations

from app.persistence.database import async_session_factory
from app.persistence.models import DebugSessionORM, FailureRecordORM, TestExecutionORM, TestRunORM, utc_now


class DebugSessionRepository:
    async def failure_lineage(self, *, failure_id: str, workspace_id: str, nodeid: str) -> dict[str, str] | None:
        async with async_session_factory() as session:
            failure = await session.get(FailureRecordORM, failure_id)
            run = await session.get(TestRunORM, failure.run_id) if failure else None
            execution = await session.get(TestExecutionORM, failure.execution_id) if failure else None
            if (
                failure is None
                or run is None
                or execution is None
                or execution.run_id != failure.run_id
                or run.workspace_id != workspace_id
                or failure.test_nodeid != nodeid
                or execution.nodeid != nodeid
            ):
                return None
            return {"run_id": failure.run_id, "execution_id": failure.execution_id, "failure_id": failure.id}

    async def create(
        self,
        *,
        session_id: str,
        owner_id: str,
        workspace_id: str,
        nodeid: str,
        run_id: str | None,
        execution_id: str | None,
        failure_id: str | None,
    ) -> None:
        async with async_session_factory() as session:
            session.add(
                DebugSessionORM(
                    id=session_id,
                    owner_id=owner_id,
                    workspace_id=workspace_id,
                    nodeid=nodeid,
                    run_id=run_id,
                    execution_id=execution_id,
                    failure_id=failure_id,
                    status="STARTING",
                )
            )
            await session.commit()

    async def activate(self, session_id: str) -> None:
        async with async_session_factory() as session:
            record = await session.get(DebugSessionORM, session_id)
            if record is None or record.status != "STARTING":
                return
            record.status = "ACTIVE"
            await session.commit()

    async def close(self, session_id: str) -> None:
        async with async_session_factory() as session:
            record = await session.get(DebugSessionORM, session_id)
            if record is None or record.status == "CLOSED":
                return
            record.status = "CLOSED"
            record.closed_at = utc_now()
            await session.commit()

    async def get(self, session_id: str, owner_id: str) -> dict[str, str | None] | None:
        async with async_session_factory() as session:
            record = await session.get(DebugSessionORM, session_id)
            if record is None or record.owner_id != owner_id:
                return None
            return {
                "id": record.id,
                "workspace_id": record.workspace_id,
                "nodeid": record.nodeid,
                "status": record.status,
                "run_id": record.run_id,
                "execution_id": record.execution_id,
                "failure_id": record.failure_id,
            }
