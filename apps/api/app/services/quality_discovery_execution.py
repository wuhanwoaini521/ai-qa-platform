from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from project_model.lifecycle import StructuredRequirementModel
from project_model.models import DecisionOption, DecisionRequest
from qa_core.ai.browser_safety import classify_browser_action
from qa_core.ai.models import AICompletionRequest
from qa_core.failure.redactor import SensitiveRedactor

from app.persistence.models import QualityDiscoveryRunORM, utc_now
from app.repositories.artifact_repo import ArtifactRepository
from app.repositories.requirement_repo import RequirementRepository
from app.services.artifact_storage_service import ArtifactStorageService
from app.services.quality_discovery_models import (
    DiscoveryBlocked,
    DiscoveryMode,
    DiscoveryPlan,
    DiscoveryStatus,
    RequirementAnalysis,
    RequirementSignal,
)


class QualityDiscoveryExecutionMixin:
    async def _execute(self, run_id: str) -> None:
        session_id: str | None = None
        try:
            row = await self.get(run_id)
            if row is None or row.status in self.TERMINAL:
                return
            config = self._get_config().discovery
            result = json.loads(json.dumps(row.result or {}))
            runtime = self._get_config()
            await self._change_result(
                run_id,
                lambda current: current.update(
                    {
                        "runtime_config": {
                            "ai_provider": runtime.ai.provider,
                            "ai_model": runtime.ai.model,
                            "jev_provider": runtime.jev.provider,
                            "jev_model": runtime.jev.model,
                            "require_ai": config.require_ai,
                            "require_jev": config.require_jev,
                            "safe_mode": config.safe_mode,
                            "max_actions": config.max_actions,
                            "max_states": config.max_states,
                            "max_depth": config.max_depth,
                            "max_candidates": config.max_candidates,
                            "feature_mapping_confidence": config.feature_mapping_confidence,
                        }
                    }
                ),
            )
            self._assert_runtime_ready(config)
            await self._update(run_id, status=DiscoveryStatus.RUNNING.value, error=None)
            await self._event(run_id, "run.started", "正在初始化产品探索。")
            requirement_input = await self._requirement_input(row)
            if requirement_input and not result.get("requirements"):
                analysis = await self._analyze_requirements(run_id, requirement_input)
                result = await self._append_requirements(run_id, analysis)
            allow_cart_mutation = row.mode in {DiscoveryMode.VALIDATE.value, DiscoveryMode.AUDIT.value} and bool(
                requirement_input and self._requirement_allows_cart_mutation(requirement_input["text"])
            )
            allow_repeat_cart_mutation = allow_cart_mutation and bool(
                requirement_input and self._requirement_allows_repeat_cart_mutation(requirement_input["text"])
            )
            allowed_hosts = self._allowed_hosts(row)
            session = await self.browser_runtime.create_session(block_service_workers=True)
            session_id = session.id
            restrict_navigation = getattr(self.browser_runtime, "restrict_navigation", None)
            if callable(restrict_navigation):
                await restrict_navigation(session_id, allowed_hosts)
            resume_url = self._resume_url(result, row.start_url)
            response_status = await self.browser_runtime.navigate(session_id, resume_url)
            page = await self.browser_runtime.get_page(session_id)
            if not self._host_allowed(page.url, allowed_hosts):
                raise DiscoveryBlocked("Navigation redirected outside the start domain and allowed domain list.")
            if response_status is not None and response_status >= 500:
                raise DiscoveryBlocked(f"Start URL returned HTTP {response_status}; exploration stopped.")

            started = time.monotonic()
            persisted_elapsed = max(0.0, (utc_now() - row.created_at).total_seconds())
            max_runtime = config.max_runtime_minutes * 60
            while True:
                await self._wait_if_paused(run_id)
                if self._stop_events[run_id].is_set():
                    await self._finish(run_id, DiscoveryStatus.STOPPED.value, "用户停止了探索。")
                    return
                current = await self.get(run_id)
                if current is None:
                    return
                current_result = current.result or {}
                action_count = len(current_result.get("actions") or [])
                failures = sum(
                    action.get("status") in {"FAILED", "TARGET_NOT_VERIFIED", "BLOCKED_BY_DOMAIN_POLICY"}
                    for action in current_result.get("actions") or []
                )
                if (
                    action_count >= config.max_actions
                    or max(persisted_elapsed, time.monotonic() - started) >= max_runtime
                ):
                    await self._finish(run_id, DiscoveryStatus.BUDGET_EXHAUSTED.value, "探索预算已达到配置上限。")
                    await self._build_quality_map(run_id)
                    return
                if failures >= config.max_failures:
                    await self._finish(run_id, DiscoveryStatus.BUDGET_EXHAUSTED.value, "已达到最大失败动作数量上限。")
                    await self._build_quality_map(run_id)
                    return

                snapshot = await self.browser_runtime.snapshot(
                    session_id,
                    include_screenshot=config.screenshot,
                    full_page=True,
                )
                if not self._host_allowed(snapshot.url, allowed_hosts):
                    raise DiscoveryBlocked("The current page left the start domain and allowed domain list.")
                controls = self._safe_controls(snapshot.controls)
                scroll = await page.evaluate(
                    "() => ({y: Math.round(window.scrollY), height: document.documentElement.scrollHeight, viewport: window.innerHeight})"
                )
                state_id, fingerprint = self._state_fingerprint(snapshot, controls, scroll)
                similar_state = self._find_similar_state(
                    current_result, snapshot, controls, config.state_similarity_threshold
                )
                state = self._state_record(snapshot, controls, scroll, state_id, fingerprint)
                if not config.capture_console:
                    state["console_errors"] = []
                if not config.capture_network:
                    state["network"] = {"responses": {}, "failures": 0, "sample_count": 0}
                if similar_state and not self._find_state(current_result, fingerprint):
                    state["similar_to_state_id"] = similar_state["state_id"]
                    state["similarity"] = similar_state["score"]
                if (
                    not self._find_state(current_result, fingerprint)
                    and len(current_result.get("states") or []) >= config.max_states
                ):
                    await self._finish(run_id, DiscoveryStatus.BUDGET_EXHAUSTED.value, "已达到最大产品状态数量上限。")
                    await self._build_quality_map(run_id)
                    return
                screenshot_count = sum(
                    bool(item.get("screenshot_evidence_id")) for item in current_result.get("states", [])
                )
                if not self._find_state(current_result, fingerprint):
                    state["evidence_id"] = await self._save_state_evidence(run_id, state_id, state)
                if (
                    snapshot.screenshot
                    and screenshot_count < config.max_screenshots
                    and not self._find_state(current_result, fingerprint)
                ):
                    state["screenshot_evidence_id"] = await self._save_screenshot(run_id, state_id, snapshot.screenshot)
                result = await self._upsert_state(run_id, state)
                state = self._find_state(result, fingerprint) or state
                if row.mode == DiscoveryMode.VALIDATE.value and self._all_acceptance_criteria_passed(
                    result.get("requirements") or [],
                    result.get("states") or [],
                    result.get("edges") or [],
                    result.get("actions") or [],
                ):
                    await self._finish(run_id, DiscoveryStatus.COMPLETED.value, None)
                    await self._build_quality_map(run_id)
                    return
                safe_title = self._safe_title(snapshot.title)
                await self._event(
                    run_id,
                    "state.observed",
                    f"已观察：{safe_title or self._safe_url(snapshot.url)}",
                    {"state_id": state_id},
                )

                depth_limited = int(state.get("depth", 0)) >= config.max_depth
                blocked_candidates = self._blocked_candidates(
                    state, allowed_hosts, allow_cart_mutation=allow_cart_mutation
                )
                await self._record_frontier(
                    run_id, state_id, blocked_candidates, "BLOCKED_BY_POLICY", "安全策略禁止执行此动作。"
                )
                candidates = self._candidate_actions(
                    state,
                    allowed_hosts,
                    len(state.get("controls", [])) + 1,
                    allow_cart_mutation=allow_cart_mutation,
                    skip_empty_cart_revisit=(
                        not allow_cart_mutation and self._has_observed_empty_cart(current_result.get("states") or [])
                    ),
                )
                attempted = set(state.get("attempted_candidate_ids") or [])
                skipped = set(state.get("skipped_candidate_ids") or [])
                handled = attempted | skipped
                pending = [candidate for candidate in candidates if candidate["candidate_id"] not in handled]
                pending = self._prioritize_variant_actions_before_cart(
                    pending,
                    current_result.get("actions") or [],
                    current_result.get("states") or [],
                    state,
                )
                pending = self._prioritize_cart_verification_after_add(
                    pending,
                    state,
                    current_result.get("actions") or [],
                    current_result.get("states") or [],
                    allow_repeat_same_variant=allow_repeat_cart_mutation,
                )
                if depth_limited and pending:
                    await self._record_frontier(
                        run_id, state_id, pending, "PENDING", "当前状态已达到探索深度上限，候选动作未执行。"
                    )
                    await self._finish(
                        run_id,
                        DiscoveryStatus.BUDGET_EXHAUSTED.value,
                        "已达到最大探索深度，当前状态仍有未检查的安全控件。",
                    )
                    await self._build_quality_map(run_id)
                    return
                if not pending and state.get("depth", 0) > 0:
                    back = self._back_candidate(current_result, state, allowed_hosts)
                    if back and back["candidate_id"] not in attempted:
                        pending = [back]
                if not pending:
                    await self._finish(run_id, DiscoveryStatus.COMPLETED.value, None)
                    await self._build_quality_map(run_id)
                    return

                if state.get("similar_to_state_id"):
                    await self._skip_candidates(
                        run_id,
                        fingerprint,
                        pending,
                        f"与代表状态 {state['similar_to_state_id']} 的页面结构相似，已跳过重复动作采样。",
                    )
                    continue

                all_pending = pending
                pending = all_pending[: config.max_candidates]
                await self._record_frontier(run_id, state_id, all_pending, "PENDING", "安全候选动作等待 Jev 分批选择。")
                plan = await self._plan_next(run_id, row, snapshot, state, pending, result.get("requirements") or [])
                await self._record_ai(run_id, plan.pop("_usage"))
                result = await self._record_features(run_id, plan, state)
                for candidate in pending:
                    if candidate.get("action_type") == "search":
                        candidate["value"] = self._search_value_for_goal(
                            state,
                            plan,
                            result.get("requirements") or [],
                            current_result.get("actions") or [],
                            current_result.get("states") or [],
                        )
                await self._set_state_page_type(run_id, fingerprint, plan.get("page_type", "unknown"))
                # AI may prioritize candidates, but it cannot remove service-generated safe options.
                suggested = [
                    key for key in plan.get("candidate_ids", []) if key in {item["candidate_id"] for item in pending}
                ]
                if plan.get("done") and not suggested:
                    await self._skip_candidates(
                        run_id,
                        fingerprint,
                        pending,
                        "AI marked these remaining actions as having no meaningful exploration value.",
                    )
                    if len(all_pending) > len(pending):
                        continue
                    await self._finish(run_id, DiscoveryStatus.COMPLETED.value, None)
                    await self._build_quality_map(run_id)
                    return
                ordered_pending = sorted(
                    pending,
                    key=lambda item: (
                        suggested.index(item["candidate_id"]) if item["candidate_id"] in suggested else len(suggested)
                    ),
                )
                decision_pending = self._filter_repeated_search_candidates(
                    ordered_pending, current_result.get("actions") or []
                )
                decision_pending = self._filter_repeated_select_candidates(
                    decision_pending,
                    current_result.get("actions") or [],
                    current_result.get("states") or [],
                    state,
                    allow_repeat_same_variant=allow_repeat_cart_mutation,
                )
                decision_candidate_ids = {item["candidate_id"] for item in decision_pending}
                repeated_searches = [
                    item
                    for item in ordered_pending
                    if item["candidate_id"] not in decision_candidate_ids and item.get("action_type") == "search"
                ]
                repeated_selections = [
                    item
                    for item in ordered_pending
                    if item["candidate_id"] not in decision_candidate_ids and item.get("action_type") == "select"
                ]
                if repeated_searches:
                    await self._skip_candidates(
                        run_id,
                        fingerprint,
                        repeated_searches,
                        "本次探索已经执行过通用搜索，跳过重复搜索以检查其他功能。",
                    )
                if repeated_selections:
                    await self._skip_candidates(
                        run_id,
                        fingerprint,
                        repeated_selections,
                        "当前商品的该规格控件已经产生过一次状态变化，跳过重复切换。",
                    )
                if not decision_pending:
                    if len(all_pending) > len(pending):
                        continue
                    await self._finish(run_id, DiscoveryStatus.COMPLETED.value, None)
                    await self._build_quality_map(run_id)
                    return
                choices = {item["candidate_id"]: item for item in decision_pending}
                suggested = [candidate_id for candidate_id in suggested if candidate_id in choices]
                base_priority = suggested or list(choices)
                suggested = await self._score_candidate_priority(
                    run_id,
                    state={
                        "state_id": state_id,
                        "url": self._safe_url(snapshot.url),
                        "page_type": plan.get("page_type", "unknown"),
                        "goal": row.mode,
                        "active_goal": self._active_goal_context(
                            plan,
                            result.get("requirements") or [],
                            current_result.get("actions") or [],
                            current_result.get("states") or [],
                        ),
                    },
                    choices=choices,
                    priority_ids=base_priority,
                )
                decision = await self.decisions.choose(
                    DecisionRequest(
                        name="exploration_action_selection",
                        state={
                            "state_id": state_id,
                            "url": self._safe_url(snapshot.url),
                            "page_type": plan.get("page_type", "unknown"),
                            "goal": row.mode,
                            "active_goal": self._active_goal_context(
                                plan,
                                result.get("requirements") or [],
                                current_result.get("actions") or [],
                                current_result.get("states") or [],
                            ),
                            "planner_guidance": {
                                "goals": plan.get("goals", [])[:10],
                                "priority_candidate_ids": suggested,
                            },
                            "candidates": [
                                {
                                    "key": candidate_id,
                                    "action": candidate["action_type"],
                                    "target": candidate["target"],
                                    "expected_effect": candidate["expected_effect"],
                                    "target_role": candidate.get("target_role"),
                                    "target_tag": candidate.get("target_tag"),
                                    "operation": candidate.get("operation"),
                                    "planner_priority": (
                                        suggested.index(candidate_id) + 1 if candidate_id in suggested else None
                                    ),
                                }
                                for candidate_id, candidate in choices.items()
                            ],
                        },
                        options=[
                            DecisionOption(
                                key=candidate_id,
                                description=(
                                    f"AI planner priority {suggested.index(candidate_id) + 1}; "
                                    if candidate_id in suggested
                                    else ""
                                )
                                + f"{candidate['action_type']} {candidate['target']}: {candidate['expected_effect']}"[
                                    :1000
                                ],
                            )
                            for candidate_id, candidate in choices.items()
                        ],
                        instructions=(
                            "若提供 active_goal，先按该目标及其关联验收标准选择最相关的安全动作；"
                            "否则根据当前模式和未覆盖的规划目标推进最高优先级目标。"
                            "候选顺序是 AI planner 和 Jev score 的建议信号；优先选择排名靠前且与当前状态相符的动作。"
                            "若排序靠前的动作有具体状态或安全冲突，才选择其他候选或拒绝。"
                            "confidence 表示当前动作作为有证据支持的下一步的把握，不表示其他候选都无效。"
                            "多步验收标准应按步骤逐步验证；不要要求单个中间动作独立完成整条验收标准。"
                            "选项仅来自服务端观察到的安全控件；必须原样返回其中一个 key，不得发明动作。"
                        ),
                    ),
                    run_id=run_id,
                )
                decision_id = uuid4().hex
                await self._record_decision(
                    run_id,
                    decision,
                    decision_id=decision_id,
                    candidate_ids=list(choices),
                    priority_candidate_ids=suggested,
                )
                if decision.fallback_used:
                    attempted_candidate = choices.get(decision.attempted_choice)
                    if attempted_candidate and decision.reason in {"below_minimum_confidence", "confidence_missing"}:
                        skip_reason = "Jev 决策未达到置信度要求；该候选未执行，已跳过。"
                        await self._skip_candidates(run_id, fingerprint, [attempted_candidate], skip_reason)
                        await self._event(
                            run_id,
                            "decision.low_confidence_skipped",
                            "Jev 对该候选的置信度不足，未执行；继续评估其他安全候选。",
                            {
                                "candidate_id": attempted_candidate["candidate_id"],
                                "confidence": decision.confidence,
                                "minimum_confidence": decision.minimum_confidence,
                                "reason": decision.reason,
                            },
                        )
                        continue
                    if config.require_jev:
                        await self._record_frontier(
                            run_id, state_id, pending, "BLOCKED", "Jev fallback 被配置禁止；动作未执行。"
                        )
                        raise DiscoveryBlocked("Jev 不可用或置信度不足；按配置停止，未执行候选动作。")
                if not decision.choice or decision.choice not in choices:
                    await self._record_frontier(
                        run_id, state_id, pending, "BLOCKED", "决策服务未返回有效候选；动作未执行。"
                    )
                    raise DiscoveryBlocked("决策服务未返回可执行的候选动作。")
                selected = choices[decision.choice]
                await self._record_frontier(run_id, state_id, [selected], "SELECTED", "Jev 选择了此候选动作。")
                await self._event(
                    run_id,
                    "decision.selected",
                    f"Jev 选择：{selected['target']}",
                    {
                        "candidate_id": decision.choice,
                        "decision_id": decision_id,
                        "candidate_count": len(choices),
                        "provider": decision.provider,
                        "fallback_used": decision.fallback_used,
                    },
                )
                await self._execute_candidate(run_id, session_id, state, selected, decision_id=decision_id)
                await self._wait_if_paused(run_id)
        except asyncio.CancelledError:
            raise
        except DiscoveryBlocked as error:
            await self._finish(run_id, DiscoveryStatus.BLOCKED.value, self._safe_error(error))
            await self._build_quality_map(run_id)
        except Exception as error:
            await self._finish(run_id, DiscoveryStatus.FAILED.value, self._safe_error(error))
            await self._build_quality_map(run_id)
        finally:
            if session_id:
                await self.browser_runtime.close_session(session_id)

    async def _requirement_input(self, row: QualityDiscoveryRunORM) -> dict[str, str] | None:
        text = row.requirement_text
        if row.requirement_id:
            async with self.session_factory() as session:
                requirement = await RequirementRepository(session).get_by_id(row.requirement_id)
            if requirement is None:
                raise DiscoveryBlocked("Selected Requirement no longer exists.")
            text = "\n".join(
                part for part in (requirement.title, requirement.description, requirement.acceptance_criteria) if part
            )
        if not text.strip():
            return None
        return {"text": text[:20_000], "source_id": row.requirement_id or "PASTED"}

    @staticmethod
    def _requirement_analysis_chunks(text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        criterion_pattern = re.compile(r"^(?:AC[-_]?\d+\s*:|[A-Z][A-Z0-9_-]{0,15}\d+\s*:|[-*•]\s+|\d+[.)]\s+)", re.I)
        criteria = [line for line in lines if criterion_pattern.match(line)]
        context = [line for line in lines if not criterion_pattern.match(line)]
        if len(criteria) > 1:
            prefix = "\n".join(context)
            return [
                "\n".join(part for part in (prefix, *criteria[index : index + 2]) if part)
                for index in range(0, len(criteria), 2)
            ]

        if len(text) <= 1800:
            return [text]
        pieces = [piece.strip() for piece in re.split(r"(?<=[.!?。！？])\s*|\r?\n+", text) if piece.strip()]
        chunks: list[str] = []
        current = ""
        for piece in pieces:
            while len(piece) > 1800:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(piece[:1800])
                piece = piece[1800:]
            if current and len(current) + len(piece) + 1 > 1800:
                chunks.append(current)
                current = ""
            current = f"{current}\n{piece}" if current else piece
        if current:
            chunks.append(current)
        return chunks or [text]

    async def _analyze_requirements(self, run_id: str, requirement: dict[str, str]) -> dict[str, Any]:
        provider = self.provider_factory()
        requirements_by_feature: dict[str, dict[str, Any]] = {}
        ambiguities: list[str] = []
        explicit_criteria = {
            criterion_id
            for line in requirement["text"].splitlines()
            if (criterion_id := self._criterion_id(line))
            and self._is_explicit_acceptance_criterion(line, requirement["text"])
        }
        for chunk in self._requirement_analysis_chunks(requirement["text"]):
            response = await provider.complete(
                AICompletionRequest(
                    run_id=run_id,
                    prompt=json.dumps({"source_id": requirement["source_id"], "text": chunk}, ensure_ascii=False),
                    system_instruction=(
                        "Analyze this part of a QA requirement. Return only the declared compact schema. "
                        "Group related criteria into at most four features. Keep expected_behavior to one short sentence and copy each criterion verbatim once. "
                        "List ambiguity rather than inventing details. A concrete acceptance criterion with a stated action and observable outcome is not ambiguous merely because a surrounding user story is broad. "
                        "Mark a criterion ambiguous only when it is internally conflicting or lacks information needed to distinguish plausible outcomes, and identify that missing detail. "
                        "Extract checks only for directly observable enabled/selected state or exact visible text. "
                        "For visible checks, use a literal target quoted in the criterion; do not infer targets. "
                        "Use when=after_action for results expected after interaction and size-specific conditions only when stated. "
                        "Copy the source criterion exactly into check.criterion. A page transition alone does not prove a business outcome."
                    ),
                    response_schema=RequirementAnalysis,
                    prompt_id="quality_discovery_requirements",
                    prompt_version="1",
                    temperature=0.1,
                    max_tokens=1600,
                    timeout_seconds=30,
                    thinking_mode=self._provider_thinking_mode(),
                    max_retries=0,
                )
            )
            compact = RequirementAnalysis.model_validate(response.structured_data or json.loads(response.content))
            await self._record_ai(
                run_id,
                {
                    "provider": response.provider,
                    "model": response.model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                },
            )
            for item in compact.requirements:
                signal = RequirementSignal.model_validate(item.model_dump(mode="json")).model_dump(mode="json")
                criteria = signal.get("acceptance_criteria") or []
                if criteria and all(self._criterion_id(criterion) in explicit_criteria for criterion in criteria):
                    signal["ambiguous"] = False
                key = signal["feature"].strip().casefold()
                existing = requirements_by_feature.get(key)
                if existing is None:
                    requirements_by_feature[key] = signal
                    continue
                existing["acceptance_criteria"] = list(
                    dict.fromkeys([*existing["acceptance_criteria"], *signal["acceptance_criteria"]])
                )
                checks = {json.dumps(check, sort_keys=True): check for check in existing["checks"]}
                checks.update({json.dumps(check, sort_keys=True): check for check in signal["checks"]})
                existing["checks"] = list(checks.values())[:8]
                existing["ambiguous"] = existing["ambiguous"] or signal["ambiguous"]
                if existing["risk"] == "unknown":
                    existing["risk"] = signal["risk"]
            ambiguities.extend(
                item
                for item in compact.ambiguities
                if self._criterion_id(item) not in explicit_criteria and item not in ambiguities
            )

        data = {"requirements": list(requirements_by_feature.values()), "ambiguities": ambiguities[:20]}
        for index, item in enumerate(data["requirements"], start=1):
            item["id"] = f"{requirement['source_id']}:REQ-{index:03d}"
            item["source_id"] = requirement["source_id"]
        structured = StructuredRequirementModel.model_validate(
            {
                "source_id": requirement["source_id"],
                "features": [
                    {key: value for key, value in item.items() if key != "checks"} for item in data["requirements"]
                ],
                "ambiguities": data["ambiguities"],
            }
        )
        result = {
            "requirements": data["requirements"],
            "requirement_model": structured.model_dump(mode="json"),
            "ambiguities": data["ambiguities"],
        }
        await self._event(run_id, "requirement.analyzed", f"已结构化 {len(data['requirements'])} 个需求点。")
        return result

    @staticmethod
    def _criterion_id(value: str) -> str | None:
        match = re.match(r"\s*(AC[-_]?\d+)\s*:", str(value), re.I)
        return re.sub(r"[-_]", "", match.group(1)).casefold() if match else None

    @staticmethod
    def _is_explicit_acceptance_criterion(criterion: str, requirement_text: str = "") -> bool:
        text = criterion.casefold()
        empty_state_is_explicit = (
            re.search(r"无匹配|没有匹配|no\s+matches?", text, re.I)
            and re.search(r"明确空状态|清晰空状态|空状态|empty\s+state", text, re.I)
            and re.search(r"无商品卡片|不显示商品卡片|no\s+product\s+cards?", text, re.I)
        )
        if empty_state_is_explicit:
            return True

        same_variant_repeat_is_explicit = (
            re.search(r"重复|再次|again|repeatedly|twice", text, re.I)
            and re.search(r"相同|同一|same", text, re.I)
            and re.search(r"规格|variant|sku", text, re.I)
            and re.search(r"合并|merge", text, re.I)
            and re.search(r"数量|件数|quantity|count", text, re.I)
            and re.search(r"重新计算|重算|recalculat", text, re.I)
            and re.search(r"金额|总价|价格|amount|total|price", text, re.I)
            and re.search(
                r"价格\s*乘\s*数量|单价.{0,12}数量|price\s*(?:[×x*]|times)\s*(?:the\s+)?(?:quantity|qty)|"
                r"price.{0,24}(?:quantity|qty)",
                requirement_text,
                re.I,
            )
        )
        return bool(same_variant_repeat_is_explicit)

    async def _plan_next(
        self,
        run_id: str,
        row: QualityDiscoveryRunORM,
        snapshot,
        state: dict[str, Any],
        candidates: list[dict[str, Any]],
        requirements: list[dict[str, Any]],
    ) -> dict[str, Any]:
        provider = self.provider_factory()
        prompt = {
            "mode": row.mode,
            "requirements": requirements[:20],
            "observation": {
                "url": self._safe_url(snapshot.url),
                "title": self._safe_title(snapshot.title),
                "visible_text": SensitiveRedactor.redact_text(snapshot.text[:5000]),
                "accessibility_tree": SensitiveRedactor.redact_text(snapshot.accessibility_tree[:8000]),
                "controls": state["controls"][:40],
                "network": self._network_summary(snapshot.network),
                "state_id": state["state_id"],
            },
            "candidates": [
                {
                    key: candidate.get(key)
                    for key in ("candidate_id", "action_type", "target_id", "target", "expected_effect")
                }
                for candidate in candidates
            ],
            "requested_output": "Return page_type, evidence-grounded feature signals, concise exploration goals linked to requirements when possible, and safe candidate_ids only.",
            "rule": "Return only candidate_ids supplied above. A feature signal must cite a visible target_id or exact visible evidence_text.",
        }
        response = await provider.complete(
            AICompletionRequest(
                run_id=run_id,
                prompt=json.dumps(prompt, ensure_ascii=False, separators=(",", ":")),
                system_instruction=(
                    "You are the page-understanding and exploration-planning component of a QA discovery workflow. "
                    "AI proposes; Jev makes the action choice; the browser service executes only its returned choice. "
                    "Return concise exploration goals, preferring requirement-linked and high-risk behavior not yet covered by this graph. "
                    "Report only capabilities supported by the current page. Never invent selectors or IDs. "
                    "Never propose payment, checkout, order placement, account changes, submission of arbitrary forms, deletion, or external navigation. "
                    "Return a compact structured plan and no chain of thought."
                ),
                response_schema=DiscoveryPlan,
                prompt_id="quality_discovery_planning",
                prompt_version="1",
                temperature=0.1,
                max_tokens=1800,
                timeout_seconds=20,
                thinking_mode=self._provider_thinking_mode(),
                max_retries=0,
            )
        )
        plan = DiscoveryPlan.model_validate(response.structured_data or json.loads(response.content)).model_dump(
            mode="json"
        )
        plan["_usage"] = {
            "provider": response.provider,
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        }
        return plan

    async def _execute_candidate(
        self,
        run_id: str,
        session_id: str,
        state: dict[str, Any],
        candidate: dict[str, Any],
        *,
        decision_id: str | None = None,
    ) -> None:
        action_type = candidate["action_type"]
        locator = candidate.get("locator") or {"kind": "page", "value": ""}
        event_action = candidate.get("operation") or {
            "navigate": "click",
            "search": "press",
            "filter": "click",
            "scroll": "scroll",
            "back": "click",
        }.get(action_type, action_type)
        verified = True
        if action_type not in {"scroll", "back"}:
            verification = await self.browser_runtime.verify_locator(session_id, locator, {"action": event_action})
            verified = bool(verification.get("verified"))
        action_record = {
            "candidate_id": candidate["candidate_id"],
            "from_state_id": state["state_id"],
            "target_id": candidate.get("target_id"),
            "action_type": action_type,
            "target": candidate["target"],
            "expected_effect": candidate["expected_effect"],
            "selected_value": candidate.get("value") if action_type == "select" else None,
            "search_value": candidate.get("value") if action_type == "search" else None,
            "cart_variant_key": candidate.get("cart_variant_key")
            if self._is_cart_mutation_label(candidate["target"])
            else None,
            "jev_choice": candidate["candidate_id"],
            "jev_decision_id": decision_id,
            "status": "STARTED" if verified else "TARGET_NOT_VERIFIED",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._mark_attempted(run_id, state["fingerprint"], candidate["candidate_id"])
        if not verified:
            action_record["status"] = "FAILED"
            action_record["error"] = "Observed target was no longer uniquely visible and enabled."
            await self._append_action(run_id, action_record)
            await self._record_frontier(run_id, state["state_id"], [candidate], "FAILED", action_record["error"])
            await self._event(run_id, "action.failed", f"目标验证失败：{candidate['target']}")
            return
        await self._event(
            run_id,
            "action.started",
            f"正在执行：{candidate['action_type']} {candidate['target']}",
            {"candidate_id": candidate["candidate_id"]},
        )
        try:
            if action_type == "back":
                result = await self.browser_runtime.navigate(session_id, candidate["value"], timeout_ms=10_000)
            elif action_type == "navigate":
                result = await self.browser_runtime.execute_action(
                    session_id, locator, {"type": "click", "timeout_ms": 10_000}
                )
            elif action_type == "fill":
                result = await self.browser_runtime.execute_action(
                    session_id, locator, {"type": "fill", "value": candidate.get("value", ""), "timeout_ms": 10_000}
                )
            elif action_type == "search":
                if candidate.get("operation") == "click":
                    result = await self.browser_runtime.execute_action(
                        session_id, locator, {"type": "click", "timeout_ms": 10_000}
                    )
                else:
                    await self.browser_runtime.execute_action(
                        session_id,
                        locator,
                        {"type": "fill", "value": candidate.get("value", "qa sample"), "timeout_ms": 10_000},
                    )
                    result = await self.browser_runtime.execute_action(
                        session_id, locator, {"type": "press", "value": "Enter", "timeout_ms": 10_000}
                    )
            elif action_type == "select":
                result = await self.browser_runtime.execute_action(
                    session_id, locator, {"type": "select", "value": candidate.get("value", ""), "timeout_ms": 10_000}
                )
            elif action_type == "press":
                result = await self.browser_runtime.execute_action(
                    session_id,
                    locator,
                    {"type": "press", "value": candidate.get("value", "Enter"), "timeout_ms": 10_000},
                )
            else:
                result = await self.browser_runtime.execute_action(
                    session_id, locator, {"type": action_type, "value": candidate.get("value"), "timeout_ms": 10_000}
                )
            action_record["status"] = "EXECUTED"
            action_record["result"] = str(result)[:160] if result is not None else None
            page = await self.browser_runtime.get_page(session_id)
            action_record["url_after"] = self._safe_url(page.url)
            current_run = await self.get(run_id)
            if current_run and not self._host_allowed(page.url, self._allowed_hosts(current_run)):
                action_record["status"] = "BLOCKED_BY_DOMAIN_POLICY"
                action_record["finished_at"] = datetime.now(timezone.utc).isoformat()
                await self._append_action(run_id, action_record)
                raise DiscoveryBlocked("Action navigated outside the start domain and allowed domain list.")
            action_record["finished_at"] = datetime.now(timezone.utc).isoformat()
            await self._append_action(run_id, action_record)
            await self._record_frontier(
                run_id, state["state_id"], [candidate], "EXECUTED", "浏览器动作已执行，等待状态观察。"
            )
            await self._event(run_id, "action.completed", f"已执行：{candidate['target']}")
            # Re-observe without a second screenshot to verify a real state transition.
            after = await self.browser_runtime.snapshot(session_id, include_screenshot=False)
            after_controls = self._safe_controls(after.controls)
            after_scroll = await page.evaluate(
                "() => ({y: Math.round(window.scrollY), height: document.documentElement.scrollHeight, viewport: window.innerHeight})"
            )
            _after_state_id, after_fingerprint = self._state_fingerprint(after, after_controls, after_scroll)
            changed = after_fingerprint != state["fingerprint"]
            action_record["state_changed"] = changed
            action_record["to_fingerprint"] = after_fingerprint
            await self._replace_action(run_id, action_record)
            await self._link_feature_evidence(run_id, state, candidate, changed)
            await self._append_edge(run_id, state["state_id"], after_fingerprint, candidate)
            await self._event(
                run_id,
                "action.verified" if changed else "action.no_state_change",
                "浏览器状态已变化。" if changed else "执行后未观察到页面状态变化。",
                {"candidate_id": candidate["candidate_id"], "state_changed": changed},
            )
        except DiscoveryBlocked:
            raise
        except Exception as error:
            action_record["status"] = "FAILED"
            action_record["error"] = self._safe_error(error, limit=240)
            action_record["finished_at"] = datetime.now(timezone.utc).isoformat()
            await self._append_action(run_id, action_record)
            await self._record_frontier(run_id, state["state_id"], [candidate], "FAILED", action_record["error"])
            await self._event(run_id, "action.failed", f"动作失败：{candidate['target']}")

    def _candidate_actions(
        self,
        state: dict[str, Any],
        allowed_hosts: set[str],
        limit: int,
        *,
        depth_limited: bool = False,
        allow_cart_mutation: bool = False,
        skip_empty_cart_revisit: bool = False,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        state_id = state["state_id"]
        has_search_input = any(
            control.get("tag") == "input"
            and str(control.get("type") or "").lower() in {"search", "text"}
            and re.search(
                r"search|查询|搜索",
                str(control.get("name") or control.get("placeholder") or ""),
                re.I,
            )
            for control in state["controls"]
        )
        cart_view_open = bool(
            re.search(
                r"shopping cart|your cart is empty|购物车为空|购物车.*空",
                f"{state.get('title', '')} {state.get('main_content', '')}",
                re.I,
            )
        )
        for control in state["controls"]:
            if depth_limited:
                break
            if len(output) >= limit:
                break
            name = str(control.get("name") or control.get("placeholder") or control.get("href") or "").strip()
            if not name:
                continue
            if not control.get("enabled", True):
                continue
            tag = str(control.get("tag") or "")
            role = str(control.get("role") or "")
            href = str(control.get("href") or "")
            input_type = str(control.get("type") or "").lower()
            if control.get("has_query") or control.get("has_credentials") or self._url_has_secret_query(href):
                continue
            href_parts = urlsplit(href)
            relative_href = bool(href) and not href_parts.scheme and not href_parts.netloc
            if href and not relative_href and not self._host_allowed(href, allowed_hosts):
                continue
            cart_mutation = self._is_cart_mutation_label(name)
            if cart_mutation and not allow_cart_mutation:
                continue
            if re.search(
                r"checkout|payment|purchase|place.?order|delete|remove|logout|sign.?out|account.?settings|支付|付款|结账|下单|删除|注销|退出登录",
                name,
                re.I,
            ):
                continue
            locator = self._locator_for_control(control)
            if locator is None:
                continue
            action_type = "click"
            safe_kind = classify_browser_action("click", name=name, tag=tag, href=href, input_type=input_type)
            if cart_mutation and allow_cart_mutation:
                safe_kind = "SAFE_INTERACTION"
            if tag == "select" and re.search(r"filter|筛选|sort|排序|color|colour|size|颜色|尺码", name, re.I):
                action_type = "select"
                safe_kind = "SAFE_INTERACTION"
            elif re.search(r"search|查询|搜索", name, re.I) and tag == "input" and input_type in {"search", "text"}:
                action_type = "search"
                safe_kind = "SAFE_INTERACTION"
            elif tag == "a" and re.search(r"search|查询|搜索", name, re.I):
                action_type = "click"
            elif tag == "button" and not has_search_input and re.search(r"search|查询|搜索", name, re.I):
                action_type = "click"
            elif re.search(r"search|查询|搜索|filter|筛选|sort|排序", name, re.I):
                action_type = "search" if re.search(r"search|查询|搜索", name, re.I) else "filter"
                safe_kind = (
                    "SAFE_INTERACTION"
                    if action_type == "search"
                    else classify_browser_action(action_type, name=name, tag=tag, href=href, input_type=input_type)
                )
            if action_type == "search" and tag != "input" and has_search_input:
                continue
            value = self._safe_search_value(state) if action_type == "search" else self._safe_select_value(control)
            if action_type == "select" and not value:
                continue
            cart_view_button = action_type == "click" and bool(
                re.fullmatch(
                    r"(?:shopping\s+)?(?:cart|bag|basket)(?:\s*\(\s*\d+\s*\))?",
                    name,
                    re.I,
                )
            )
            if (cart_view_open or skip_empty_cart_revisit) and cart_view_button:
                continue
            if action_type == "click" and re.search(
                r"back to\s+(?:products|shop|catalog|results)|continue shopping|"
                r"return to\s+(?:products|shop|catalog|results)|继续购物|返回(?:商品|产品|列表|搜索)",
                name,
                re.I,
            ):
                safe_kind = "SAFE_INTERACTION"
            if cart_view_button:
                # Opening the cart view is read-only; add/remove/checkout labels are blocked above.
                safe_kind = "READ_ONLY"
            if safe_kind not in {"READ_ONLY", "SAFE_INTERACTION"}:
                continue
            candidate_id = self._candidate_id(state_id, action_type, str(control.get("id") or control.get("index")))
            output.append(
                {
                    "candidate_id": candidate_id,
                    "action_type": action_type,
                    "target_id": f"el_{control.get('index', 0)}",
                    "target_role": role,
                    "target_tag": tag,
                    "target": name[:140],
                    "expected_effect": self._candidate_expected_effect(action_type, name, control),
                    "locator": locator,
                    "value": value,
                    "operation": "click"
                    if action_type == "search" and not (tag == "input" and input_type in {"search", "text"})
                    else None,
                    "href": href,
                    "risk": safe_kind,
                    "cart_variant_key": self._cart_variant_key(state) if cart_mutation else None,
                }
            )
        if (
            not depth_limited
            and state.get("scroll", {}).get("height", 0) > state.get("scroll", {}).get("viewport", 0)
            and len(output) < limit
        ):
            candidate_id = self._candidate_id(state_id, "scroll", "down")
            output.append(
                {
                    "candidate_id": candidate_id,
                    "action_type": "scroll",
                    "target_id": None,
                    "target": "向下滚动",
                    "expected_effect": "观察当前页面下方的功能和控件。",
                    "locator": {"kind": "page", "value": ""},
                    "value": "down",
                    "risk": "READ_ONLY",
                }
            )
        return output

    @classmethod
    def _candidate_expected_effect(cls, action_type: str, name: str, control: dict[str, Any]) -> str:
        label = name[:80].strip()
        if cls._is_cart_mutation_label(label):
            return "将当前商品和已选规格加入购物车，再检查商品条目、数量与金额是否符合需求。"
        if action_type == "search":
            return "提交安全搜索词，观察匹配商品列表或无匹配空状态。"
        if action_type == "filter":
            return f"应用“{label}”筛选，观察商品列表和筛选状态变化。"
        if action_type == "select":
            return f"选择一个可用的“{label}”选项，核验控件选中状态。"
        if re.search(r"cart|bag|basket|购物车|购物袋", label, re.I):
            return "打开购物车，检查商品条目、数量和金额。"
        if re.search(
            r"back to\s+(?:products|shop|catalog|results)|continue shopping|"
            r"return to\s+(?:products|shop|catalog|results)|继续购物|返回(?:商品|产品|列表|搜索)",
            label,
            re.I,
        ):
            return "返回商品列表，观察商品卡片和搜索控件是否恢复。"
        if re.search(r"view|details|product|商品|详情", label, re.I):
            return f"打开“{label}”对应的商品详情，检查名称、价格和规格控件。"
        if control.get("href") or control.get("tag") == "a":
            return f"打开站内链接“{label}”，检查目标页面标题、内容或状态。"
        return f"触发“{label}”，观察相关区域的内容、提示或控件状态变化。"

    def _blocked_candidates(
        self,
        state: dict[str, Any],
        allowed_hosts: set[str],
        *,
        allow_cart_mutation: bool = False,
    ) -> list[dict[str, Any]]:
        blocked = []
        dangerous = re.compile(
            r"checkout|payment|purchase|place.?order|delete|remove|logout|sign.?out|account.?settings|submit|支付|付款|结账|下单|删除|注销|退出登录|提交",
            re.I,
        )
        for control in state.get("controls", []):
            name = str(control.get("name") or control.get("href") or "").strip()
            href = str(control.get("href") or "")
            outside = bool(control.get("has_query") or control.get("has_credentials"))
            if href:
                parsed = urlsplit(href)
                if parsed.scheme or parsed.netloc:
                    outside = outside or not self._host_allowed(href, allowed_hosts)
                elif parsed.query or parsed.fragment:
                    outside = True
            cart_blocked = self._is_cart_mutation_label(name) and not allow_cart_mutation
            if not name or not (dangerous.search(name) or cart_blocked or outside):
                continue
            blocked.append(
                {
                    "candidate_id": self._candidate_id(state["state_id"], "blocked", str(control.get("index", 0))),
                    "target": name[:140],
                    "action_type": "click",
                }
            )
        return blocked

    @staticmethod
    def _is_cart_mutation_label(name: str) -> bool:
        return bool(re.search(r"add\s*[- ]?\s*to\s*[- ]?\s*(?:cart|bag)|加入购物车|添加到购物车", name, re.I))

    @staticmethod
    def _requirement_allows_cart_mutation(text: str) -> bool:
        return bool(
            re.search(
                r"add\b.{0,80}\b(?:to|into)\s+(?:the\s+)?(?:shopping\s+)?(?:cart|bag)|加入购物车|添加到购物车",
                text,
                re.I,
            )
        )

    @staticmethod
    def _requirement_allows_repeat_cart_mutation(text: str) -> bool:
        same_variant = re.search(
            r"(?:same|identical|same\s+selected)\b.{0,50}\b(?:variant|item|product|sku)\b|"
            r"\b(?:variant|item|product|sku)\b.{0,50}\b(?:same|identical)\b|"
            r"(?:相同|同一)(?:商品|产品)?(?:规格|款式|sku)|(?:重复|再次).{0,50}(?:加入|添加).{0,50}(?:相同|同一)",
            text,
            re.I,
        )
        quantity_merge = re.search(r"merge|combine|quantity|quantities|count|合并|数量|件数", text, re.I)
        return bool(same_variant and quantity_merge)

    @staticmethod
    def _has_observed_empty_cart(states: list[dict[str, Any]]) -> bool:
        return any(
            state.get("page_type") == "cart-empty"
            or bool(
                re.search(
                    r"your cart is empty|购物车为空|购物车.*空",
                    str(state.get("main_content") or ""),
                    re.I,
                )
            )
            for state in states
        )

    @staticmethod
    def _locator_for_control(control: dict[str, Any]) -> dict[str, Any] | None:
        role, name = control.get("role"), str(control.get("name") or "").strip()
        if role and name:
            return {"kind": "role", "value": role, "name": name, "exact": True}
        if control.get("test_id"):
            return {"kind": "test_id", "value": control["test_id"]}
        if control.get("id"):
            return {"kind": "id", "value": str(control["id"])}
        if control.get("href"):
            return {"kind": "css", "value": f"a[href={json.dumps(str(control['href']))}]"}
        if name and tag_is_text(control.get("tag")):
            return {"kind": "text", "value": name, "exact": True}
        return None

    @classmethod
    def _safe_controls(cls, controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for control in controls:
            if not control.get("visible"):
                continue
            name = SensitiveRedactor.redact_text(str(control.get("name") or ""))[:160]
            safe_filter = bool(re.search(r"filter|sort|color|colour|size|筛选|排序|颜色|尺码", name, re.I))
            href = str(control.get("href") or "")
            safe_href = cls._safe_url(href)
            try:
                href_parts = urlsplit(href)
                has_query = bool(href_parts.query or href_parts.fragment)
                has_credentials = bool(href_parts.username or href_parts.password)
            except ValueError:
                has_query = has_credentials = True
            result.append(
                {
                    "index": int(control.get("index", len(result))),
                    "tag": str(control.get("tag") or "")[:30],
                    "role": str(control.get("role") or "")[:30],
                    "name": name,
                    "type": str(control.get("type") or "")[:30],
                    "href": safe_href[:500],
                    "has_query": has_query,
                    "has_credentials": has_credentials,
                    "test_id": SensitiveRedactor.redact_text(str(control.get("test_id") or ""))[:120],
                    "id": SensitiveRedactor.redact_text(str(control.get("id") or ""))[:120],
                    "visible": True,
                    "enabled": bool(control.get("enabled", True)),
                    "selected": bool(control.get("selected", False)),
                    "checked": bool(control.get("checked", False)),
                    "selection_fingerprint": (
                        hashlib.sha256(str(control.get("value") or "").encode()).hexdigest()[:12]
                        if control.get("tag") == "select" and control.get("value")
                        else ""
                    ),
                    "value": (
                        SensitiveRedactor.redact_text(str(control.get("value") or ""))[:120]
                        if control.get("tag") == "select" and safe_filter
                        else ""
                    ),
                    "options": [
                        {
                            "value": SensitiveRedactor.redact_text(str(item.get("value") or ""))[:120],
                            "enabled": bool(item.get("enabled", True)),
                        }
                        for item in (
                            (control.get("options") or [])[:30]
                            if control.get("tag") == "select" and safe_filter
                            else []
                        )
                        if isinstance(item, dict)
                    ],
                }
            )
        return result

    @staticmethod
    def _safe_select_value(control: dict[str, Any]) -> str:
        current = str(control.get("value") or "")
        return next(
            (
                str(option.get("value") or "")
                for option in (control.get("options") or [])
                if option.get("enabled")
                and str(option.get("value") or "")
                and str(option.get("value") or "") != current
            ),
            "",
        )

    @staticmethod
    def _safe_search_value(state: dict[str, Any]) -> str:
        for control in state.get("controls", []):
            name = str(control.get("name") or "").strip()
            match = re.fullmatch(r"view\s+(.+)", name, re.I)
            if match and match.group(1).strip():
                return match.group(1).strip()[:100]
        return "qa sample"

    @classmethod
    def _search_value_for_goal(
        cls,
        state: dict[str, Any],
        plan: dict[str, Any],
        requirements: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        states: list[dict[str, Any]],
    ) -> str:
        active_goal = cls._active_goal_context(plan, requirements, actions, states) or {}
        goal_text = " ".join(
            str(active_goal.get(key) or "")
            for key in ("title", "feature", "rationale", "expected_behavior", "acceptance_criteria")
        )
        if re.search(r"no[-\s]+match|no[-\s]+result|empty\s+state|无匹配|无结果|空状态|未找到", goal_text, re.I):
            return "zzqa-no-matching-item"

        current_value = cls._safe_search_value(state)
        if current_value != "qa sample":
            if re.search(r"case\s*[- ]?insensitive|ignore\s+case|忽略大小写|不区分大小写", goal_text, re.I):
                return current_value.casefold()
            return current_value
        for previous_state in states:
            previous_value = cls._safe_search_value(previous_state)
            if previous_value != "qa sample":
                if re.search(r"case\s*[- ]?insensitive|ignore\s+case|忽略大小写|不区分大小写", goal_text, re.I):
                    return previous_value.casefold()
                return previous_value
        return next(
            (
                str(action.get("search_value"))
                for action in reversed(actions)
                if action.get("action_type") == "search"
                and action.get("status") == "EXECUTED"
                and action.get("search_value")
                and action.get("search_value") != "zzqa-no-matching-item"
            ),
            current_value,
        )

    @staticmethod
    def _active_goal_context(
        plan: dict[str, Any],
        requirements: list[dict[str, Any]],
        actions: list[dict[str, Any]] | None = None,
        states: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        goals = plan.get("goals") or []
        if not goals:
            return None
        search_values = {
            str(action.get("search_value") or "").casefold()
            for action in (actions or [])
            if action.get("action_type") == "search" and action.get("status") == "EXECUTED"
        }
        for goal in goals:
            requirement_id = goal.get("requirement_id")
            requirement = next((item for item in requirements if item.get("id") == requirement_id), None)
            context = {
                key: goal.get(key)
                for key in ("title", "feature", "priority", "rationale", "requirement_id")
                if goal.get(key)
            }
            if requirement:
                context["expected_behavior"] = requirement.get("expected_behavior")
                context["acceptance_criteria"] = (requirement.get("acceptance_criteria") or [])[:5]
            goal_text = " ".join(
                str(context.get(key) or "")
                for key in ("title", "feature", "rationale", "expected_behavior", "acceptance_criteria")
            )
            is_no_match_goal = bool(
                re.search(r"no[-\s]+match|no[-\s]+result|empty\s+state|无匹配|无结果|空状态|未找到", goal_text, re.I)
            )
            if not re.search(r"search|搜索", goal_text, re.I) and not is_no_match_goal:
                return context
            if is_no_match_goal and "zzqa-no-matching-item" in search_values:
                continue
            if not is_no_match_goal and any(value and value != "zzqa-no-matching-item" for value in search_values):
                continue
            return context
        return None

    @staticmethod
    def _filter_repeated_search_candidates(
        candidates: list[dict[str, Any]], actions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        executed_searches = [
            action for action in actions if action.get("action_type") == "search" and action.get("status") == "EXECUTED"
        ]
        if not executed_searches:
            return candidates
        searched_values = {str(action.get("search_value") or "").casefold() for action in executed_searches}
        if "" in searched_values:
            return [candidate for candidate in candidates if candidate.get("action_type") != "search"]
        return [
            candidate
            for candidate in candidates
            if candidate.get("action_type") != "search"
            or str(candidate.get("value") or "").casefold() not in searched_values
        ]

    @classmethod
    def _filter_repeated_select_candidates(
        cls,
        candidates: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        states: list[dict[str, Any]],
        state: dict[str, Any],
        *,
        allow_repeat_same_variant: bool = False,
    ) -> list[dict[str, Any]]:
        state_by_id = {item.get("state_id"): item for item in states}
        current_scope = cls._product_scope_key(state)
        previous_selections = [
            action
            for action in actions
            if action.get("action_type") == "select"
            and action.get("status") == "EXECUTED"
            and action.get("from_state_id") in state_by_id
            and cls._product_scope_key(state_by_id[action["from_state_id"]]) == current_scope
        ]
        selected_targets = {str(action.get("target") or "").casefold() for action in previous_selections}
        repeat_add_count = sum(
            action.get("status") == "EXECUTED" and cls._is_cart_mutation_label(str(action.get("target") or ""))
            for action in actions
        )
        return [
            candidate
            for candidate in candidates
            if candidate.get("action_type") != "select"
            or str(candidate.get("target") or "").casefold() not in selected_targets
            or (
                allow_repeat_same_variant
                and repeat_add_count == 1
                and any(
                    str(action.get("target") or "").casefold() == str(candidate.get("target") or "").casefold()
                    and str(action.get("selected_value") or "").casefold()
                    == str(candidate.get("value") or "").casefold()
                    for action in previous_selections
                )
            )
        ]

    @staticmethod
    def _product_scope_key(state: dict[str, Any]) -> str:
        url = str(state.get("url") or "").casefold()
        landmarks = str(state.get("landmarks") or "")
        heading = re.search(r'heading\s+"([^"\r\n]+)"\s+\[level=1\]', landmarks, re.I)
        product = heading.group(1).strip().casefold() if heading else ""
        return hashlib.sha256(f"{url}\n{product}".encode()).hexdigest()[:20]

    @classmethod
    def _cart_variant_key(cls, state: dict[str, Any]) -> str:
        variants = [
            (
                str(control.get("name") or "").casefold(),
                str(control.get("selection_fingerprint") or "")
                or hashlib.sha256(str(control.get("value") or "").casefold().encode()).hexdigest()[:12],
            )
            for control in state.get("controls", [])
            if control.get("tag") == "select"
            and re.search(
                r"color|colour|size|variant|option|material|颜色|尺码|规格",
                str(control.get("name") or ""),
                re.I,
            )
        ]
        key = json.dumps([cls._product_scope_key(state), variants], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(key.encode()).hexdigest()[:24]

    @classmethod
    def _prioritize_variant_actions_before_cart(
        cls,
        candidates: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        states: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        cart_candidates = [
            candidate for candidate in candidates if cls._is_cart_mutation_label(str(candidate.get("target") or ""))
        ]
        if not cart_candidates:
            return candidates

        variant_controls = [
            control
            for control in state.get("controls", [])
            if control.get("tag") == "select"
            and re.search(
                r"color|colour|size|variant|option|material|颜色|尺码|规格",
                str(control.get("name") or ""),
                re.I,
            )
            and cls._safe_select_value(control)
        ]
        if not variant_controls:
            return candidates

        state_by_id = {item.get("state_id"): item for item in states}
        current_scope = cls._product_scope_key(state)
        selected_targets = {
            str(action.get("target") or "").casefold()
            for action in actions
            if action.get("action_type") == "select"
            and action.get("status") == "EXECUTED"
            and action.get("from_state_id") in state_by_id
            and cls._product_scope_key(state_by_id[action["from_state_id"]]) == current_scope
        }
        required_targets = {str(control.get("name") or "").casefold() for control in variant_controls}
        unresolved_targets = [target for target in required_targets if target not in selected_targets]
        if not unresolved_targets:
            return candidates
        next_target = next(
            str(control.get("name") or "").casefold()
            for control in variant_controls
            if str(control.get("name") or "").casefold() in unresolved_targets
        )
        return [
            candidate
            for candidate in candidates
            if candidate.get("action_type") == "select" and str(candidate.get("target") or "").casefold() == next_target
        ]

    @classmethod
    def _prioritize_cart_verification_after_add(
        cls,
        candidates: list[dict[str, Any]],
        state: dict[str, Any],
        actions: list[dict[str, Any]],
        states: list[dict[str, Any]],
        *,
        allow_repeat_same_variant: bool = False,
    ) -> list[dict[str, Any]]:
        successful_adds = [
            action
            for action in actions
            if action.get("status") == "EXECUTED" and cls._is_cart_mutation_label(str(action.get("target") or ""))
        ]
        if not successful_adds:
            return candidates

        if allow_repeat_same_variant and len(successful_adds) == 1:
            previous_variant_key = successful_adds[0].get("cart_variant_key")
            same_variant_adds = [
                candidate
                for candidate in candidates
                if cls._is_cart_mutation_label(str(candidate.get("target") or ""))
                and previous_variant_key
                and candidate.get("cart_variant_key") == previous_variant_key
            ]
            if same_variant_adds:
                return same_variant_adds

        cart_inspected = any(
            (
                str(item.get("page_type") or "").casefold() in {"cart", "shopping_cart", "cart_populated"}
                or re.search(
                    r"shopping cart|购物车",
                    f"{item.get('title') or ''} {item.get('main_content') or ''}",
                    re.I,
                )
            )
            and bool(re.search(r"total\s*:\s*\$\s*\d", str(item.get("main_content") or ""), re.I))
            and not bool(
                re.search(r"your cart is empty|购物车为空|购物车.*空", str(item.get("main_content") or ""), re.I)
            )
            and bool(successful_adds[-1].get("finished_at"))
            and bool(item.get("observed_at"))
            and datetime.fromisoformat(str(item["observed_at"]).replace("Z", "+00:00"))
            >= datetime.fromisoformat(str(successful_adds[-1]["finished_at"]).replace("Z", "+00:00"))
            for item in states
        )
        if not cart_inspected:
            cart_views = [
                candidate
                for candidate in candidates
                if candidate.get("action_type") == "click"
                and re.fullmatch(
                    r"(?:shopping\s+)?(?:cart|bag|basket)(?:\s*\(\s*\d+\s*\))?",
                    str(candidate.get("target") or ""),
                    re.I,
                )
            ]
            if cart_views:
                return cart_views
        return [
            candidate for candidate in candidates if not cls._is_cart_mutation_label(str(candidate.get("target") or ""))
        ]

    @classmethod
    def _back_candidate(
        cls, result: dict[str, Any], state: dict[str, Any], allowed_hosts: set[str]
    ) -> dict[str, Any] | None:
        state_id = state["state_id"]
        states = {item.get("state_id"): item for item in result.get("states", [])}
        for edge in reversed(result.get("edges", [])):
            if edge.get("to_state_id") != state_id:
                continue
            parent = states.get(edge.get("from_state_id"))
            if not parent or parent.get("url") == state.get("url") or not parent.get("url_navigable"):
                continue
            destination = str(parent.get("url") or "")
            if not cls._host_allowed(destination, allowed_hosts):
                continue
            return {
                "candidate_id": cls._candidate_id(state_id, "back", "history"),
                "action_type": "back",
                "target_id": None,
                "target": "返回已观察的站内页面",
                "expected_effect": "导航回已观察的站内页面，检查其他未探索路径。",
                "locator": {"kind": "page", "value": ""},
                "value": destination,
                "risk": "READ_ONLY",
            }
        return None

    @staticmethod
    def _url_is_navigable(value: str) -> bool:
        try:
            parts = urlsplit(value)
            return bool(
                parts.scheme in {"http", "https"}
                and parts.hostname
                and not parts.username
                and not parts.password
                and not parts.query
                and not parts.fragment
            )
        except ValueError:
            return False

    @staticmethod
    def _candidate_id(state_id: str, action: str, target: str) -> str:
        digest = hashlib.sha256(f"{state_id}:{action}:{target}".encode()).hexdigest()[:12]
        return f"cand_{digest}"

    @classmethod
    def _state_fingerprint(cls, snapshot, controls: list[dict[str, Any]], scroll: dict[str, Any]) -> tuple[str, str]:
        normalized_url = cls._safe_url(snapshot.url)
        descriptor = {
            "url": normalized_url,
            "title": cls._safe_title(snapshot.title)[:180],
            "text": SensitiveRedactor.redact_text(re.sub(r"\s+", " ", snapshot.text or ""))[:1800],
            "scroll": scroll,
            "controls": [
                {
                    key: item.get(key)
                    for key in ("tag", "role", "name", "href", "value", "selected", "checked", "selection_fingerprint")
                }
                for item in controls[:60]
            ],
        }
        fingerprint = hashlib.sha256(json.dumps(descriptor, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[
            :24
        ]
        return f"state_{fingerprint[:16]}", fingerprint

    @classmethod
    def _state_record(cls, snapshot, controls, scroll, state_id, fingerprint) -> dict[str, Any]:
        text = re.sub(r"\s+", " ", snapshot.text or "").strip()
        evidence_chars = cls._get_config().discovery.max_evidence_chars
        content_limit = evidence_chars // 2
        return {
            "state_id": state_id,
            "fingerprint": fingerprint,
            "url": cls._safe_url(snapshot.url)[:2048],
            "url_navigable": cls._url_is_navigable(snapshot.url),
            "title": cls._safe_title(snapshot.title)[:200],
            "page_type": "unknown",
            "visible_controls": len(controls),
            "controls": controls,
            "main_content": SensitiveRedactor.redact_text(text)[:content_limit],
            "landmarks": SensitiveRedactor.redact_text(snapshot.accessibility_tree or "")[
                : evidence_chars - content_limit
            ],
            "scroll": scroll,
            "network": cls._network_summary(snapshot.network),
            "console_errors": [
                {key: SensitiveRedactor.redact_text(str(value))[:500] for key, value in item.items()}
                for item in snapshot.console
                if item.get("type") == "error"
            ][:20],
            "evidence_id": None,
            "depth": 0,
            "attempted_candidate_ids": [],
            "skipped_candidate_ids": [],
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _network_summary(network: list[dict[str, Any]]) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        failures = 0
        for item in network[-50:]:
            status = item.get("status")
            if isinstance(status, int):
                bucket = f"{status // 100}xx"
                statuses[bucket] = statuses.get(bucket, 0) + 1
                if status >= 400:
                    failures += 1
            if item.get("failed"):
                failures += 1
        return {"responses": statuses, "failures": failures, "sample_count": min(len(network), 50)}

    @classmethod
    def _allowed_hosts(cls, row: QualityDiscoveryRunORM) -> set[str]:
        initial = (urlsplit(row.start_url).hostname or "").lower().rstrip(".")
        configured = cls._get_config().discovery.allowed_domains
        return {initial, *(host.lower().rstrip(".") for host in [*(row.allowed_domains or []), *configured])}

    @classmethod
    def _find_similar_state(
        cls,
        result: dict[str, Any],
        snapshot,
        controls: list[dict[str, Any]],
        threshold: float,
    ) -> dict[str, Any] | None:
        current_selects = {
            item.get("name"): item.get("selection_fingerprint")
            for item in controls
            if item.get("tag") == "select" and item.get("selection_fingerprint")
        }
        best = None
        for state in result.get("states", []):
            old_controls = state.get("controls", [])
            old_selects = {
                item.get("name"): item.get("selection_fingerprint")
                for item in old_controls
                if item.get("tag") == "select" and item.get("selection_fingerprint")
            }
            if current_selects != old_selects:
                continue
            score = cls._state_similarity(
                state,
                {
                    "url": cls._safe_url(snapshot.url),
                    "title": cls._safe_title(snapshot.title),
                    "controls": controls,
                },
            )
            if score >= threshold and (best is None or score > best["score"]):
                best = {"state_id": state["state_id"], "score": round(score, 3)}
        return best

    @classmethod
    def _state_similarity(cls, left: dict[str, Any], right: dict[str, Any]) -> float:
        def template(value: str) -> str:
            path = urlsplit(value).path.casefold()
            path = re.sub(r"(?<![a-z])[0-9a-f]{8}-[0-9a-f-]{20,}(?![a-z])", ":id", path)
            path = re.sub(r"(?<=/)[0-9]+(?=/|$)", ":id", path)
            return path.rstrip("/") or "/"

        left_url, right_url = template(str(left.get("url") or "")), template(str(right.get("url") or ""))
        if left_url != right_url:
            return 0.0
        left_controls = {
            (
                item.get("tag"),
                item.get("role"),
                item.get("type"),
                str(item.get("name") or "").casefold(),
                item.get("checked"),
                item.get("selected"),
            )
            for item in left.get("controls", [])
        }
        right_controls = {
            (
                item.get("tag"),
                item.get("role"),
                item.get("type"),
                str(item.get("name") or "").casefold(),
                item.get("checked"),
                item.get("selected"),
            )
            for item in right.get("controls", [])
        }
        control_score = (
            len(left_controls & right_controls) / len(left_controls | right_controls)
            if left_controls | right_controls
            else 1.0
        )
        title_score = cls._similarity(str(left.get("title") or ""), str(right.get("title") or ""))
        return 0.75 * control_score + 0.20 * title_score + 0.05

    @staticmethod
    def _host_allowed(url: str, hosts: set[str]) -> bool:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        host = parsed.hostname.lower().rstrip(".")
        return host in hosts

    @staticmethod
    def _safe_url(url: str) -> str:
        try:
            parts = urlsplit(url)
            hostname = parts.hostname or ""
            if ":" in hostname and not hostname.startswith("["):
                hostname = f"[{hostname}]"
            port = f":{parts.port}" if parts.port is not None else ""
        except ValueError:
            return ""
        netloc = f"{hostname}{port}" if parts.netloc else ""
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))

    @staticmethod
    def _safe_title(title: str) -> str:
        safe = SensitiveRedactor.redact_text(str(title or ""))
        protocol_relative_url = re.compile(r"(?<![A-Za-z0-9:])//(?P<path>[^\s?#]+)(?:\?[^\s#]*)?(?:#[^\s]*)?")
        safe = protocol_relative_url.sub(lambda match: f"//{match.group('path')}", safe)
        relative_url = re.compile(
            r"(?<![A-Za-z0-9/:])(?P<path>/?[A-Za-z0-9._~!$&'()*+,;=:@%-]+(?:/[A-Za-z0-9._~!$&'()*+,;=:@%-]+)*)(?:\?[^\s#]*|#[^\s#]*)+"
        )
        safe = relative_url.sub(lambda match: match.group("path"), safe)
        safe = re.sub(r"(?<!\S)[?#][^\s]*", "", safe)
        return safe.strip()[:500]

    @staticmethod
    def _url_has_secret_query(url: str) -> bool:
        parsed = urlsplit(url)
        return bool(parsed.query or parsed.fragment)

    @classmethod
    def _safe_error(cls, error: Exception, limit: int = 500) -> str:
        message = SensitiveRedactor.redact_text(str(error))
        message = re.sub(
            r"https?://[^\s\"'<>]+",
            lambda match: cls._safe_url(match.group(0)),
            message,
        )
        return f"{type(error).__name__}: {message[:limit]}"

    @staticmethod
    def _resume_url(result: dict[str, Any], start_url: str) -> str:
        states = result.get("states") or []
        return str(states[-1].get("url") or start_url) if states else start_url

    async def _save_screenshot(self, run_id: str, state_id: str, screenshot: bytes) -> str | None:
        storage = ArtifactStorageService(ArtifactRepository(self.session_factory))
        saved = await storage.save_artifact(
            filename=f"{run_id}_{state_id}.png",
            content=screenshot,
            content_type="image/png",
        )
        return saved.artifact_id

    async def _save_state_evidence(self, run_id: str, state_id: str, state: dict[str, Any]) -> str | None:
        evidence = {
            key: state.get(key)
            for key in (
                "url",
                "title",
                "page_type",
                "visible_controls",
                "controls",
                "main_content",
                "landmarks",
                "scroll",
                "network",
                "console_errors",
            )
        }
        content = json.dumps(evidence, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        storage = ArtifactStorageService(ArtifactRepository(self.session_factory))
        saved = await storage.save_artifact(
            filename=f"{run_id}_{state_id}_evidence.json",
            content=content,
            content_type="application/json",
        )
        return saved.artifact_id


def tag_is_text(value: Any) -> bool:
    return value in {"button", "a", "span", "div", "label"}
