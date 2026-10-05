from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from project_model.models import DecisionOption, DecisionRequest
from qa_core.ai.trace import AITraceEvent, make_trace_event
from qa_core.failure.redactor import SensitiveRedactor
from qa_core.healing.locator_intelligence import rank_locator_candidates

from app.services.decision_service import DecisionService
from app.services.decision_settings_service import DecisionSettingsService

_METHODS = {
    "role": "get_by_role",
    "label": "get_by_label",
    "test_id": "get_by_test_id",
    "placeholder": "get_by_placeholder",
    "text": "get_by_text",
}


class LocatorDecisionService:
    """Shared candidate scoring, Jev/local choice, and Playwright verification."""

    def __init__(
        self,
        decision_service: DecisionService | None = None,
        settings_service: DecisionSettingsService | None = None,
    ) -> None:
        self.settings_service = settings_service or DecisionSettingsService()
        self.decision_service = decision_service or DecisionService(settings_service=self.settings_service)

    @staticmethod
    def generate_candidates(event: dict[str, Any]) -> list[dict[str, Any]]:
        """Enrich only locators observed for the target; never synthesize a selector."""
        raw = rank_locator_candidates(event.get("candidates") or [])[:10]
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
    def format_locator(candidate: dict[str, Any]) -> str:
        kind = str(candidate.get("kind", "css"))
        value = json.dumps(str(candidate.get("value", "")), ensure_ascii=False)
        if kind == "role":
            name = json.dumps(str(candidate.get("name", "")), ensure_ascii=False)
            return f"get_by_role({value}, name={name})"
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
        case_execution_id: str | None = None,
        step_id: str | None = None,
        on_event: Callable[[AITraceEvent], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        trace: list[AITraceEvent] = []
        safe_url = SensitiveRedactor.redact_url(str(event.get("url") or ""))
        from app.services.locator_history_service import LocatorHistoryService

        history = LocatorHistoryService()
        await history.enrich(safe_url, candidates)
        ranked = rank_locator_candidates(candidates)
        scores = {item["candidate_id"]: item["confidence"] for item in ranked}
        for item in candidates:
            item["static_score"] = scores[item["candidate_id"]]
        candidates.sort(key=lambda item: item["static_score"], reverse=True)

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
            if (
                event_type == "failed"
                or event_type == "verification_completed"
                and not (metadata or {}).get("verified")
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
        fallback_reason = "jev_disabled"
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
                decision = await asyncio.wait_for(
                    self.decision_service.choose(request, run_id=run_id, allow_missing_confidence=True), timeout=3.5
                )
                latency_ms = round((time.perf_counter() - decision_started) * 1000, 1)
                fallback_reason = decision.reason or "provider_unavailable"
            except asyncio.TimeoutError:
                fallback_reason = "timeout"
            except Exception as error:
                fallback_reason = type(error).__name__

        actual_jev = bool(decision and decision.provider == "jev" and not decision.fallback_used and decision.choice)
        selected_id = str(decision.choice) if actual_jev else None
        candidate_by_id = {item["candidate_id"]: item for item in candidates}
        selected = candidate_by_id.get(selected_id) if selected_id else None
        engine = "Jev" if selected is not None and actual_jev else "Local Strategy"
        if selected is None and candidates:
            selected = candidates[0]
            selected_id = selected["candidate_id"]

        await emit(
            "decision_completed",
            "Jev selected candidate" if engine == "Jev" else "Local Strategy selected candidate",
            stage="decision",
            message=(selected["locator"] if selected else "No usable candidate")
            + (f" · {latency_ms:.1f} ms" if engine == "Jev" else ""),
            metadata={
                "provider": "jev" if engine == "Jev" else "local-strategy",
                "model": decision.model if engine == "Jev" else None,
                "candidate_id": selected_id,
                "selected_locator": selected.get("locator") if selected else None,
                "candidate_count": len(candidates),
                "confidence": decision.confidence if engine == "Jev" else None,
                "latency_ms": latency_ms if engine == "Jev" else None,
                "fallback_reason": None if engine == "Jev" else fallback_reason,
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
        ordered = ([selected] if selected else []) + [item for item in candidates if item is not selected]
        if page is not None:
            for candidate in ordered:
                await emit(
                    "verification_started",
                    "Playwright verification started",
                    stage="verification",
                    metadata={"candidate_id": candidate["candidate_id"]},
                )
                verification = await self.verify_candidate(page, candidate, event)
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

        if selected is not None and page is not None and verified_candidate is None:
            selected = None
            selected_id = None
        if selected is not None and page is None and engine == "Jev":
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
            "provider": "jev" if engine == "Jev" else "local-strategy",
            "engine": engine,
            "model": decision.model if engine == "Jev" else None,
            "latency_ms": latency_ms if engine == "Jev" else None,
            "confidence": decision.confidence if engine == "Jev" else None,
            "candidate_count": len(candidates),
            "candidate_id": selected_id,
            "selected_locator": selected.get("locator") if selected else None,
            "verified": bool(verification["verified"]),
            "fallback_reason": None if engine == "Jev" else fallback_reason,
        }
        return {
            "ranked_candidates": candidates,
            "selected_candidate": selected,
            "summary": summary,
            "verification": verification,
            "trace": [event.model_dump(mode="json") for event in trace],
        }

    @staticmethod
    async def verify_candidate(page: Any, candidate: dict[str, Any], event: dict[str, Any]) -> dict[str, bool | None]:
        locator = page
        try:
            for selector in event.get("frame_path") or []:
                locator = locator.frame_locator(selector)
            kind = candidate.get("kind")
            value = str(candidate.get("value") or "")
            if kind == "role":
                locator = locator.get_by_role(value, name=candidate.get("name"), exact=candidate.get("exact", True))
            elif kind == "test_id":
                locator = locator.get_by_test_id(value)
            elif kind == "label":
                locator = locator.get_by_label(value, exact=candidate.get("exact", True))
            elif kind == "placeholder":
                locator = locator.get_by_placeholder(value, exact=candidate.get("exact", True))
            elif kind == "text":
                locator = locator.get_by_text(value, exact=candidate.get("exact", True))
            elif kind == "id":
                locator = locator.locator(f"[id={json.dumps(value)}]")
            elif kind == "name":
                locator = locator.locator(f"[name={json.dumps(value)}]")
            else:
                locator = locator.locator(value if kind != "xpath" or value.startswith("xpath=") else f"xpath={value}")
            count = await locator.count()
            target = locator.nth(candidate["nth"]) if candidate.get("nth") is not None else locator
            visible = count > 0 and await target.is_visible()
            interactive = str(event.get("action") or "") in {
                "click",
                "double_click",
                "fill",
                "select",
                "check",
                "uncheck",
                "press",
                "hover",
            }
            enabled = count > 0 and await target.is_enabled() if interactive else None
            editable = count > 0 and await target.is_editable() if event.get("action") == "fill" else None
            clickable = None
            if event.get("action") in {"click", "double_click"}:
                clickable = bool(
                    await target.evaluate("""el => {
                      const tag = el.tagName.toLowerCase();
                      const role = el.getAttribute('role');
                      const interactive = (tag === 'a' && Boolean(el.getAttribute('href')))
                        || ['button', 'input', 'textarea', 'select', 'summary'].includes(tag)
                        || ['button', 'link', 'checkbox', 'radio', 'switch', 'menuitem'].includes(role);
                      const rect = el.getBoundingClientRect();
                      if (!interactive || rect.width <= 0 || rect.height <= 0) return false;
                      const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
                      if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) return true;
                      const hit = document.elementFromPoint(x, y);
                      return hit === el || el.contains(hit);
                    }""")
                )
            unique = count == 1
            verified = unique and visible and enabled is not False and editable is not False and clickable is not False
            return {
                "unique": unique,
                "visible": visible,
                "enabled": enabled,
                "editable": editable,
                "clickable": clickable,
                "verified": verified,
            }
        except Exception:
            return {
                "unique": False,
                "visible": False,
                "enabled": False,
                "editable": False,
                "clickable": False,
                "verified": False,
            }
