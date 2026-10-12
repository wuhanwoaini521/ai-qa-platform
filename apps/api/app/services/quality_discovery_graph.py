from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from datetime import datetime, timezone
from typing import Any

from project_model.models import DecisionResult, DecisionSignalRequest

logger = logging.getLogger("app.discovery")


class QualityDiscoveryGraphMixin:
    async def _append_requirements(self, run_id: str, analysis: dict[str, Any]) -> dict[str, Any]:
        await self._change_result(run_id, lambda result: result.update(analysis))
        row = await self.get(run_id)
        return row.result if row else {}

    async def _upsert_state(self, run_id: str, state: dict[str, Any]) -> dict[str, Any]:
        def change(result):
            existing = self._find_state(result, state["fingerprint"])
            if existing:
                state["depth"] = existing.get("depth", 0)
                state["attempted_candidate_ids"] = existing.get("attempted_candidate_ids", [])
                state["skipped_candidate_ids"] = existing.get("skipped_candidate_ids", [])
                state["evidence_id"] = existing.get("evidence_id") or state.get("evidence_id")
                state["screenshot_evidence_id"] = existing.get("screenshot_evidence_id") or state.get(
                    "screenshot_evidence_id"
                )
                state["similar_to_state_id"] = existing.get("similar_to_state_id") or state.get("similar_to_state_id")
                state["similarity"] = existing.get("similarity") or state.get("similarity")
                result["states"] = [
                    state if item["fingerprint"] == state["fingerprint"] else item for item in result["states"]
                ]
            else:
                state["depth"] = min(
                    self._state_depth(result, state["state_id"]),
                    self._get_config().discovery.max_depth + 1,
                )
                result["states"].append(state)
            self._verify_features_for_state(result, state)

        await self._change_result(run_id, change)
        row = await self.get(run_id)
        return row.result if row else {}

    @staticmethod
    def _find_state(result: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
        return next((item for item in result.get("states", []) if item.get("fingerprint") == fingerprint), None)

    @staticmethod
    def _verify_features_for_state(result: dict[str, Any], state: dict[str, Any]) -> None:
        evidence_id = state.get("evidence_id")
        if not evidence_id:
            return
        actions = [
            action
            for action in result.get("actions", [])
            if action.get("status") == "EXECUTED"
            and action.get("state_changed") is True
            and action.get("to_fingerprint") == state.get("fingerprint")
            and action.get("target_id")
        ]
        for action in actions:
            scoped_target_id = f"{action.get('from_state_id')}:{action['target_id']}"
            for feature in result.get("features", []):
                if scoped_target_id not in feature.get("target_ids", []):
                    continue
                action_ids = feature.setdefault("verification_action_ids", [])
                if action["candidate_id"] not in action_ids:
                    action_ids.append(action["candidate_id"])
                state_ids = feature.setdefault("verification_state_ids", [])
                if state.get("state_id") not in state_ids:
                    state_ids.append(state["state_id"])
                evidence_ids = feature.setdefault("evidence_ids", [])
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
                feature["verified_by_action_id"] = action["candidate_id"]
                feature["status"] = "VERIFIED"
                feature["trust"] = "VERIFIED"

    @staticmethod
    def _state_depth(result: dict[str, Any], state_id: str) -> int:
        states = result.get("states", [])
        if not states:
            return 0
        depths = {states[0]["state_id"]: 0}
        changed = True
        while changed:
            changed = False
            for edge in result.get("edges", []):
                source, target = edge.get("from_state_id"), edge.get("to_state_id")
                if source not in depths or not target:
                    continue
                next_depth = depths[source] + 1
                if next_depth < depths.get(target, next_depth + 1):
                    depths[target] = next_depth
                    changed = True
        return depths.get(state_id, max((item.get("depth", 0) for item in states), default=0) + 1)

    async def _record_features(self, run_id: str, plan: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        controls = {f"el_{control['index']}": control for control in state["controls"]}
        visible_text = str(state.get("main_content") or "").casefold()
        evidence_id = state.get("evidence_id")

        def change(result):
            result.setdefault("features", [])
            for signal in plan.get("features", []):
                target = controls.get(signal.get("target_id"))
                evidence_text = str(signal.get("evidence_text") or "").strip()
                grounded = bool(target or (len(evidence_text) >= 3 and evidence_text.casefold() in visible_text))
                feature_id = self._feature_id(signal["name"])
                feature = next((item for item in result["features"] if item["feature_id"] == feature_id), None)
                if feature is None:
                    feature = {
                        "feature_id": feature_id,
                        "name": signal["name"],
                        "description": signal.get("description", ""),
                        "page": state.get("title") or state.get("url"),
                        "status": "OBSERVED" if grounded else "INFERRED",
                        "evidence_ids": [],
                        "state_ids": [],
                        "inference_state_ids": [],
                        "requirement_ids": [],
                        "target_ids": [],
                        "confidence": signal.get("confidence", 0.5),
                        "mapping_confidence": 0.0,
                        "mapping_status": "UNMAPPED" if grounded else "NEEDS_REVIEW",
                    }
                    result["features"].append(feature)
                feature["confidence"] = max(float(feature.get("confidence", 0)), float(signal.get("confidence", 0.5)))
                if grounded:
                    if feature.get("status") != "VERIFIED":
                        feature["status"] = "OBSERVED"
                    if evidence_id and evidence_id not in feature["evidence_ids"]:
                        feature["evidence_ids"].append(evidence_id)
                    if state["state_id"] not in feature["state_ids"]:
                        feature["state_ids"].append(state["state_id"])
                elif state["state_id"] not in feature.setdefault("inference_state_ids", []):
                    feature["inference_state_ids"].append(state["state_id"])
                scoped_target_id = f"{state['state_id']}:{signal['target_id']}" if signal.get("target_id") else None
                if grounded and scoped_target_id and scoped_target_id not in feature["target_ids"]:
                    feature["target_ids"].append(scoped_target_id)
                feature["description"] = feature.get("description") or signal.get("description", "")
                feature["page_type"] = plan.get("page_type", "unknown")
                feature["trust"] = feature["status"]

            result.setdefault("goals", [])
            known_requirements = {item.get("id") for item in result.get("requirements", [])}
            known_goal_titles = {str(item.get("title", "")).casefold() for item in result["goals"]}
            for goal in plan.get("goals", []):
                title = str(goal.get("title") or "").strip()
                if not title or title.casefold() in known_goal_titles:
                    continue
                requirement_id = goal.get("requirement_id")
                if requirement_id not in known_requirements:
                    requirement_id = None
                result["goals"].append(
                    {
                        **goal,
                        "requirement_id": requirement_id,
                        "state_id": state["state_id"],
                        "status": "INFERRED",
                        "evidence_ids": [evidence_id] if evidence_id else [],
                    }
                )
                known_goal_titles.add(title.casefold())

        await self._change_result(run_id, change)
        row = await self.get(run_id)
        return row.result if row else {}

    @staticmethod
    def _feature_id(name: str) -> str:
        token = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
        digest = hashlib.sha256(name.casefold().encode()).hexdigest()[:6]
        return f"feature-{(token[:40] or 'discovered')}-{digest}"

    async def _mark_attempted(self, run_id: str, fingerprint: str, candidate_id: str) -> None:
        def change(result):
            state = self._find_state(result, fingerprint)
            if state and candidate_id not in state.setdefault("attempted_candidate_ids", []):
                state["attempted_candidate_ids"].append(candidate_id)

        await self._change_result(run_id, change)

    async def _skip_candidates(
        self, run_id: str, fingerprint: str, candidates: list[dict[str, Any]], reason: str
    ) -> None:
        def change(result):
            state = self._find_state(result, fingerprint)
            if state is None:
                return
            skipped_ids = state.setdefault("skipped_candidate_ids", [])
            for candidate in candidates:
                candidate_id = candidate["candidate_id"]
                if candidate_id not in skipped_ids:
                    skipped_ids.append(candidate_id)

        await self._change_result(run_id, change)
        row = await self.get(run_id)
        state = self._find_state(row.result if row else {}, fingerprint)
        if state:
            await self._record_frontier(run_id, state["state_id"], candidates, "SKIPPED", reason)

    async def _record_frontier(
        self,
        run_id: str,
        state_id: str,
        candidates: list[dict[str, Any]],
        status: str,
        reason: str,
    ) -> None:
        if not candidates:
            return

        def change(result):
            frontier = result.setdefault("frontier", [])
            for candidate in candidates:
                candidate_id = candidate["candidate_id"]
                existing = next(
                    (
                        item
                        for item in frontier
                        if item.get("state_id") == state_id and item.get("candidate_id") == candidate_id
                    ),
                    None,
                )
                record = {
                    "state_id": state_id,
                    "candidate_id": candidate_id,
                    "target": candidate.get("target", "")[:140],
                    "status": status,
                    "reason": reason[:300],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                if existing:
                    existing.update(record)
                else:
                    frontier.append(record)

        await self._change_result(run_id, change)

    async def _set_state_page_type(self, run_id: str, fingerprint: str, page_type: str) -> None:
        normalized_type = re.sub(r"[^a-z0-9_-]+", "_", str(page_type).casefold()).strip("_")[:80] or "unknown"

        def change(result):
            state = self._find_state(result, fingerprint)
            if state:
                state["page_type"] = normalized_type

        await self._change_result(run_id, change)

    async def _append_action(self, run_id: str, action: dict[str, Any]) -> None:
        await self._change_result(run_id, lambda result: result.setdefault("actions", []).append(action))

    async def _replace_action(self, run_id: str, action: dict[str, Any]) -> None:
        def change(result):
            for index, existing in enumerate(result.get("actions", [])):
                if existing.get("candidate_id") == action.get("candidate_id") and existing.get(
                    "from_state_id"
                ) == action.get("from_state_id"):
                    result["actions"][index] = action
                    break

        await self._change_result(run_id, change)

    async def _append_edge(
        self, run_id: str, from_state_id: str, to_fingerprint: str, candidate: dict[str, Any]
    ) -> None:
        row = await self.get(run_id)
        if row is None:
            return
        to_state = self._find_state(row.result or {}, to_fingerprint)
        edge = {
            "from_state_id": from_state_id,
            "to_state_id": to_state.get("state_id") if to_state else f"state_{to_fingerprint[:16]}",
            "action": candidate["action_type"],
            "label": candidate["target"],
            "candidate_id": candidate["candidate_id"],
        }
        await self._change_result(
            run_id,
            lambda result: (
                result.setdefault("edges", []).append(edge) if edge not in result.setdefault("edges", []) else None
            ),
        )

    async def _link_feature_evidence(
        self, run_id: str, state: dict[str, Any], candidate: dict[str, Any], changed: bool
    ) -> None:
        if not changed:
            return
        scoped_target_id = f"{state['state_id']}:{candidate.get('target_id')}"

        def change(result):
            for feature in result.get("features", []):
                if scoped_target_id in feature.get("target_ids", []):
                    action_ids = feature.setdefault("observed_transition_action_ids", [])
                    if candidate["candidate_id"] not in action_ids:
                        action_ids.append(candidate["candidate_id"])

        await self._change_result(run_id, change)

    async def _record_ai(self, run_id: str, usage: dict[str, Any]) -> None:
        def change(result):
            ai = result.setdefault(
                "ai",
                {
                    "provider": None,
                    "model": None,
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "unknown_token_calls": 0,
                },
            )
            ai["provider"], ai["model"] = usage.get("provider"), usage.get("model")
            ai["calls"] += 1
            for token_name in ("input_tokens", "output_tokens"):
                value = usage.get(token_name)
                if isinstance(value, int):
                    ai[token_name] += value
                else:
                    ai["unknown_token_calls"] += 1

        await self._change_result(run_id, change)

    async def _score_candidate_priority(
        self,
        run_id: str,
        *,
        state: dict[str, Any],
        choices: dict[str, dict[str, Any]],
        priority_ids: list[str],
    ) -> list[str]:
        ask_score = getattr(self.decisions, "ask_score", None)
        if not callable(ask_score):
            return priority_ids

        limit = self._get_config().discovery.max_candidates
        scores: dict[str, float] = {}
        for candidate_id in priority_ids[:limit]:
            candidate = choices.get(candidate_id)
            if candidate is None:
                continue
            score_started = time.perf_counter()
            try:
                result = await ask_score(
                    DecisionSignalRequest(
                        name="discovery_candidate_score",
                        state={
                            **state,
                            "candidate": {
                                "candidate_id": candidate_id,
                                "action": candidate.get("action_type"),
                                "target": candidate.get("target"),
                                "expected_effect": candidate.get("expected_effect"),
                            },
                        },
                        instructions=(
                            "Score this observed candidate from 0 to 1 for relevance to the active exploration goal "
                            "and expected evidence. This is only a ranking recommendation: do not judge action safety, "
                            "test PASS/FAIL, or whether the action is allowed."
                        ),
                    ),
                    run_id=run_id,
                    daily_request_reserve=1,
                )
            except Exception as error:
                result = DecisionResult(
                    provider="fallback", fallback_used=True, reason=f"score_error:{type(error).__name__}"
                )
            latency_ms = round((time.perf_counter() - score_started) * 1000, 1)
            if not isinstance(result, DecisionResult):
                continue
            score = result.score
            confidence = result.confidence
            minimum_confidence = (
                result.minimum_confidence
                if isinstance(result.minimum_confidence, (int, float))
                and not isinstance(result.minimum_confidence, bool)
                else self._get_config().jev.minimum_confidence
            )
            trusted_score = (
                result.provider == "jev"
                and not result.fallback_used
                and isinstance(score, (int, float))
                and not isinstance(score, bool)
                and math.isfinite(score)
                and 0 <= score <= 1
                and isinstance(confidence, (int, float))
                and not isinstance(confidence, bool)
                and math.isfinite(confidence)
                and 0 <= confidence <= 1
                and math.isfinite(minimum_confidence)
                and 0 <= minimum_confidence <= 1
                and confidence >= minimum_confidence
            )
            if trusted_score:
                scores[candidate_id] = float(score)
            usage = result.usage or {}
            sample_metadata = {
                "decision_point": "discovery_candidate_score",
                "candidate_id": candidate_id,
                "score": float(score) if trusted_score else None,
                "confidence": confidence if trusted_score else None,
                "provider": result.provider,
                "fallback_used": result.fallback_used or result.provider == "fallback",
                "reason": result.reason,
                "latency_ms": latency_ms,
                "status": "AVAILABLE" if trusted_score else "UNAVAILABLE",
                "advisory_only": True,
                **{
                    token_name: usage[token_name]
                    for token_name in ("input_tokens", "output_tokens")
                    if isinstance(usage.get(token_name), int)
                    and not isinstance(usage.get(token_name), bool)
                    and usage[token_name] >= 0
                },
            }
            try:
                await self._event(
                    run_id,
                    "decision.score_recommendation",
                    "Jev score recommendation recorded."
                    if trusted_score
                    else "Score recommendation unavailable; existing priority order was retained.",
                    sample_metadata,
                )
            except Exception as error:
                logger.warning("Discovery score telemetry write failed (%s)", type(error).__name__)
        if not scores:
            return priority_ids
        original_order = {candidate_id: index for index, candidate_id in enumerate(priority_ids)}
        return sorted(
            priority_ids,
            key=lambda candidate_id: (-scores.get(candidate_id, -1.0), original_order[candidate_id]),
        )

    async def _record_decision(
        self,
        run_id: str,
        decision,
        *,
        decision_id: str,
        candidate_ids: list[str],
        priority_candidate_ids: list[str],
    ) -> None:
        def change(result):
            jev = result.setdefault(
                "jev", {"provider": None, "model": None, "decisions": 0, "fallbacks": 0, "usage": {}}
            )
            if decision.fallback_used:
                if jev.get("provider") is None:
                    jev["provider"] = "fallback"
                    jev["model"] = None
            else:
                jev["provider"] = decision.provider
                jev["model"] = decision.model
                jev["usage"] = decision.usage or {}
            jev["decisions"] += 1
            jev["fallbacks"] += int(bool(decision.fallback_used))
            result.setdefault("decisions", []).append(
                {
                    "decision_id": decision_id,
                    "choice": decision.choice,
                    "selected_candidate_id": (
                        decision.choice if not decision.fallback_used and decision.choice in candidate_ids else None
                    ),
                    "attempted_choice": decision.attempted_choice,
                    "candidate_count": len(candidate_ids),
                    "candidate_ids": candidate_ids,
                    "priority_candidate_ids": priority_candidate_ids,
                    "provider": decision.provider,
                    "model": decision.model,
                    "attempted_provider": decision.attempted_provider,
                    "attempted_model": decision.attempted_model,
                    "confidence": decision.confidence,
                    "minimum_confidence": decision.minimum_confidence,
                    "probabilities": decision.probabilities,
                    "fallback_used": decision.fallback_used,
                    "reason": decision.reason,
                }
            )

        await self._change_result(run_id, change)
