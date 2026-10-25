from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from project_model.models import DecisionOption, DecisionRequest
from qa_core.ai.trace import AITraceEvent, make_trace_event
from qa_core.failure.redactor import SensitiveRedactor
from qa_core.healing.locator_intelligence import rank_locator_candidates

from app.ports.browser_runtime import BrowserRuntime
from app.ports.repository_scope import RepositoryScopeFactory
from app.services.decision_service import DecisionService
from app.services.decision_settings_service import DecisionSettingsService
from app.settings import get_config

_METHODS = {
    "role": "get_by_role",
    "label": "get_by_label",
    "test_id": "get_by_test_id",
    "placeholder": "get_by_placeholder",
    "text": "get_by_text",
}
_LOCATOR_NOISE = {
    "button",
    "element",
    "locator",
    "get",
    "by",
    "role",
    "name",
    "test",
    "data",
    "id",
    "css",
    "xpath",
    "old",
}
_GENERIC_TARGET_TOKENS = {
    "add",
    "button",
    "cancel",
    "cart",
    "checkout",
    "click",
    "close",
    "continue",
    "create",
    "delete",
    "login",
    "logout",
    "open",
    "order",
    "purchase",
    "remove",
    "save",
    "send",
    "submit",
    "update",
}


def _locator_tokens(value: str) -> set[str]:
    return {
        token.lower() for token in re.findall(r"[\w]+", value) if len(token) > 2 and token.lower() not in _LOCATOR_NOISE
    }


class LocatorDecisionService:
    """Shared candidate scoring, Jev/local choice, and Playwright verification."""

    def __init__(
        self,
        decision_service: DecisionService | None = None,
        settings_service: DecisionSettingsService | None = None,
        browser_runtime: BrowserRuntime | None = None,
        repository_scope: RepositoryScopeFactory | None = None,
    ) -> None:
        self.settings_service = settings_service or DecisionSettingsService(repository_scope)
        self.repository_scope = repository_scope
        self.decision_service = decision_service or DecisionService(
            settings_service=self.settings_service, repository_scope=repository_scope
        )
        if browser_runtime is None:
            from app.container import get_browser_runtime

            browser_runtime = get_browser_runtime()
        self.browser_runtime = browser_runtime

    @staticmethod
    def generate_candidates(event: dict[str, Any]) -> list[dict[str, Any]]:
        """Enrich only locators observed for the target; never synthesize a selector."""
        raw = rank_locator_candidates(event.get("candidates") or [])[:8]
        result: list[dict[str, Any]] = []
        for index, item in enumerate(raw, start=1):
            kind = item["kind"]
            value = str(item["value"])
            evidence = dict(item.get("evidence") or {})
            evidence.setdefault("uniqueness", None)
            evidence.setdefault("dom_depth", event.get("dom_depth"))
            evidence.setdefault("dynamic_attribute_risk", bool(re.search(r"(?:\d{5,}|[0-9a-f]{8,})", value, re.I)))
            evidence.setdefault(
                "text_stability",
                not bool(re.search(r"\d{5,}|\b\d{4}-\d{2}-\d{2}\b", value)) if kind == "text" else None,
            )
            item.update(
                candidate_id=f"candidate_{index}",
                strategy=kind,
                locator=LocatorDecisionService.format_locator(item),
                evidence=evidence,
                static_score=float(item.pop("confidence", item.get("static_score", 0.0))),
            )
            result.append(item)
        return result

    @staticmethod
    def prioritize_candidates_for_failure(
        failing_locator: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Boost candidates related to the old locator without excluding semantic replacements."""
        target_tokens = _locator_tokens(failing_locator)
        scored: list[tuple[int, float, int, dict[str, Any]]] = []
        for index, candidate in enumerate(candidates):
            description = " ".join(
                str(candidate.get(key) or "") for key in ("kind", "value", "name", "locator", "strategy")
            )
            candidate_tokens = _locator_tokens(description)
            overlap = len(target_tokens & candidate_tokens)
            static_score = candidate.get("static_score", 0.0)
            scored.append((overlap, static_score if isinstance(static_score, (int, float)) else 0.0, -index, candidate))

        return [item for _, _, _, item in sorted(scored, reverse=True)]

    @staticmethod
    def semantically_matches_failed_locator(failing_locator: str, proposed_locator: str) -> bool:
        """Require stronger target evidence before a local fallback can authorize a patch."""
        shared = _locator_tokens(failing_locator) & _locator_tokens(proposed_locator)
        if len(shared) >= 2:
            return True
        return any(len(token) >= 7 and token not in _GENERIC_TARGET_TOKENS for token in shared)

    @staticmethod
    def format_locator(candidate: dict[str, Any]) -> str:
        kind = str(candidate.get("kind", "css"))
        value = json.dumps(str(candidate.get("value", "")), ensure_ascii=False)
        if kind == "role":
            name = json.dumps(str(candidate.get("name", "")), ensure_ascii=False)
            exact = ", exact=True" if candidate.get("exact") is True else ""
            return f"get_by_role({value}, name={name}{exact})"
        method = _METHODS.get(kind)
        if method:
            return f"{method}({value})"
        if kind == "id":
            return f"locator('[id={value}]')"
        if kind == "name":
            return f"locator('[name={value}]')"
        return f"locator({json.dumps(('xpath=' if kind == 'xpath' and not str(candidate.get('value', '')).startswith('xpath=') else '') + str(candidate.get('value', '')), ensure_ascii=False)})"

    async def decide(
        self,
        *,
        run_id: str,
        event: dict[str, Any],
        candidates: list[dict[str, Any]],
        page: Any | None = None,
        browser_session_id: str | None = None,
        case_execution_id: str | None = None,
        step_id: str | None = None,
        on_event: Callable[[AITraceEvent], Awaitable[None]] | None = None,
        require_jev: bool = False,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        candidates = candidates[: get_config().agent.browser.max_candidates]
        decision_id = uuid4().hex
        trace: list[AITraceEvent] = []
        safe_url = SensitiveRedactor.redact_url(str(event.get("url") or ""))
        from app.services.locator_history_service import LocatorHistoryService

        history = LocatorHistoryService(self.repository_scope)

        async def emit(
            event_type: str,
            title: str,
            *,
            stage: str,
            message: str = "",
            metadata: dict[str, Any] | None = None,
            duration: float | None = None,
        ) -> None:
            status = "RUNNING" if event_type.endswith("_started") else "COMPLETED"
            if event_type == "repair_suggested" and not (metadata or {}).get("verified"):
                status = "UNVERIFIED"
            elif event_type == "failed" or (
                event_type == "verification_completed" and not (metadata or {}).get("verified")
            ):
                status = "FAILED"
            item = make_trace_event(
                run_id,
                event_type,
                stage=stage,
                title=title,
                message=message,
                metadata=metadata,
                case_execution_id=case_execution_id,
                step_id=step_id,
                status=status,
                duration_ms=duration,
            )
            trace.append(item)
            if on_event is not None:
                await on_event(item)

        await emit(
            "analysis_started",
            "Locator analysis started",
            stage="analysis",
            metadata={"action": str(event.get("action", ""))},
        )
        await emit("locator_history_started", "Checking locator history", stage="history")
        await history.enrich(safe_url, candidates)
        await emit("locator_history_completed", "Locator history checked", stage="history")
        ranked = rank_locator_candidates(candidates)
        scores = {item["candidate_id"]: item["confidence"] for item in ranked}
        for item in candidates:
            item["static_score"] = scores[item["candidate_id"]]
        candidates.sort(key=lambda item: item["static_score"], reverse=True)
        await emit(
            "evidence_collected",
            "Target element evidence collected",
            stage="evidence",
            message=f"{str(event.get('tag') or 'element')[:40]} · {str(event.get('role') or 'no role')[:40]}",
            metadata={"url": safe_url[:500], "candidate_count": len(candidates)},
        )
        await emit(
            "candidates_generated",
            "Locator candidates generated",
            stage="candidate_generation",
            message=f"{len(candidates)} candidate(s)",
            metadata={
                "candidate_count": len(candidates),
                "candidate_ids": [item["candidate_id"] for item in candidates],
            },
        )

        decision: Any = None
        latency_ms = 0.0
        fallback_reason = "no_candidates"
        if candidates:
            options = [
                DecisionOption(key=item["candidate_id"], description=item["locator"][:1000]) for item in candidates
            ]
            request = DecisionRequest(
                name="locator_candidate_selection",
                state={
                    "target": SensitiveRedactor.redact_value(event.get("target"))
                    or {
                        "tag": str(event.get("tag") or "")[:40],
                        "role": str(event.get("role") or "")[:80],
                        "accessible_name": str(event.get("name") or "")[:180],
                        "action": str(event.get("action") or "click")[:30],
                    },
                    "context": SensitiveRedactor.redact_value(
                        {
                            "url": safe_url[:500],
                            "frame_path": event.get("frame_path") or [],
                            **(event.get("context") or {}),
                        }
                    ),
                    "candidates": [
                        {
                            "candidate_id": item["candidate_id"],
                            "strategy": item["strategy"],
                            "locator": item["locator"],
                            "evidence": item["evidence"],
                            "static_score": item["static_score"],
                        }
                        for item in candidates
                    ],
                },
                instructions="Choose only a candidate_id from the supplied candidates. Do not write or alter a locator.",
                options=options,
            )
            await emit(
                "decision_started",
                "Locator decision started",
                stage="decision",
                metadata={"candidate_count": len(candidates)},
            )
            decision_started = time.perf_counter()
            try:
                # DecisionService owns the configured provider timeout. A second short
                # timeout here cancelled healthy Jev requests before that policy elapsed.
                decision = await self.decision_service.choose(request, run_id=run_id)
                latency_ms = round((time.perf_counter() - decision_started) * 1000, 1)
                fallback_reason = decision.reason or "provider_unavailable"
            except asyncio.TimeoutError:
                fallback_reason = "timeout"
            except Exception as error:
                fallback_reason = type(error).__name__

        candidate_by_id = {item["candidate_id"]: item for item in candidates}
        actual_jev = bool(
            decision
            and decision.provider == "jev"
            and not decision.fallback_used
            and decision.choice
            and decision.confidence is not None
            and str(decision.choice) in candidate_by_id
        )
        if decision and decision.provider == "jev" and not decision.fallback_used and decision.choice:
            if str(decision.choice) not in candidate_by_id:
                fallback_reason = "choice_not_in_candidates"
        elif decision and not decision.fallback_used and decision.provider != "jev":
            fallback_reason = "unexpected_provider"
        elif decision and decision.fallback_used:
            fallback_reason = decision.reason or "decision_fallback"
        selected_id = str(decision.choice) if actual_jev else None
        selected = candidate_by_id.get(selected_id) if selected_id else None
        engine = "Jev" if selected is not None and actual_jev else "BLOCKED" if require_jev else "Local Strategy"
        attempted_provider = (decision.attempted_provider or decision.provider) if decision else None
        attempted_model = (decision.attempted_model or decision.model) if decision else None
        attempted_choice = decision.attempted_choice if decision else None
        minimum_confidence = decision.minimum_confidence if decision else None
        if selected is None and candidates and not require_jev:
            selected = candidates[0]
            selected_id = selected["candidate_id"]

        await emit(
            "decision_completed",
            "Jev selected candidate"
            if engine == "Jev"
            else "Repair decision blocked"
            if require_jev
            else "Local Strategy selected candidate",
            stage="decision",
            message=(selected["locator"] if selected else "No usable candidate")
            + (f" · {latency_ms:.1f} ms" if engine == "Jev" else ""),
            metadata={
                "provider": "jev" if engine == "Jev" else "blocked" if require_jev else "local-strategy",
                "model": decision.model if engine == "Jev" else None,
                "candidate_id": selected_id,
                "selected_locator": selected.get("locator") if selected else None,
                "candidate_count": len(candidates),
                "confidence": decision.confidence if decision else None,
                "attempted_provider": attempted_provider,
                "attempted_model": attempted_model,
                "attempted_choice": attempted_choice,
                "minimum_confidence": minimum_confidence,
                "latency_ms": latency_ms if engine == "Jev" else None,
                "fallback_used": not actual_jev,
                "fallback_reason": None if engine == "Jev" else fallback_reason,
                "decision_id": decision_id,
                "decision_type": "locator_candidate_selection",
                "candidate_ids": [item["candidate_id"] for item in candidates],
                "probabilities": decision.probabilities if decision and engine == "Jev" else {},
            },
        )

        verification: dict[str, bool | None] = {
            "unique": False,
            "visible": False,
            "enabled": None,
            "editable": None,
            "clickable": None,
            "verified": False,
        }
        verified_candidate = None
        ordered = (
            ([selected] if selected else [])
            if require_jev
            else ([selected] if selected else []) + [item for item in candidates if item is not selected]
        )
        if page is not None or browser_session_id is not None:
            for candidate in ordered:
                await emit(
                    "verification_started",
                    "Playwright verification started",
                    stage="verification",
                    metadata={"candidate_id": candidate["candidate_id"]},
                )
                verification = (
                    await self.browser_runtime.verify_locator(browser_session_id, candidate, event)
                    if browser_session_id is not None
                    else await self.browser_runtime.verify_page_locator(page, candidate, event)
                )
                await history.record(safe_url, candidate["locator"], bool(verification["verified"]), verification=True)
                await emit(
                    "verification_completed",
                    "Playwright verification passed" if verification["verified"] else "Playwright verification failed",
                    stage="verification",
                    message=" · ".join(
                        f"{key}={'yes' if value else 'no'}"
                        for key, value in verification.items()
                        if value is not None and key != "verified"
                    ),
                    metadata={
                        "candidate_id": candidate["candidate_id"],
                        "status": "PASS" if verification["verified"] else "FAILED",
                        **verification,
                    },
                    duration=round((time.perf_counter() - started) * 1000, 1),
                )
                if verification["verified"]:
                    verified_candidate = candidate
                    if candidate is not selected:
                        selected = candidate
                        selected_id = candidate["candidate_id"]
                        engine = "Local Strategy"
                        fallback_reason = "selected_candidate_failed_verification"
                        if actual_jev:
                            await emit(
                                "decision.fallback",
                                "Fallback to Local Strategy",
                                stage="decision",
                                metadata={
                                    "provider": "local-strategy",
                                    "candidate_id": selected_id,
                                    "selected_locator": selected["locator"],
                                    "candidate_count": len(candidates),
                                    "confidence": None,
                                    "verified": True,
                                    "fallback_used": True,
                                    "fallback_reason": fallback_reason,
                                },
                            )
                    break
                if require_jev:
                    fallback_reason = "JEV_SELECTED_CANDIDATE_FAILED"
                    await emit(
                        "jev.selected_candidate_failed",
                        "Jev-selected candidate failed browser verification",
                        stage="verification",
                        metadata={
                            "decision_id": decision_id,
                            "candidate_id": candidate["candidate_id"],
                            "provider": "jev",
                            "fallback_used": False,
                            "verification": verification,
                        },
                    )

        browser_verified = page is not None or browser_session_id is not None
        if selected is not None and browser_verified and verified_candidate is None:
            selected = None
            selected_id = None
        if selected is not None and not browser_verified and engine == "Jev":
            # Non-browser callers must verify later; keep the result explicitly pending.
            verification["verified"] = False

        await emit(
            "diagnosis_completed",
            "Locator decision analysis completed",
            stage="analysis",
            metadata={"engine": engine, "fallback_reason": None if engine == "Jev" else fallback_reason},
        )
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        await emit(
            "repair_suggested",
            "Verified locator suggestion prepared"
            if verification["verified"]
            else "Locator suggestion requires review",
            stage="repair",
            metadata={"candidate_id": selected_id, "verified": verification["verified"]},
            duration=elapsed,
        )
        summary = {
            "provider": "jev" if engine == "Jev" else "blocked" if require_jev else "local-strategy",
            "engine": engine,
            "model": decision.model if engine == "Jev" else None,
            "latency_ms": latency_ms if engine == "Jev" else None,
            "confidence": decision.confidence if decision else None,
            "attempted_provider": attempted_provider,
            "attempted_model": attempted_model,
            "attempted_choice": attempted_choice,
            "minimum_confidence": minimum_confidence,
            "candidate_count": len(candidates),
            "candidate_id": selected_id,
            "selected_locator": selected.get("locator") if selected else None,
            "verified": bool(verification["verified"]),
            "decision_id": decision_id,
            "decision_type": "locator_candidate_selection",
            "candidate_ids": [item["candidate_id"] for item in candidates],
            "probabilities": decision.probabilities if decision and engine == "Jev" else {},
            "fallback_used": not actual_jev,
            "fallback_reason": None if engine == "Jev" else fallback_reason,
        }
        return {
            "ranked_candidates": candidates,
            "selected_candidate": selected,
            "summary": summary,
            "verification": verification,
            "trace": [event.model_dump(mode="json") for event in trace],
        }
