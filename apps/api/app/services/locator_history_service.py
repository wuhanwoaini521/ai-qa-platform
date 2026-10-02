from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

from qa_core.failure.redactor import SensitiveRedactor
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.persistence import database
from app.persistence.models import FailureAnalysisORM, LocatorHistoryORM, utc_now


class LocatorHistoryService:
    @staticmethod
    def identity(url: str, locator: str):
        parts = urlsplit(SensitiveRedactor.redact_url(url))
        page = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[:2048]
        locator = SensitiveRedactor.redact_text(locator)[:1000]
        # Playwright runtime telemetry uses selectors; proposals use public Python APIs.
        # Normalize only known formats, so equivalent observations share one history key.
        role = re.fullmatch(r'internal:role=(\w+)\[name=("(?:[^"\\]|\\.)*")[si]\]', locator)
        if role:
            locator = f"get_by_role({json.dumps(role[1])}, name={json.dumps(json.loads(role[2]), ensure_ascii=False)})"
        for strategy, method in (
            ("label", "get_by_label"),
            ("placeholder", "get_by_placeholder"),
            ("text", "get_by_text"),
        ):
            match = re.fullmatch(rf'internal:{strategy}=("(?:[^"\\]|\\.)*")[si]', locator)
            if match:
                locator = f"{method}({json.dumps(json.loads(match[1]), ensure_ascii=False)})"
        test_id = re.fullmatch(r'internal:testid=\[data-testid=("(?:[^"\\]|\\.)*")[si]\]', locator)
        if test_id:
            locator = f"get_by_test_id({json.dumps(json.loads(test_id[1]), ensure_ascii=False)})"
        key = hashlib.sha256(f"{page}\n{locator}".encode()).hexdigest()
        return key, page, locator

    async def enrich(self, url: str, candidates: list[dict]):
        keys = {self.identity(url, item["locator"])[0]: item for item in candidates}
        if not keys:
            return
        async with database.get_session() as session:
            rows = (
                (await session.execute(select(LocatorHistoryORM).where(LocatorHistoryORM.id.in_(keys)))).scalars().all()
            )
            for row in rows:
                keys[row.id]["evidence"]["history"] = {
                    "success_count": row.success_count,
                    "failure_count": row.failure_count,
                    "verification_count": row.verification_count,
                    "heal_count": row.heal_count,
                    "stability_score": round((row.success_count + 1) / (row.success_count + row.failure_count + 2), 3),
                }

    async def record(
        self,
        url: str,
        locator: str,
        passed: bool,
        *,
        verification=False,
        healed=False,
        healed_analysis_id: str | None = None,
    ):
        key, page, safe_locator = self.identity(url, locator)
        now = utc_now()
        values = {
            "id": key,
            "page_url": page,
            "locator": safe_locator,
            "success_count": int(passed and not verification),
            "failure_count": int(not passed and not verification),
            "verification_count": int(verification),
            "heal_count": int(healed),
            "last_success_at": now if passed and not verification else None,
            "last_failure_at": now if not passed and not verification else None,
        }
        async with database.get_session() as session:
            if healed_analysis_id:
                analysis = await session.get(FailureAnalysisORM, healed_analysis_id)
                if (
                    analysis is None
                    or not analysis.result.get("verified")
                    or analysis.result.get("locator_heal_recorded")
                ):
                    return
                claimed = await session.execute(
                    update(FailureAnalysisORM)
                    .where(
                        FailureAnalysisORM.id == healed_analysis_id,
                        FailureAnalysisORM.result == analysis.result,
                    )
                    .values(result={**analysis.result, "locator_heal_recorded": True})
                )
                if not claimed.rowcount:
                    return
            insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
            statement = insert(LocatorHistoryORM).values(**values)
            updates = {
                field: getattr(LocatorHistoryORM, field) + values[field]
                for field in ("success_count", "failure_count", "verification_count", "heal_count")
            }
            updates["updated_at"] = now
            if values["last_success_at"]:
                updates["last_success_at"] = now
            if values["last_failure_at"]:
                updates["last_failure_at"] = now
            await session.execute(statement.on_conflict_do_update(index_elements=["id"], set_=updates))
            await session.commit()
