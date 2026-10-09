from __future__ import annotations

import json

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import BrowserSessionORM, utc_now


class BrowserSessionRepository:
    """Persistence operations for run-owned browser sessions and captured evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, session_id: str) -> BrowserSessionORM | None:
        return await self.session.get(BrowserSessionORM, session_id)

    async def list_by_run(self, run_id: str) -> list[BrowserSessionORM]:
        result = await self.session.execute(select(BrowserSessionORM).where(BrowserSessionORM.run_id == run_id))
        return list(result.scalars().all())

    async def attach_execution(self, run_id: str, nodeid: str, execution_id: str) -> None:
        await self.session.execute(
            update(BrowserSessionORM)
            .where(
                BrowserSessionORM.run_id == run_id,
                BrowserSessionORM.nodeid == nodeid,
                BrowserSessionORM.case_execution_id.is_(None),
            )
            .values(case_execution_id=execution_id)
        )

    async def attach_last_frame_artifact(
        self, session_id: str, run_id: str, artifact_id: str
    ) -> BrowserSessionORM | None:
        row = await self.get_by_id(session_id)
        if row is None or row.run_id != run_id:
            return None
        evidence = json.loads(row.page_evidence_json or "{}")
        evidence["last_frame_artifact_id"] = artifact_id
        row.page_evidence_json = json.dumps(evidence, ensure_ascii=False)
        await self.session.flush()
        return row

    async def record_lifecycle_event(
        self,
        *,
        run_id: str,
        session_id: str,
        event_type: str,
        page_id: str,
        worker_id: str,
        nodeid: str,
        case_name: str,
        url: str,
        status: str,
        occurred_at,
        page_evidence: dict | None,
    ) -> BrowserSessionORM | None:
        row = await self.get_by_id(session_id)
        if row is None and event_type == "session.started":
            row = BrowserSessionORM(
                id=session_id,
                run_id=run_id,
                browser_session_id=session_id,
                page_id=page_id,
                worker_id=worker_id,
                nodeid=nodeid,
                case_name=case_name,
                current_url=url,
                status=status,
                started_at=occurred_at or utc_now(),
            )
            self.session.add(row)
        elif row is not None:
            row.current_url = url
            row.status = status
            if event_type == "session.finished":
                row.finished_at = occurred_at or utc_now()
                if page_evidence is not None:
                    row.page_evidence_json = json.dumps(page_evidence, ensure_ascii=False)
        if row is not None:
            await self.session.flush()
        return row

    async def append_evidence(self, session_id: str, key: str, entry: dict) -> None:
        row = await self.get_by_id(session_id)
        if row is None:
            return
        evidence = json.loads(row.page_evidence_json or "{}")
        evidence[key] = [*(evidence.get(key) or []), entry][-100:]
        row.page_evidence_json = json.dumps(evidence, ensure_ascii=False)
        await self.session.flush()

    async def close_running_sessions(self, run_id: str, executions_by_nodeid: dict, finished_at) -> None:
        for row in await self.list_by_run(run_id):
            execution = executions_by_nodeid.get(row.nodeid)
            if execution and row.case_execution_id is None:
                row.case_execution_id = execution.id
            if row.status == "running":
                row.status = execution.status.lower() if execution else "closed"
                row.finished_at = finished_at
        await self.session.flush()
