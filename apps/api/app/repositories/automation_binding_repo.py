from __future__ import annotations

import json
import uuid

from project_model.models import AutomationBindingCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import AutomationBindingORM, TestCaseORM, utc_now


class AutomationBindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_test_case_id(self, test_case_id: str) -> AutomationBindingORM | None:
        result = await self.session.execute(
            select(AutomationBindingORM).where(AutomationBindingORM.test_case_id == test_case_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, binding_id: str) -> AutomationBindingORM | None:
        result = await self.session.execute(select(AutomationBindingORM).where(AutomationBindingORM.id == binding_id))
        return result.scalar_one_or_none()

    async def get_active_by_nodeid(self, nodeid: str, project_id: str) -> AutomationBindingORM | None:
        result = await self.session.execute(
            select(AutomationBindingORM)
            .join(TestCaseORM, TestCaseORM.id == AutomationBindingORM.test_case_id)
            .where(
                AutomationBindingORM.nodeid == nodeid,
                AutomationBindingORM.status == "ACTIVE",
                TestCaseORM.project_id == project_id,
            )
            .limit(2)
        )
        rows = list(result.scalars())
        return rows[0] if len(rows) == 1 else None

    @staticmethod
    def _decision_history(bundle: dict | None) -> list[dict]:
        if not isinstance(bundle, dict):
            return []
        history = bundle.get("decision_history")
        if isinstance(history, list):
            return [item for item in history if isinstance(item, dict)]
        return [
            {"step_id": step.get("step_id"), **decision}
            for step in bundle.get("steps", [])
            if isinstance(step, dict)
            for decision in ((step.get("evidence") or {}).get("decision_history") or [])
            if isinstance(decision, dict)
        ]

    async def update_recorder_evidence_bundle(self, test_case_id: str, bundle: dict) -> None:
        binding = await self.get_by_test_case_id(test_case_id)
        if binding is None:
            raise ValueError("Automation binding not found")
        previous = binding.recorder_evidence_bundle or {}
        history = {}
        for decision in self._decision_history(previous) + self._decision_history(bundle):
            key = json.dumps(decision, sort_keys=True, ensure_ascii=False)
            history[key] = decision
        bundle["decision_history"] = list(history.values())
        bundle["revision"] = int(previous.get("revision", 0)) + 1
        bundle["revisions"] = list(previous.get("revisions", []))
        if previous:
            bundle["revisions"].append(
                {
                    "version": previous.get("version"),
                    "revision": previous.get("revision", 1),
                    "captured_at": previous.get("captured_at"),
                    "session_id": previous.get("session_id"),
                    "steps": previous.get("steps", []),
                    "decision_history": self._decision_history(previous),
                }
            )
        if len(json.dumps(bundle, ensure_ascii=False).encode("utf-8")) > 1_000_000:
            raise ValueError("Recorder evidence history exceeds 1 MB; previous bundle was preserved")
        binding.recorder_evidence_bundle = bundle
        binding.updated_at = utc_now()
        await self.session.flush()

    async def create_or_update(self, data: AutomationBindingCreate) -> AutomationBindingORM:
        existing = await self.get_by_test_case_id(data.test_case_id)
        now = utc_now()
        if existing:
            existing.workspace_id = data.workspace_id
            existing.nodeid = data.nodeid
            existing.file_path = data.file_path
            existing.framework = data.framework.value
            existing.status = data.status.value
            existing.updated_at = now
            await self.session.flush()
            return existing

        binding_id = f"bind_{uuid.uuid4().hex[:12]}"
        orm = AutomationBindingORM(
            id=binding_id,
            test_case_id=data.test_case_id,
            workspace_id=data.workspace_id,
            nodeid=data.nodeid,
            file_path=data.file_path,
            framework=data.framework.value,
            status=data.status.value,
            created_at=now,
            updated_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def list_all(self) -> list[AutomationBindingORM]:
        result = await self.session.execute(select(AutomationBindingORM))
        return list(result.scalars().all())

    async def list_by_project(self, project_id: str) -> list[AutomationBindingORM]:
        from app.persistence.models import TestCaseORM

        stmt = (
            select(AutomationBindingORM)
            .join(TestCaseORM, AutomationBindingORM.test_case_id == TestCaseORM.id)
            .where(TestCaseORM.project_id == project_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_for_cases(self, test_case_ids: list[str]) -> list[AutomationBindingORM]:
        if not test_case_ids:
            return []
        result = await self.session.execute(
            select(AutomationBindingORM).where(
                AutomationBindingORM.test_case_id.in_(test_case_ids),
                AutomationBindingORM.status == "ACTIVE",
            )
        )
        return list(result.scalars().all())

    async def list_active_by_requirement(self, project_id: str, requirement_id: str) -> list[AutomationBindingORM]:
        from app.persistence.models import TestCaseORM

        result = await self.session.execute(
            select(AutomationBindingORM)
            .join(TestCaseORM, TestCaseORM.id == AutomationBindingORM.test_case_id)
            .where(
                TestCaseORM.project_id == project_id,
                TestCaseORM.requirement_id == requirement_id,
                AutomationBindingORM.status == "ACTIVE",
            )
        )
        return list(result.scalars().all())

    async def delete_by_test_case_id(self, test_case_id: str) -> bool:
        existing = await self.get_by_test_case_id(test_case_id)
        if not existing:
            return False
        await self.session.delete(existing)
        await self.session.flush()
        return True
