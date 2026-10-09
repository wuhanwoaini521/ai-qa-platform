from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

from qa_core.failure.redactor import SensitiveRedactor

from app.persistence.models import utc_now
from app.ports.repository_scope import RepositoryScopeFactory


class LocatorHistoryService:
    def __init__(self, repository_scope: RepositoryScopeFactory | None = None) -> None:
        self.repository_scope = repository_scope

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
        if self.repository_scope is None:
            return
        async with self.repository_scope() as repositories:
            rows = await repositories.locator_history.list_by_ids(list(keys))
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
        if self.repository_scope is None:
            return
        async with self.repository_scope() as repositories:
            repository = repositories.locator_history
            if healed_analysis_id:
                if not await repository.claim_verified_heal(healed_analysis_id):
                    return
            await repository.record_outcome(values)
            await repositories.commit()
