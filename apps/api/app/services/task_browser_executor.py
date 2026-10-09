from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from project_model.models import DecisionOption, DecisionRequest
from project_model.task_models import EvidenceType, TaskStatus
from qa_core.ai.browser_safety import classify_browser_action
from qa_core.ai.models import BrowserActionCandidate, BrowserAgentPlan
from qa_core.ai.trace import make_trace_event
from qa_core.failure.redactor import SensitiveRedactor

from app.domain.task_records import TaskRecord as TaskExecutionRecord
from app.services.task_ai_service import TaskAIService
from app.services.task_decision_service import TaskDecisionService
from app.services.task_errors import TaskBlocked
from app.services.task_execution_ports import TaskExecutionPorts
from app.settings import get_config

logger = logging.getLogger("app.task_browser_executor")


class TaskBrowserExecutor:
    """Own browser task policy, page exploration and browser action execution."""

    def __init__(
        self,
        context: TaskExecutionPorts,
        *,
        ai_service: TaskAIService,
        decision_service: TaskDecisionService,
    ) -> None:
        self.context = context
        self.browser_runtime = context.browser_runtime
        self.ai_service = ai_service
        self.decision_service = decision_service

    async def _observe_browser_page(
        self,
        page: Any,
        network: dict[str, int],
        *,
        waited_loading_states: set[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(3):
            try:
                return await self._observe_browser_page_once(
                    page,
                    network,
                    waited_loading_states=waited_loading_states,
                )
            except Exception as error:
                message = str(error).casefold()
                navigation_race = any(
                    marker in message
                    for marker in (
                        "execution context was destroyed",
                        "frame was detached",
                        "navigation interrupted",
                        "navigation in progress",
                        "cannot find context with specified id",
                    )
                )
                if not navigation_race or attempt == 2:
                    raise
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
                await page.wait_for_timeout(100 * (attempt + 1))
        raise RuntimeError("Browser page observation did not stabilize.")

    async def _observe_browser_page_once(
        self,
        page: Any,
        network: dict[str, int],
        *,
        waited_loading_states: set[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        try:
            statuses = page.locator('[role="status"]')
            for index in range(min(await statuses.count(), 5)):
                status = statuses.nth(index)
                status_text = await status.inner_text(timeout=500)
                state_key = (page.url, status_text.casefold())
                if re.search(r"\bloading\b|正在加载|加载中", status_text, re.I) and (
                    waited_loading_states is None or state_key not in waited_loading_states
                ):
                    if waited_loading_states is not None:
                        waited_loading_states.add(state_key)
                    await status.wait_for(state="hidden", timeout=2000)
                    break
        except Exception as error:
            if not self.browser_runtime.is_timeout_error(error):
                raise

        title = await page.title()
        url = page.url
        try:
            body = (await page.locator("body").inner_text(timeout=3000))[:8000]
        except Exception as error:
            if not self.browser_runtime.is_timeout_error(error):
                raise
            body = ""
        try:
            accessibility_tree = (await page.locator("body").aria_snapshot(timeout=3000))[:16000]
        except Exception:
            accessibility_tree = ""
        scroll_state = await page.evaluate(
            """() => ({
              scroll_y: Math.round(window.scrollY),
              scroll_height: document.documentElement.scrollHeight,
              viewport_height: window.innerHeight
            })"""
        )
        elements = await page.locator(
            "a[href],button,input:not([type=hidden]),textarea,select,[role=button],[role=link],[role=combobox],[role=option]"
        ).evaluate_all(
            r"""els => els.slice(0,100).map((el,index) => {
              const tag=el.tagName.toLowerCase(), type=(el.getAttribute('type') || (tag==='input' || (tag==='button' && el.form) ? el.type : '') || '').toLowerCase();
              const style=getComputedStyle(el), rect=el.getBoundingClientRect();
              const visible=style.visibility!=='hidden' && style.display!=='none' && rect.width>0 && rect.height>0;
              const role=el.getAttribute('role') || (tag==='a'?'link':tag==='button'?'button':tag==='select'?'combobox':['input','textarea'].includes(tag)?'textbox':null);
              const label=(el.labels?.length ? Array.from(el.labels).map(x=>x.innerText).join(' ') : '').trim().replace(/\s+/g,' ').slice(0,120);
              const name=(el.getAttribute('aria-label') || label || el.getAttribute('alt') || el.innerText || el.getAttribute('placeholder') || el.getAttribute('name') || '').trim().replace(/\s+/g,' ').slice(0,160);
              const safeInput=['search','text','number'].includes(type) || tag==='textarea';
              const value=tag==='select' ? (el.selectedOptions[0]?.textContent || '').trim().slice(0,100) : safeInput ? String(el.value || '').slice(0,120) : '';
              const form=el.form || null;
              const formAction=form ? (form.getAttribute('action') || form.action || '') : '';
              const options=tag==='select' ? Array.from(el.options).slice(0,30).map(o=>({value:o.value,label:(o.textContent||'').trim().slice(0,100),enabled:!o.disabled})) : [];
              return {
                id:`el_${index}`, tag, role, name, label, type,
                href:el instanceof HTMLAnchorElement ? el.href : (el.getAttribute('href') || ''),
                href_selector:(el.getAttribute('href') || ''),
                form_action:formAction,
                placeholder:(el.getAttribute('placeholder') || '').slice(0,120),
                test_id:(el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('data-qa') || '').slice(0,120),
                stable_id:(el.id || '').slice(0,120), value, options,
                visible, enabled:!el.disabled && el.getAttribute('aria-disabled')!=='true',
                selected:el.checked===true || el.getAttribute('aria-pressed')==='true' || el.getAttribute('aria-selected')==='true',
                expanded:el.getAttribute('aria-expanded'),
              };
            }).filter(el => el.visible)"""
        )
        safe_controls = [
            {
                **{key: value for key, value in item.items() if key != "href_selector"},
                "_href": item.get("href") or "",
                "_href_selector": item.get("href_selector") or "",
                "href": SensitiveRedactor.redact_url(str(item.get("href") or ""))[:500],
                "form_action": SensitiveRedactor.redact_url(str(item.get("form_action") or ""))[:500],
            }
            for item in elements
        ]
        state = {
            "url": SensitiveRedactor.redact_url(url)[:500],
            "title": title[:200],
            "text": body,
            "accessibility_tree": accessibility_tree,
            "elements": safe_controls,
            "network": dict(network),
            "scroll": scroll_state,
        }
        fingerprint = {
            "url": state["url"],
            "title": state["title"],
            "text": body[:1600],
            "scroll": scroll_state,
            "elements": [
                {key: item.get(key) for key in ("role", "name", "href", "value", "selected", "expanded")}
                for item in safe_controls[:50]
            ],
        }
        state["state_hash"] = hashlib.sha256(
            json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        state["cart"] = TaskBrowserExecutor._browser_cart_state(state)
        return state

    @staticmethod
    def _browser_cart_state(observation: dict[str, Any]) -> dict[str, Any]:
        text = str(observation.get("text") or "")
        controls = observation.get("elements") or []
        cart_control = next(
            (
                item
                for item in controls
                if re.search(r"cart|bag|basket|购物车|购物袋", str(item.get("name") or ""), re.I)
            ),
            {},
        )
        badge = str(cart_control.get("name") or "")
        count_match = re.search(r"\b(\d{1,3})\b", badge)
        confirmation_match = re.search(
            r"added to (?:your )?(?:cart|bag|basket)|added successfully|已(?:加入|添加到)购物车|已(?:加入|添加到)购物袋",
            text,
            re.I,
        )
        return {
            "badge_text": badge[:120],
            "badge_text_visible": bool(badge and badge.casefold() in text.casefold()),
            "count": int(count_match.group(1)) if count_match else None,
            "confirmation": bool(confirmation_match),
            "confirmation_text": confirmation_match.group(0)[:120] if confirmation_match else "",
        }

    @staticmethod
    def _browser_cart_verified(before: dict[str, Any], after: dict[str, Any]) -> bool:
        return bool(
            after.get("confirmation")
            and not before.get("confirmation")
            or before.get("count") is not None
            and after.get("count") is not None
            and after["count"] > before["count"]
        )

    @staticmethod
    def _browser_cart_intent(goal: str) -> bool:
        return bool(
            re.search(
                r"(?:add.{0,32}(?:to.{0,4})?(?:cart|bag|basket)|put.{0,24}(?:in|into).{0,8}(?:cart|bag|basket)|"
                r"(?:加入|放入|添加|加到|加进).{0,8}(?:购物车|购物袋|cart|bag|basket))",
                goal,
                re.I,
            )
        )

    @staticmethod
    def _browser_locator_variants(element: dict[str, Any]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        if element.get("role") and element.get("name"):
            values.append({"kind": "role", "value": element["role"], "name": element["name"], "exact": True})
        if element.get("test_id"):
            values.append({"kind": "test_id", "value": element["test_id"]})
        if element.get("label"):
            values.append({"kind": "label", "value": element["label"], "exact": True})
        if element.get("placeholder"):
            values.append({"kind": "placeholder", "value": element["placeholder"], "exact": True})
        if element.get("stable_id"):
            values.append({"kind": "id", "value": element["stable_id"]})
        if element.get("tag") in {"input", "textarea"}:
            selector = str(element["tag"])
            if element.get("type"):
                selector += f"[type={json.dumps(str(element['type']))}]"
            values.append({"kind": "css", "value": selector})
        if element.get("name"):
            values.append({"kind": "text", "value": element["name"], "exact": True})
        if (element.get("_href_selector") or element.get("href")) and element.get("tag") == "a":
            values.append(
                {"kind": "css", "value": f"a[href={json.dumps(element.get('_href_selector') or element['href'])}]"}
            )
        return values

    @staticmethod
    def _browser_human_verification_required(observation: dict[str, Any]) -> bool:
        url = urlparse(str(observation.get("url") or ""))
        text = " ".join((str(observation.get("title") or ""), str(observation.get("text") or "")))
        return bool(
            re.search(r"captcha|verification", url.path, re.I)
            or re.search(
                r"captcha|security check|verify you are human|unusual traffic|安全验证|人机验证|验证码|完成验证",
                text,
                re.I,
            )
        )

    @staticmethod
    def _browser_search_requests_enter(observation: dict[str, Any]) -> bool:
        text = " ".join((str(observation.get("title") or ""), str(observation.get("text") or "")))
        return bool(
            re.search(
                r"按.{0,6}(?:回车|enter).{0,8}(?:检索|搜索|search)|press.{0,12}enter.{0,20}search",
                text,
                re.I,
            )
        )

    @staticmethod
    def _browser_agent_prompt_elements(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep planner context semantic and bounded; do not send unrelated form values."""
        controls: list[dict[str, Any]] = []
        for item in elements[:40]:
            control = {
                key: item[key]
                for key in (
                    "id",
                    "tag",
                    "role",
                    "name",
                    "type",
                    "placeholder",
                    "href",
                    "enabled",
                    "selected",
                    "expanded",
                )
                if key in item
            }
            is_search = bool(
                item.get("type") == "search"
                or re.search(r"search|搜索|查询|查找", f"{item.get('name', '')} {item.get('placeholder', '')}", re.I)
            )
            if item.get("tag") == "select":
                control["value"] = str(item.get("value") or "")[:80]
                control["options"] = [
                    {
                        "value": str(option.get("value") or "")[:80],
                        "label": str(option.get("label") or "")[:80],
                        "enabled": bool(option.get("enabled", True)),
                    }
                    for option in (item.get("options") or [])[:16]
                ]
            elif is_search and "value" in item:
                control["value"] = str(item.get("value") or "")[:120]
            if "name" in control:
                control["name"] = str(control["name"] or "")[:120]
            if "placeholder" in control:
                control["placeholder"] = str(control["placeholder"] or "")[:100]
            if "href" in control:
                control["href"] = str(control["href"] or "")[:240]
            controls.append(control)
        return controls

    async def _browser_agent_candidates(
        self,
        task: TaskExecutionRecord,
        observation: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[BrowserAgentPlan, dict[str, Any]]:
        trusted_domains = self._browser_trusted_domains(self.context.input(task, "trusted_domains", []))
        if state["metrics"].get("ai_fallback_active"):
            plan = self._browser_rule_fallback_plan(
                task.goal, observation, state.get("history") or [], trusted_domains=trusted_domains
            )
            if plan:
                candidate_summary = [item.model_dump(mode="json") for item in plan.candidates]
                await self.context.record_ai_trace(
                    task.id,
                    make_trace_event(
                        uuid4().hex,
                        "workflow.fallback",
                        stage="page_understanding",
                        title="使用本地安全规则生成下一步",
                        message="AI Planner 不可用；规则只从当前页面快照中提出明确的搜索动作。",
                        metadata={
                            "planner_mode": "rule-fallback",
                            "provider_error": state["metrics"].get("ai_fallback_error"),
                            "current_url": observation.get("url"),
                            "candidate_summary": json.dumps(candidate_summary, ensure_ascii=False)[:700],
                        },
                        status="FALLBACK",
                    ),
                )
                return plan, {
                    "provider": "rule-engine",
                    "model": "",
                    "latency_ms": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "planner_mode": "rule-fallback",
                    "fallback_used": True,
                    "fallback_reason": state["metrics"].get("ai_fallback_error"),
                }
            raise TaskBlocked(
                "AI Planner 不可用，当前页面也没有可安全验证的规则动作；请检查页面或恢复 AI Provider 后重试。",
                failure_type="AI_PROVIDER_BLOCKED",
                details={
                    "provider_message": state["metrics"].get("ai_fallback_error"),
                    "planner_mode": "rule-fallback",
                    "current_url": observation.get("url"),
                    "actions_already_executed": len(state.get("history") or []),
                },
            )

        if not await self.ai_service.reserve_ai_call(task.id):
            raise TaskBlocked(
                "AI 候选生成额度已用完，浏览器已停止。",
                failure_type="AI_BUDGET_EXHAUSTED",
                details={"current_url": observation.get("url"), "action_count": len(state.get("history") or [])},
            )

        trace_id = uuid4().hex
        subgoals = state.get("subgoals") or []
        await self.context.record_ai_trace(
            task.id,
            make_trace_event(
                trace_id,
                "analysis_started",
                stage="page_understanding",
                title="AI 正在理解页面并生成下一步候选",
                message=(state.get("current_subgoal") or task.goal)[:240],
                metadata={"url": observation.get("url"), "title": observation.get("title")},
            ),
        )
        prompt_data = {
            "goal": task.goal[:1500],
            "trusted_domains": self._browser_trusted_domains(self.context.input(task, "trusted_domains", [])),
            "high_level_subgoals": subgoals,
            "previous_subgoal": state.get("current_subgoal"),
            "previous_actions_and_results": [
                {
                    key: item.get(key)
                    for key in ("action", "target", "status", "expected_effect", "url_before", "url_after")
                    if item.get(key) is not None
                }
                for item in (state.get("history") or [])[-5:]
            ],
            "current_page": {
                "url": observation.get("url"),
                "title": observation.get("title"),
                "visible_text": (observation.get("text") or "")[:3000],
                "accessibility_tree": (observation.get("accessibility_tree") or "")[:4000],
                "interactive_elements": self._browser_agent_prompt_elements(observation.get("elements", [])),
                "network_status": observation.get("network"),
                "state_hash": observation.get("state_hash"),
            },
            "required_behavior": [
                "On the first observation, return at most 6 short ordered high-level subgoals.",
                "Generate 1-3 candidate actions only from current interactive element IDs; use no invented selectors.",
                "Return a preferred_candidate_id as the AI-only ranking fallback.",
                "Return one candidate unless the page has a real ambiguity; keep every explanation to one short sentence.",
                "After every action use the newly observed page; never reuse the previous observation as current state.",
                "Never choose checkout, purchase, payment, account mutation, or destructive actions.",
                "Submit a search only when the user explicitly requested it and the current page exposes the search controls; Enter may be pressed only on that observed search input.",
                "If the page visibly instructs you to press Enter to submit the current search, press Enter on the observed search input instead of clicking the submit button again.",
                "Add-to-cart is allowed only when the user goal explicitly asks to add the product to cart.",
                "Claim completion only when the current page provides visible evidence; list the exact evidence.",
                "For an official-site goal, only claim completion on HTTPS hosts matching an explicitly provided trusted_domains entry; a brand word in a hostname is not proof.",
                "If the current state is unexpected, propose one bounded recovery action such as back, then re-observe.",
            ],
        }
        started = time.perf_counter()
        provider_name = "unknown"
        provider_model = ""
        try:
            provider, response = await self.ai_service.complete_browser_action_candidates(task, prompt_data)
            provider_name = str(getattr(provider, "provider_name", "unknown"))
            provider_model = str(getattr(provider, "model", ""))
        except Exception as error:
            provider_error = str(getattr(error, "code", None) or type(error).__name__)[:100]
            provider_message = str(getattr(error, "safe_message", None) or "").strip()
            if not provider_message:
                provider_message = SensitiveRedactor.redact_text(str(error)).strip()
            if not provider_message:
                provider_message = f"AI Provider 调用失败（{type(error).__name__}）。"
            provider_message = SensitiveRedactor.redact_text(provider_message)[:500]
            provider_retry_count = max(0, int(getattr(error, "retry_count", 0) or 0))
            failed_after_ms = round((time.perf_counter() - started) * 1000, 1)
            state["metrics"]["ai_fallback_active"] = True
            state["metrics"]["ai_fallback_error"] = provider_message
            await self.context.record_ai_trace(
                task.id,
                make_trace_event(
                    trace_id,
                    "failed",
                    stage="page_understanding",
                    title="AI 页面分析失败",
                    message=f"{provider_message} 页面没有执行本轮浏览操作。",
                    metadata={
                        "provider": provider_name,
                        "model": provider_model,
                        "provider_error": provider_error,
                        "retry_count": provider_retry_count,
                        "actions_already_executed": len(state.get("history") or []),
                        "current_url": observation.get("url"),
                    },
                    status="FAILED",
                    duration_ms=failed_after_ms,
                ),
            )
            plan = self._browser_rule_fallback_plan(
                task.goal, observation, state.get("history") or [], trusted_domains=trusted_domains
            )
            if plan:
                state["metrics"]["fallbacks"] = int(state["metrics"].get("fallbacks", 0)) + 1
                rule_candidates = [item.model_dump(mode="json") for item in plan.candidates]
                await self.context.record_ai_trace(
                    task.id,
                    make_trace_event(
                        trace_id,
                        "workflow.fallback",
                        stage="page_understanding",
                        title="AI Planner 不可用，已启用安全规则回退",
                        message="将继续处理当前页面中明确的搜索动作；每个控件仍需经过可见性、风险和 Locator 验证。",
                        metadata={
                            "provider": provider_name,
                            "model": provider_model,
                            "provider_error": provider_error,
                            "planner_mode": "rule-fallback",
                            "current_url": observation.get("url"),
                            "candidate_summary": json.dumps(rule_candidates, ensure_ascii=False)[:700],
                        },
                        status="FALLBACK",
                        duration_ms=failed_after_ms,
                    ),
                )
                return plan, {
                    "provider": "rule-engine",
                    "model": "",
                    "latency_ms": failed_after_ms,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "planner_mode": "rule-fallback",
                    "fallback_used": True,
                    "fallback_reason": provider_message,
                    "upstream_provider": provider_name,
                    "upstream_model": provider_model,
                }
            raise TaskBlocked(
                f"AI 页面分析失败：{provider_message}",
                failure_type="AI_PROVIDER_BLOCKED",
                details={
                    "provider_error": provider_error,
                    "provider_message": provider_message,
                    "provider_retry_count": provider_retry_count,
                    "provider": provider_name,
                    "model": provider_model,
                    "actions_already_executed": len(state.get("history") or []),
                    "current_url": observation.get("url"),
                },
            ) from error

        state["metrics"]["ai_calls"] = int(state["metrics"].get("ai_calls", 0)) + 1
        latency = round((time.perf_counter() - started) * 1000, 1)
        async with self.context.repository_scope() as repositories:
            repo = repositories.tasks
            await repo.add_event(
                task.id,
                "step.progress",
                {
                    "step_id": self.context.active_runtime_step.get(),
                    "type": "ai.call",
                    "ai_run_id": response.invocation_id,
                    "provider": response.provider,
                    "model": response.model,
                    "fallback_used": response.fallback_used,
                    "duration_ms": response.duration_ms,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "operation": "browser_action_candidates",
                },
            )
            await repositories.commit()
        if response.provider == "fake" or response.fallback_used:
            raise TaskBlocked(
                "当前 AI Provider 只返回模拟结果；浏览 Agent 已停止，没有把模拟输出当成真实页面理解。",
                failure_type="AI_PROVIDER_BLOCKED",
                details={"provider": response.provider, "model": response.model},
            )
        try:
            plan = BrowserAgentPlan.model_validate(
                response.structured_data if response.structured_data is not None else json.loads(response.content)
            )
        except Exception as error:
            raise TaskBlocked(
                "AI 返回的浏览候选格式无效，未执行浏览器动作。",
                failure_type="AI_OUTPUT_INVALID",
                details={"provider": response.provider, "model": response.model},
            ) from error
        state["metrics"]["ai_latency_ms"] = latency
        if plan.subgoals and not state.get("subgoals"):
            state["subgoals"] = plan.subgoals[:12]
            await self.context.record_ai_trace(
                task.id,
                make_trace_event(
                    trace_id,
                    "workflow.plan",
                    stage="planning",
                    title="AI 拆分浏览目标",
                    message=" → ".join(state["subgoals"][:8])[:500],
                    metadata={"subgoal_count": len(state["subgoals"])},
                ),
            )
        state["current_subgoal"] = (plan.current_subgoal or task.goal)[:300]
        state["current_subgoal_index"] = plan.current_subgoal_index
        return plan, {
            "provider": response.provider,
            "model": response.model,
            "latency_ms": latency,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        }

    async def _browser_agent(self, task: TaskExecutionRecord, _outputs: dict[str, Any]) -> dict[str, Any]:
        requested_url = str(self.context.input(task, "url", "")).strip()
        parsed = urlparse(requested_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise TaskBlocked("浏览器 Agent 需要不含用户名或密码的 http(s) URL。", failure_type="NAVIGATION_FAILED")

        from app.container import recorder_service
        from app.services.recorder_service import RecorderSessionCreate

        task, _ = await self.context.load_task(task.id)
        if task is None:
            raise TaskBlocked("Browser task no longer exists.")
        persisted = (task.context or {}).get("browser_agent") or {}
        state = {
            "current_url": persisted.get("current_url") or SensitiveRedactor.redact_url(requested_url),
            "subgoals": persisted.get("subgoals") or [],
            "current_subgoal": persisted.get("current_subgoal") or task.goal[:300],
            "current_subgoal_index": int(persisted.get("current_subgoal_index") or 0),
            "history": list(persisted.get("history") or [])[-20:],
            "decision_samples": list(persisted.get("decision_samples") or [])[-20:],
            "state_hashes": list(persisted.get("state_hashes") or [])[-20:],
            "url_history": list(persisted.get("url_history") or [])[-20:],
            "metrics": {
                "ai_calls": 0,
                "jev_decisions": 0,
                "jev_correct": 0,
                "jev_failed": 0,
                "jev_abstain": 0,
                "fallbacks": 0,
                "browser_actions": 0,
                "browser_action_success": 0,
                "failed_actions": 0,
                "recovery_count": 0,
                "human_takeovers": int((persisted.get("metrics") or {}).get("human_takeovers", 0)),
                "loop_detected": False,
                "goal_completion": False,
                "total_duration_ms": 0,
                "ai_latency_ms": 0,
                "jev_latency_ms": 0,
                "browser_latency_ms": 0,
                **(persisted.get("metrics") or {}),
            },
        }
        session = None
        browser_session_id: str | None = None
        owns_browser_session = False
        page = None
        initial_http_status = None

        async def close_owned_browser_after_setup_error() -> None:
            if owns_browser_session and browser_session_id:
                await self.browser_runtime.close_session(browser_session_id)

        recorder_session_id = str(self.context.input(task, "recorder_session_id", "") or "").strip()
        if recorder_session_id:
            session = await recorder_service.get(recorder_session_id, str(task.owner_id))
            if not session or session.project_id != task.project_id:
                raise TaskBlocked("浏览器录制会话已关闭或不属于当前项目。", failure_type="HUMAN_TAKEOVER_UNAVAILABLE")
        elif task.project_id:
            try:
                session = await recorder_service.create_session(
                    str(task.owner_id), RecorderSessionCreate(project_id=task.project_id, start_url=requested_url)
                )
            except Exception as error:
                raise TaskBlocked(
                    "无法启动实时浏览器；请检查 Chromium/Edge 权限。",
                    failure_type="BROWSER_UNAVAILABLE",
                    details={"error_type": type(error).__name__},
                ) from error
            recorder_session_id = session.id
            async with self.context.repository_scope() as repositories:
                current = await repositories.tasks.get(task.id)
                if current:
                    await repositories.tasks.update_inputs(task.id, recorder_session_id=session.id)
                    await repositories.commit()
        if session:
            browser_session_id = session.browser_session_id
            page = await self.browser_runtime.get_page(browser_session_id)
            if page.url == "about:blank":
                try:
                    initial_http_status = await self.browser_runtime.navigate(
                        browser_session_id, requested_url, timeout_ms=30_000
                    )
                except Exception as error:
                    raise self._browser_navigation_failure(error, requested_url) from error
        else:
            try:
                browser_session = await self.browser_runtime.create_session()
                browser_session_id = browser_session.id
                owns_browser_session = True
                page = await self.browser_runtime.get_page(browser_session_id)
            except Exception as error:
                safe_message = SensitiveRedactor.redact_text(str(error)).strip()[:500]
                await close_owned_browser_after_setup_error()
                raise TaskBlocked(
                    f"无法启动实时浏览器实例。{safe_message}" if safe_message else "无法启动实时浏览器实例。",
                    failure_type="BROWSER_UNAVAILABLE",
                    details={
                        "stage": "browser_startup",
                        "error_type": type(error).__name__,
                        "error_message": safe_message or None,
                    },
                ) from error
            resume_url = str(state.get("current_url") or requested_url)
            try:
                initial_http_status = await self.browser_runtime.navigate(
                    browser_session_id, resume_url, timeout_ms=30_000
                )
            except Exception as error:
                await close_owned_browser_after_setup_error()
                raise self._browser_navigation_failure(error, resume_url) from error

        if browser_session_id is None or page is None:
            await close_owned_browser_after_setup_error()
            raise TaskBlocked("浏览器运行时没有返回有效会话。", failure_type="BROWSER_UNAVAILABLE")

        started = time.perf_counter()
        network = {"requests": 0, "failed": 0, "responses": 0}
        page.on("request", lambda _request: network.__setitem__("requests", network["requests"] + 1))
        page.on("requestfailed", lambda _request: network.__setitem__("failed", network["failed"] + 1))
        page.on("response", lambda _response: network.__setitem__("responses", network["responses"] + 1))
        browser_policy = get_config().agent.browser
        max_actions = max(
            1,
            min(
                browser_policy.max_actions,
                int(self.context.input(task, "max_browser_actions", browser_policy.max_actions)),
            ),
        )
        max_recoveries = max(0, min(5, int(self.context.input(task, "max_recovery_attempts", 2))))
        criteria = self.context.input(task, "observable_text_criteria", [])
        criteria = [str(value)[:200] for value in criteria[:10]] if isinstance(criteria, list) else []
        trusted_domains = self._browser_trusted_domains(self.context.input(task, "trusted_domains", []))
        goal_text = task.goal.casefold()
        cart_intent = self._browser_cart_intent(goal_text)
        initial_hash = persisted.get("pause_state_hash")
        stop_reason = "ACTION_LIMIT_REACHED"
        goal_completed = False
        latest_observation: dict[str, Any] = {}
        recovered_pause = bool(persisted.get("pause_count"))
        waited_loading_states: set[tuple[str, str]] = set()

        try:
            if recovered_pause and session:
                latest_observation = await self._observe_browser_page(
                    page, network, waited_loading_states=waited_loading_states
                )
                if initial_hash and latest_observation["state_hash"] != initial_hash:
                    state["metrics"]["human_takeovers"] += 1
                    takeover = {
                        "action": "human_takeover",
                        "status": "observed_page_changed_while_paused",
                        "url": latest_observation["url"],
                        "state_hash": latest_observation["state_hash"],
                    }
                    state["history"].append(takeover)
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.human_takeover",
                        "检测到用户接管后的页面变化",
                        latest_observation["title"],
                        status="COMPLETED",
                        metadata={"url": latest_observation["url"], "state_hash": latest_observation["state_hash"]},
                    )

            for action_index in range(int(state["metrics"].get("browser_actions", 0)), max_actions):
                task, _ = await self.context.load_task(task.id)
                if not task or task.status == TaskStatus.CANCELLED.value:
                    raise TaskBlocked("浏览任务已取消。", failure_type="ACTION_FAILED")
                previous_url = str(latest_observation.get("url") or "")
                observed = await self._observe_browser_page(page, network, waited_loading_states=waited_loading_states)
                if self._browser_official_site_brand(task.goal):
                    navigation_rejection = None
                    if previous_url:
                        navigation_rejection = self._browser_navigation_landing_rejection(
                            task.goal, previous_url, observed["url"], trusted_domains
                        )
                    elif not self._browser_official_entry_url_allowed(observed["url"], trusted_domains):
                        navigation_rejection = "navigation_landed_not_trusted"
                    if navigation_rejection:
                        latest_observation = observed
                        state["current_url"] = observed["url"]
                        stop_reason = "OFFICIAL_DOMAIN_UNVERIFIED"
                        await self.context.browser_agent_event(
                            task.id,
                            "browser.official_domain_unverified",
                            "当前页面未通过可信导航校验，Agent 已停止",
                            "页面不属于 HTTPS 搜索来源或已配置的可信官网；未向 Planner 提交该页面或执行后续动作。",
                            status="BLOCKED",
                            metadata={
                                "url_before": previous_url or None,
                                "url_after": observed["url"],
                                "trusted_domains": trusted_domains,
                            },
                        )
                        break
                latest_observation = observed
                current_hash = latest_observation["state_hash"]
                current_url = latest_observation["url"]
                if not state["url_history"] or state["url_history"][-1] != current_url:
                    state["url_history"].append(current_url)
                    state["url_history"] = state["url_history"][-20:]
                if self._browser_url_loop(state["url_history"]):
                    state["metrics"]["loop_detected"] = True
                    stop_reason = "LOOP_DETECTED"
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.loop_detected",
                        "页面来回跳转已停止",
                        "检测到重复的 URL 往返；Agent 已停止继续操作。",
                        status="BLOCKED",
                        metadata={"url": current_url},
                    )
                    break
                visits = state["state_hashes"]
                if visits.count(current_hash) >= 3:
                    state["metrics"]["loop_detected"] = True
                    stop_reason = "LOOP_DETECTED"
                    break
                visits.append(current_hash)
                state["state_hashes"] = visits[-20:]

                await self.context.persist_browser_agent_evidence(
                    task.id,
                    EvidenceType.ACCESSIBILITY_TREE,
                    "playwright.aria_snapshot",
                    f"Observed {latest_observation['title']!r} at {latest_observation['url']}; {len(latest_observation['elements'])} visible controls.",
                    latest_observation["accessibility_tree"],
                    {
                        "url": latest_observation["url"],
                        "title": latest_observation["title"],
                        "state_hash": current_hash,
                    },
                )
                await self.context.persist_browser_agent_evidence(
                    task.id,
                    EvidenceType.DOM_SNAPSHOT,
                    "playwright.visible_page_text",
                    "Visible text and interactive element snapshot for this decision.",
                    latest_observation["text"],
                    {"candidate_count": len(latest_observation["elements"]), "state_hash": current_hash},
                )

                if not state.get("history"):
                    screenshot = await self.context.artifact(
                        task,
                        "browser_agent",
                        "browser-initial.png",
                        "SCREENSHOT",
                        await page.screenshot(type="png"),
                        "image/png",
                    )
                    await self.context.persist_browser_agent_artifact(task.id, screenshot)

                if not state.get("history") and initial_http_status is not None and initial_http_status >= 400:
                    stop_reason = "HTTP_STATUS_ERROR"
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.action_blocked",
                        f"起始页面返回 HTTP {initial_http_status}",
                        "页面地址没有返回成功状态；Agent 已停止，未执行任何浏览操作。",
                        status="BLOCKED",
                        metadata={
                            "url": current_url,
                            "http_status": initial_http_status,
                            "action_executed": False,
                        },
                    )
                    break

                if self._browser_human_verification_required(latest_observation):
                    state["current_url"] = current_url
                    state["pause_state_hash"] = current_hash
                    state["pause_count"] = int(state.get("pause_count", 0)) + 1
                    state["metrics"]["human_verification_required"] = True
                    verification_artifact_id = None
                    try:
                        verification_artifact = await self.context.artifact(
                            task,
                            "browser_agent",
                            "browser-verification.png",
                            "SCREENSHOT",
                            await page.screenshot(type="png"),
                            "image/png",
                        )
                        await self.context.persist_browser_agent_artifact(task.id, verification_artifact)
                        verification_artifact_id = verification_artifact.get("artifact_id")
                    except Exception as error:
                        logger.warning(
                            "Could not capture browser verification screenshot task_id=%s error_type=%s",
                            task.id,
                            type(error).__name__,
                        )
                    state["human_verification"] = {
                        "resume_available": False,
                        "artifact_id": verification_artifact_id,
                    }
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.human_verification_required",
                        "目标网站要求人工安全验证",
                        "Agent 已停止自动操作；已保存验证页证据。",
                        status="WAITING_FOR_USER",
                        metadata={
                            "url": current_url,
                            "title": latest_observation["title"],
                            "interactive_session_available": bool(session),
                            "artifact_id": verification_artifact_id,
                        },
                    )
                    if session:
                        paused_task = await self.pause(task.id, str(task.owner_id))
                        if paused_task:
                            state["human_verification"]["resume_available"] = True
                            await self.context.persist_browser_agent_state(
                                task.id,
                                state,
                                title="等待人工完成网站安全验证",
                                summary="请在同一浏览器会话中完成验证，再恢复 Agent。",
                                status="PAUSED",
                                event_type="browser.agent_paused",
                            )
                            return {"_pause_after_step": True, "current_url": current_url}
                    stop_reason = "HUMAN_VERIFICATION_REQUIRED"
                    break

                plan, ai_info = await self._browser_agent_candidates(task, latest_observation, state)
                state["metrics"]["total_duration_ms"] = round((time.perf_counter() - started) * 1000, 1)

                if plan.goal_status == "completed" and self._browser_goal_verified(
                    task.goal,
                    plan,
                    latest_observation,
                    state["history"],
                    criteria,
                    cart_intent,
                    trusted_domains=trusted_domains,
                ):
                    goal_completed = True
                    stop_reason = "OBSERVED_GOAL_EVIDENCE"
                    state["metrics"]["goal_completion"] = True
                    break
                if plan.goal_status == "completed" and self._browser_official_site_brand(task.goal):
                    stop_reason = "OFFICIAL_DOMAIN_UNVERIFIED"
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.official_domain_unverified",
                        "官网域名尚未验证",
                        "请填写可信域名，并确认当前 HTTPS 主机名与之匹配后再标记完成。",
                        status="BLOCKED",
                        metadata={"url": latest_observation.get("url"), "trusted_domains": trusted_domains},
                    )
                    break
                if plan.goal_status == "blocked":
                    stop_reason = "AI_REPORTED_BLOCKER"
                    break

                element_by_id = {str(item["id"]): item for item in latest_observation["elements"]}
                search_intent = bool(re.search(r"\bsearch\b|搜索|查询|查找", task.goal, re.I))
                editable_controls = [
                    item
                    for item in latest_observation["elements"]
                    if item.get("visible")
                    and item.get("enabled")
                    and item.get("tag") in {"input", "textarea"}
                    and item.get("type") in {"", "text", "search"}
                ]
                has_search_submit = any(
                    item.get("visible")
                    and item.get("enabled")
                    and item.get("role") in {"button", "link"}
                    and re.search(r"search|搜索|查询|查找|百度一下", str(item.get("name") or ""), re.I)
                    for item in latest_observation["elements"]
                )
                seen_ids: set[str] = set()
                valid_candidates: list[dict[str, Any]] = []
                approval_candidates: list[dict[str, str]] = []
                rejected = 0
                candidate_diagnostics: list[dict[str, Any]] = []

                def reject_candidate(proposal, reason: str) -> None:
                    nonlocal rejected
                    rejected += 1
                    candidate_diagnostics.append(
                        {
                            "candidate_id": proposal.candidate_id,
                            "action_type": proposal.action_type,
                            "target_id": proposal.target_id,
                            "result": "rejected",
                            "reason": reason,
                        }
                    )

                for proposal in plan.candidates[:5]:
                    if proposal.candidate_id in seen_ids:
                        reject_candidate(proposal, "duplicate_candidate_id")
                        continue
                    seen_ids.add(proposal.candidate_id)
                    element = element_by_id.get(proposal.target_id or "")
                    page_action = proposal.action_type in {"back", "scroll", "wait", "inspect"}
                    if proposal.action_type == "back" and not self._browser_has_safe_back_target(state["url_history"]):
                        reject_candidate(proposal, "no_safe_previous_page")
                        continue
                    if not page_action and (not element or not element.get("visible") or not element.get("enabled")):
                        reject_candidate(proposal, "target_not_observed_visible_and_enabled")
                        continue
                    if proposal.action_type in {"fill", "select"} and not element:
                        reject_candidate(proposal, "input_target_not_observed")
                        continue
                    search_field_labeled = bool(
                        element
                        and (
                            element.get("type") == "search"
                            or re.search(
                                r"search|搜索|查询|查找",
                                f"{element.get('name', '')} {element.get('placeholder', '')} {urlparse(str(element.get('form_action') or '')).path}",
                                re.I,
                            )
                        )
                    )
                    unique_editable_search_field = bool(
                        search_intent
                        and len(editable_controls) == 1
                        and editable_controls[0].get("id") == proposal.target_id
                    )
                    unique_search_field = unique_editable_search_field and has_search_submit
                    is_search_input = (
                        search_field_labeled
                        or unique_search_field
                        or (proposal.action_type == "press_key" and unique_editable_search_field)
                    )
                    if proposal.action_type == "fill":
                        if element.get("tag") not in {"input", "textarea"} or element.get("type") not in {
                            "",
                            "text",
                            "search",
                            "number",
                        }:
                            reject_candidate(proposal, "target_not_editable_text_input")
                            continue
                        if not proposal.value:
                            reject_candidate(proposal, "fill_value_missing")
                            continue
                        if not is_search_input:
                            reject_candidate(proposal, "target_not_recognized_as_search_input")
                            continue
                    if proposal.action_type == "press_key":
                        if element.get("tag") not in {"input", "textarea"} or element.get("type") not in {
                            "",
                            "text",
                            "search",
                        }:
                            reject_candidate(proposal, "key_target_not_text_input")
                            continue
                        if proposal.value != "Enter" or not search_intent or not is_search_input:
                            reject_candidate(proposal, "only_explicit_search_enter_is_allowed")
                            continue
                    if proposal.action_type == "select":
                        if element.get("tag") != "select":
                            reject_candidate(proposal, "target_not_select")
                            continue
                        if not any(
                            option.get("enabled") and str(option.get("value")) == str(proposal.value)
                            for option in element.get("options", [])
                        ):
                            reject_candidate(proposal, "select_option_not_available")
                            continue
                    if proposal.action_type in {"navigate", "open_product"} and not (
                        element and element.get("tag") == "a" and element.get("href")
                    ):
                        reject_candidate(proposal, "navigation_target_not_observed_link")
                        continue
                    navigation_rejection = self._browser_navigation_candidate_rejection(
                        task.goal,
                        latest_observation.get("url", ""),
                        proposal.action_type,
                        element or {},
                        trusted_domains,
                    )
                    if navigation_rejection:
                        reject_candidate(proposal, navigation_rejection)
                        continue
                    if proposal.action_type == "add_to_cart" and not cart_intent:
                        reject_candidate(proposal, "cart_action_not_requested")
                        continue
                    risk_action = proposal.action_type
                    label = str((element or {}).get("name") or proposal.target)
                    cart_control = bool(
                        re.search(
                            r"add.?to.?cart|add.?to.?bag|add.?to.?basket|加入购物车|加入购物袋|添加到购物车|添加到购物袋",
                            label,
                            re.I,
                        )
                    )
                    if cart_control and not cart_intent:
                        reject_candidate(proposal, "cart_action_not_requested")
                        continue
                    contextual_search_submit = bool(
                        search_intent
                        and has_search_submit
                        and len(editable_controls) == 1
                        and element
                        and element.get("role") == "button"
                        and re.search(r"search|搜索|查询|查找|百度一下", label, re.I)
                    )
                    if risk_action == "click" and (
                        re.search(r"search|filter|category|menu|搜索|筛选|分类|菜单", label, re.I)
                        or contextual_search_submit
                    ):
                        risk_action = "filter"
                    if risk_action == "fill":
                        risk_action = "filter"
                    if risk_action == "press_key" and is_search_input and proposal.value == "Enter":
                        risk_action = "filter"
                    if risk_action == "select" and re.search(
                        r"color|colour|size|variant|颜色|色系|尺码|尺寸|规格", label, re.I
                    ):
                        risk_action = "choose_variant"
                    if risk_action == "click" and (element or {}).get("expanded") is not None:
                        risk_action = "filter"
                    risk = classify_browser_action(
                        risk_action,
                        name=label,
                        tag=str((element or {}).get("tag") or ""),
                        href=str((element or {}).get("_href") or (element or {}).get("href") or ""),
                        input_type=str((element or {}).get("type") or ""),
                    )
                    if contextual_search_submit and risk == "STATE_CHANGE":
                        risk = "SAFE_INTERACTION"
                    if risk not in {"READ_ONLY", "SAFE_INTERACTION"}:
                        approval_candidates.append(
                            {"candidate_id": proposal.candidate_id, "target": label[:120], "risk": risk}
                        )
                        reject_candidate(proposal, f"approval_required:{risk}")
                        continue
                    locator = None
                    locator_checks = []
                    if not page_action:
                        action_for_verify = (
                            "press"
                            if proposal.action_type == "press_key"
                            else "fill"
                            if proposal.action_type == "fill"
                            else "click"
                        )
                        for variant in self._browser_locator_variants(element):
                            verification = await self.browser_runtime.verify_locator(
                                browser_session_id, variant, {"action": action_for_verify}
                            )
                            locator_checks.append({"kind": variant["kind"], **verification})
                            if verification["verified"]:
                                locator = variant
                                break
                        if locator is None:
                            reject_candidate(proposal, "locator_not_verified_against_current_page")
                            candidate_diagnostics[-1]["locator_checks"] = locator_checks
                            continue
                    row = proposal.model_dump(mode="json")
                    if cart_control:
                        row["action_type"] = "add_to_cart"
                    row.update(
                        {
                            "target": label[:200],
                            "locator": locator,
                            "locator_strategy": locator.get("kind") if locator else "page",
                            "risk": risk,
                            "_search_submit": contextual_search_submit,
                            "_element": element,
                        }
                    )
                    valid_candidates.append(row)
                    candidate_diagnostics.append(
                        {
                            "candidate_id": proposal.candidate_id,
                            "action_type": proposal.action_type,
                            "target_id": proposal.target_id,
                            "result": "accepted",
                            "reason": "unique_search_field_with_visible_search_submit"
                            if proposal.action_type in {"fill", "press_key"}
                            and unique_search_field
                            and not search_field_labeled
                            else None,
                        }
                    )

                candidate_summary = [
                    {
                        key: row.get(key)
                        for key in (
                            "candidate_id",
                            "action_type",
                            "target",
                            "locator_strategy",
                            "reason_summary",
                            "expected_effect",
                            "risk",
                        )
                    }
                    for row in valid_candidates
                ]
                decision_candidates = [
                    {**summary, "value": row.get("value")}
                    for row, summary in zip(valid_candidates, candidate_summary, strict=True)
                ]
                await self.context.record_ai_trace(
                    task.id,
                    make_trace_event(
                        uuid4().hex,
                        "candidates_generated",
                        stage="candidate_generation",
                        title=(
                            f"规则回退生成 {len(valid_candidates)} 个可验证候选"
                            if ai_info.get("planner_mode") == "rule-fallback"
                            else f"AI 生成 {len(valid_candidates)} 个可验证候选"
                        ),
                        message=state["current_subgoal"],
                        metadata={
                            "candidate_count": len(valid_candidates),
                            "candidate_summary": json.dumps(candidate_summary, ensure_ascii=False)[:480],
                            "candidate_review": candidate_diagnostics,
                            "rejected_count": rejected,
                            "ai_preference": plan.preferred_candidate_id,
                            **ai_info,
                        },
                    ),
                )
                await self.context.persist_browser_agent_state(
                    task.id,
                    state,
                    title=f"AI 正在浏览网页 · {state['current_subgoal']}",
                    summary=f"已检查 {len(latest_observation['elements'])} 个可见控件，得到 {len(valid_candidates)} 个有效候选。",
                )
                if not valid_candidates:
                    locator_candidates_only = bool(candidate_diagnostics) and all(
                        item.get("reason") == "locator_not_verified_against_current_page"
                        for item in candidate_diagnostics
                    )
                    if locator_candidates_only:
                        refreshed = await self._observe_browser_page(
                            page, network, waited_loading_states=waited_loading_states
                        )
                        if refreshed["state_hash"] != current_hash:
                            retries = int(state["metrics"].get("stale_candidate_retries", 0)) + 1
                            state["metrics"]["stale_candidate_retries"] = retries
                            await self.context.browser_agent_event(
                                task.id,
                                "browser.observation_changed",
                                "页面在 AI 分析期间发生变化",
                                "旧候选定位器已丢弃；Agent 将使用新页面快照重新分析。",
                                status="RETRYING" if retries <= 2 else "BLOCKED",
                                metadata={"previous_url": latest_observation["url"], "current_url": refreshed["url"]},
                            )
                            latest_observation = refreshed
                            state["current_url"] = refreshed["url"]
                            if retries <= 2:
                                continue
                            stop_reason = "PAGE_UNSTABLE"
                            break

                    untrusted_navigation = any(
                        item.get("reason") == "navigation_target_not_trusted" for item in candidate_diagnostics
                    )
                    no_safe_history = any(
                        item.get("reason") == "no_safe_previous_page" for item in candidate_diagnostics
                    )
                    stop_reason = (
                        "APPROVAL_REQUIRED"
                        if approval_candidates
                        else "OFFICIAL_DOMAIN_UNVERIFIED"
                        if untrusted_navigation
                        else "NO_SAFE_HISTORY"
                        if no_safe_history
                        else "NO_CANDIDATE"
                    )
                    if approval_candidates:
                        await self.context.browser_agent_event(
                            task.id,
                            "browser.action_blocked",
                            "浏览操作需要用户确认",
                            "页面上只找到需要确认的高风险操作；Agent 没有执行。请在浏览器中接管。",
                            status="BLOCKED",
                            metadata={"blocked_candidates": json.dumps(approval_candidates, ensure_ascii=False)[:400]},
                        )
                    elif untrusted_navigation:
                        await self.context.browser_agent_event(
                            task.id,
                            "browser.official_domain_unverified",
                            "目标站点不在可信域名内",
                            "请填写正确的 HTTPS 官网验证域名；Agent 未打开被拦截的链接。",
                            status="BLOCKED",
                            metadata={"url": latest_observation.get("url"), "trusted_domains": trusted_domains},
                        )
                    elif no_safe_history:
                        await self.context.browser_agent_event(
                            task.id,
                            "browser.action_blocked",
                            "当前页面没有可安全返回的上一页",
                            "该浏览任务尚未观察到可返回的网页；没有执行后退操作。",
                            status="BLOCKED",
                            metadata={"url": latest_observation.get("url"), "action_executed": False},
                        )
                    break

                jev_required = get_config().agent.browser.require_jev or bool(
                    self.context.input(task, "require_jev_decisions", False)
                )
                jev_needed = self._browser_jev_needed(len(valid_candidates), jev_required)
                jev_result = None
                jev_error = None
                jev_latency = 0.0
                if jev_needed:
                    state["metrics"]["jev_decisions"] += 1
                    decision_started = time.perf_counter()
                    await self.context.record_ai_trace(
                        task.id,
                        make_trace_event(
                            uuid4().hex,
                            "decision_started",
                            stage="decision",
                            title="JEV 正在选择浏览动作",
                            message=state["current_subgoal"],
                            metadata={"candidate_count": len(valid_candidates), "jev_attempted": True},
                        ),
                    )
                    try:
                        decision_request = DecisionRequest(
                            name="browser_action_selection",
                            state={
                                "goal": task.goal[:1000],
                                "current_subgoal": state["current_subgoal"],
                                "page_summary": {
                                    "url": latest_observation["url"],
                                    "title": latest_observation["title"],
                                    "visible_text": latest_observation["text"][:2500],
                                    "state_hash": current_hash,
                                },
                                "relevant_elements": [
                                    {key: value for key, value in row["_element"].items() if not key.startswith("_")}
                                    for row in valid_candidates
                                    if row.get("_element")
                                ],
                                "candidates": decision_candidates,
                                "previous_action_result": (state.get("history") or [{}])[-1],
                            },
                            instructions="Select only the candidate_id for the best safe next browser action, considering its exact action value, or choose abstain. Never create or alter a selector or action.",
                            options=[
                                *[
                                    DecisionOption(
                                        key=row["candidate_id"],
                                        description=json.dumps(
                                            {
                                                key: row.get(key)
                                                for key in (
                                                    "action_type",
                                                    "target",
                                                    "locator",
                                                    "reason_summary",
                                                    "expected_effect",
                                                    "risk",
                                                )
                                            },
                                            ensure_ascii=False,
                                        )[:1000],
                                    )
                                    for row in valid_candidates
                                ],
                                DecisionOption(key="abstain", description="No candidate is reliably appropriate."),
                            ],
                        )
                        jev_result = await self.decision_service.choose(
                            decision_request,
                            task_id=task.id,
                            run_id=uuid4().hex,
                        )
                    except Exception as error:
                        jev_error = type(error).__name__
                    jev_latency = round((time.perf_counter() - decision_started) * 1000, 1)
                    state["metrics"]["jev_latency_ms"] = jev_latency

                if jev_result and jev_result.provider == "jev" and jev_result.choice == "abstain":
                    state["metrics"]["jev_abstain"] += 1
                chosen, decision_provider, fallback_reason = self._choose_browser_candidate(
                    valid_candidates,
                    plan.preferred_candidate_id,
                    jev_result=jev_result,
                    jev_error=jev_error,
                )
                if jev_needed and decision_provider != "jev":
                    state["metrics"]["jev_failed"] += 1
                    state["metrics"]["last_jev_error"] = fallback_reason or "no_reliable_decision"
                    if jev_result and jev_result.confidence is not None:
                        state["metrics"]["last_jev_confidence"] = jev_result.confidence
                if jev_required and jev_needed and decision_provider != "jev":
                    stop_reason = "JEV_NO_DECISION"
                    confidence = jev_result.confidence if jev_result else None
                    decision_reason = fallback_reason or "no_reliable_decision"
                    minimum_confidence = jev_result.minimum_confidence if jev_result else None
                    if minimum_confidence is not None:
                        state["metrics"]["last_jev_minimum_confidence"] = minimum_confidence
                    if jev_result and jev_result.attempted_choice:
                        state["metrics"]["last_jev_attempted_choice"] = jev_result.attempted_choice
                    if decision_reason == "below_minimum_confidence" and confidence is not None:
                        threshold = f" {minimum_confidence:.2f}" if minimum_confidence is not None else ""
                        summary = f"Jev 置信度 {confidence:.2f} 低于配置阈值{threshold}；没有执行浏览操作。"
                    else:
                        summary = f"Jev 未给出可靠选择（{decision_reason}）；没有执行浏览操作。"
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.decision_blocked",
                        "Jev 决策未通过，浏览操作已停止",
                        summary,
                        status="BLOCKED",
                        metadata={
                            "provider": (jev_result.attempted_provider or "jev") if jev_result else "jev",
                            "model": jev_result.attempted_model if jev_result else None,
                            "candidate_count": len(valid_candidates),
                            "jev_attempted": bool(jev_needed),
                            "attempted_choice": jev_result.attempted_choice if jev_result else None,
                            "failure_reason": decision_reason,
                            "confidence": confidence,
                            "minimum_confidence": minimum_confidence,
                            "fallback_used": bool(jev_result and jev_result.fallback_used),
                            "action_executed": False,
                        },
                    )
                    break
                if jev_needed and decision_provider != "jev":
                    state["metrics"]["fallbacks"] += 1
                ai_preference = next(
                    (row for row in valid_candidates if row["candidate_id"] == plan.preferred_candidate_id), None
                )
                if (
                    ai_preference
                    and len(valid_candidates) > 1
                    and ai_preference["candidate_id"] != chosen["candidate_id"]
                ):
                    state["metrics"].setdefault("ai_jev_disagreements", 0)
                    state["metrics"]["ai_jev_disagreements"] += 1

                selected_locator = chosen.get("locator")
                selected_element = chosen.get("_element") or {}
                if self._browser_repeats_same_target(state["history"], chosen):
                    state["metrics"]["loop_detected"] = True
                    stop_reason = "LOOP_DETECTED"
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.loop_detected",
                        "重复动作已停止",
                        f"连续两次选择同一页面控件：{chosen['action_type']} · {chosen['target']}",
                        status="BLOCKED",
                        metadata={"candidate_id": chosen["candidate_id"], "action": chosen["action_type"]},
                    )
                    break
                live_url = SensitiveRedactor.redact_url(str(page.url or ""))
                if live_url != current_url:
                    refreshed = await self._observe_browser_page(
                        page, network, waited_loading_states=waited_loading_states
                    )
                    navigation_rejection = self._browser_navigation_landing_rejection(
                        task.goal, current_url, refreshed["url"], trusted_domains
                    )
                    retries = int(state["metrics"].get("stale_candidate_retries", 0)) + 1
                    state["metrics"]["stale_candidate_retries"] = retries
                    latest_observation = refreshed
                    state["current_url"] = refreshed["url"]
                    if navigation_rejection:
                        stop_reason = "OFFICIAL_DOMAIN_UNVERIFIED"
                        await self.context.browser_agent_event(
                            task.id,
                            "browser.official_domain_unverified",
                            "页面在决策期间跳转到未信任主机，Agent 已停止",
                            "Agent 丢弃了基于旧页面生成的动作，未在新主机执行。",
                            status="BLOCKED",
                            metadata={
                                "url_before": current_url,
                                "url_after": refreshed["url"],
                                "trusted_domains": trusted_domains,
                            },
                        )
                        break
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.observation_changed",
                        "页面在决策期间发生变化",
                        "旧候选动作已丢弃；Agent 将基于新页面重新分析。",
                        status="RETRYING" if retries <= 2 else "BLOCKED",
                        metadata={"previous_url": current_url, "current_url": refreshed["url"]},
                    )
                    if retries <= 2:
                        continue
                    stop_reason = "PAGE_UNSTABLE"
                    break
                decision_sample = {
                    "step": len(state["decision_samples"]) + 1,
                    "url": latest_observation["url"],
                    "state_hash": current_hash,
                    "subgoal": state["current_subgoal"],
                    "candidates": candidate_summary,
                    "ai_preferred_candidate_id": plan.preferred_candidate_id,
                    "selected_candidate_id": chosen["candidate_id"],
                    "provider": decision_provider,
                    "jev_attempted": jev_needed,
                    "jev_failed": bool(fallback_reason and jev_needed),
                    "jev_abstain": bool(jev_result and jev_result.provider == "jev" and jev_result.choice == "abstain"),
                    "fallback_used": decision_provider in {"ai-ranking", "local-heuristic"},
                    "fallback_reason": fallback_reason,
                    "ai_provider": ai_info["provider"],
                    "ai_model": ai_info["model"],
                    "ai_latency_ms": ai_info["latency_ms"],
                    "ai_input_tokens": ai_info["input_tokens"],
                    "ai_output_tokens": ai_info["output_tokens"],
                    "confidence": jev_result.confidence if decision_provider == "jev" and jev_result else None,
                    "minimum_confidence": jev_result.minimum_confidence if decision_provider == "jev" and jev_result else None,
                    "scores": jev_result.probabilities if decision_provider == "jev" and jev_result else {},
                    "latency_ms": jev_latency if jev_needed else 0.0,
                    "model": jev_result.model if decision_provider == "jev" and jev_result else None,
                }
                state["decision_samples"].append(decision_sample)
                await self.context.record_ai_trace(
                    task.id,
                    make_trace_event(
                        uuid4().hex,
                        "decision_completed"
                        if decision_provider in {"jev", "single-candidate"}
                        else "decision.fallback",
                        stage="decision",
                        title=(
                            "JEV 选择了浏览动作"
                            if decision_provider == "jev"
                            else "仅有一个已验证候选，无需 JEV 决策"
                            if decision_provider == "single-candidate"
                            else "已切换到候选排序回退"
                        ),
                        message=f"{chosen['action_type']} · {chosen['target'][:120]}",
                        metadata={
                            "provider": decision_provider,
                            "model": decision_sample["model"],
                            "candidate_id": chosen["candidate_id"],
                            "candidate_count": len(valid_candidates),
                            "confidence": decision_sample["confidence"],
                            "minimum_confidence": decision_sample["minimum_confidence"],
                            "latency_ms": decision_sample["latency_ms"],
                            "fallback_used": decision_sample["fallback_used"],
                            "fallback_reason": fallback_reason,
                            "candidate_summary": json.dumps(candidate_summary, ensure_ascii=False)[:480],
                            "candidate_scores": json.dumps(decision_sample["scores"], ensure_ascii=False)[:400],
                        },
                    ),
                )
                async with self.context.repository_scope() as repositories:
                    repo = repositories.tasks
                    stored = await repo.add_decision(
                        task_id=task.id,
                        step_id=self.context.active_runtime_step.get(),
                        name="browser_action_selection",
                        provider=decision_provider,
                        choice=chosen["candidate_id"],
                        confidence=decision_sample["confidence"],
                        rationale=chosen["reason_summary"][:500],
                    )
                    await repo.add_event(
                        task.id,
                        "decision.created",
                        {
                            "step_id": self.context.active_runtime_step.get(),
                            "decision_id": stored.id,
                            "name": "browser_action_selection",
                            "choice": stored.choice,
                            "provider": stored.provider,
                            "confidence": stored.confidence,
                        },
                    )
                    await repositories.commit()

                before_cart = latest_observation["cart"]
                action_started = time.perf_counter()
                await self.context.browser_agent_event(
                    task.id,
                    "browser.action_started",
                    f"正在执行：{chosen['action_type']} · {chosen['target'] or chosen['value'] or '页面'}",
                    chosen["expected_effect"],
                    status="RUNNING",
                    metadata={
                        "action": chosen["action_type"],
                        "locator": json.dumps(selected_locator, ensure_ascii=False) if selected_locator else "page",
                        "candidate_id": chosen["candidate_id"],
                        "url": latest_observation["url"],
                    },
                )
                # Persisting the decision and progress event above yields to the event loop.
                # A page can navigate during that time, so recheck the live tab immediately
                # before dispatching the selected action.
                dispatch_url = SensitiveRedactor.redact_url(str(page.url or ""))
                if dispatch_url != latest_observation["url"]:
                    navigation_rejection = self._browser_navigation_landing_rejection(
                        task.goal, latest_observation["url"], dispatch_url, trusted_domains
                    )
                    retries = int(state["metrics"].get("stale_candidate_retries", 0)) + 1
                    state["metrics"]["stale_candidate_retries"] = retries
                    state["current_url"] = dispatch_url
                    if navigation_rejection:
                        stop_reason = "OFFICIAL_DOMAIN_UNVERIFIED"
                        await self.context.browser_agent_event(
                            task.id,
                            "browser.official_domain_unverified",
                            "动作执行前页面跳转到未信任主机，Agent 已停止",
                            "已丢弃基于旧页面生成的动作；新页面未执行任何浏览操作。",
                            status="BLOCKED",
                            metadata={
                                "url_before": latest_observation["url"],
                                "url_after": dispatch_url,
                                "trusted_domains": trusted_domains,
                                "candidate_id": chosen["candidate_id"],
                            },
                        )
                        await self.context.browser_agent_event(
                            task.id,
                            "browser.action_blocked",
                            "旧页面候选动作已阻止",
                            "页面在动作开始事件写入期间跳转到非可信地址；所选动作没有执行。",
                            status="BLOCKED",
                            metadata={
                                "action": chosen["action_type"],
                                "candidate_id": chosen["candidate_id"],
                                "url": dispatch_url,
                                "executed": False,
                            },
                        )
                        break
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.observation_changed",
                        "动作执行前页面发生变化",
                        "已丢弃基于旧页面生成的动作；Agent 将重新观察后再规划。",
                        status="RETRYING" if retries <= 2 else "BLOCKED",
                        metadata={
                            "previous_url": latest_observation["url"],
                            "current_url": dispatch_url,
                            "candidate_id": chosen["candidate_id"],
                        },
                    )
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.action_blocked",
                        "旧页面候选动作已取消",
                        "页面在动作开始事件写入期间发生变化；所选动作没有执行，将基于新页面重新规划。",
                        status="RETRYING" if retries <= 2 else "BLOCKED",
                        metadata={
                            "action": chosen["action_type"],
                            "candidate_id": chosen["candidate_id"],
                            "url": dispatch_url,
                            "executed": False,
                        },
                    )
                    if retries <= 2:
                        continue
                    stop_reason = "PAGE_UNSTABLE"
                    break

                state["metrics"]["browser_actions"] += 1
                action_error = None
                opened_pages = []

                def record_opened_page(opened_page: Any) -> None:
                    opened_pages.append(opened_page)

                self.browser_runtime.add_page_listener(browser_session_id, record_opened_page)
                try:
                    await self.context.execute_browser_candidate(browser_session_id, chosen)
                    if chosen.get("_search_submit"):
                        try:
                            await page.wait_for_function(
                                """previousUrl => location.href !== previousUrl || /按.{0,6}(?:回车|enter).{0,8}(?:检索|搜索|search)|press.{0,12}enter.{0,20}search/i.test(document.body?.innerText || '')""",
                                latest_observation["url"],
                                timeout=2500,
                            )
                        except Exception:
                            pass
                    elif (
                        chosen["action_type"] == "press_key"
                        and search_intent
                        and self._browser_search_requests_enter(latest_observation)
                    ):
                        try:
                            await page.wait_for_function(
                                """previousUrl => location.href !== previousUrl || !/按.{0,6}(?:回车|enter).{0,8}(?:检索|搜索|search)|press.{0,12}enter.{0,20}search/i.test(document.body?.innerText || '')""",
                                latest_observation["url"],
                                timeout=2500,
                            )
                        except Exception:
                            pass
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=3000)
                    except Exception:
                        pass
                except Exception as error:
                    action_error = type(error).__name__
                finally:
                    self.browser_runtime.remove_page_listener(browser_session_id, record_opened_page)

                popup_rejection = None
                popup_landed_url = None
                if opened_pages:
                    official_site_goal = bool(self._browser_official_site_brand(task.goal))
                    if len(opened_pages) > 1 and official_site_goal:
                        popup_rejection = "multiple_popups_not_verified"
                        popup_landed_url = ", ".join(SensitiveRedactor.redact_url(popup.url) for popup in opened_pages)
                        for popup in opened_pages:
                            try:
                                if not popup.is_closed():
                                    await popup.close()
                            except Exception:
                                pass
                    else:
                        popup = opened_pages[-1]
                        try:
                            if popup.url == "about:blank":
                                await popup.wait_for_url(lambda url: url != "about:blank", timeout=5000)
                            await popup.wait_for_load_state("domcontentloaded", timeout=5000)
                        except Exception:
                            pass
                        if official_site_goal:
                            popup_rejection = (
                                "navigation_landed_not_trusted"
                                if popup.is_closed()
                                or self._browser_navigation_landing_rejection(
                                    task.goal,
                                    latest_observation["url"],
                                    popup.url,
                                    trusted_domains,
                                )
                                else None
                            )
                            if popup_rejection:
                                popup_landed_url = SensitiveRedactor.redact_url(popup.url)
                        if popup_rejection:
                            try:
                                if not popup.is_closed():
                                    await popup.close()
                            except Exception:
                                pass
                        elif not popup.is_closed():
                            page = popup
                            self.browser_runtime.set_active_page(browser_session_id, popup)
                            popup.on(
                                "request", lambda _request: network.__setitem__("requests", network["requests"] + 1)
                            )
                            popup.on(
                                "requestfailed", lambda _request: network.__setitem__("failed", network["failed"] + 1)
                            )
                            popup.on(
                                "response", lambda _response: network.__setitem__("responses", network["responses"] + 1)
                            )
                    if popup_rejection:
                        action_error = popup_rejection
                        stop_reason = "OFFICIAL_DOMAIN_UNVERIFIED"

                after = await self._observe_browser_page(page, network, waited_loading_states=waited_loading_states)
                duration = round((time.perf_counter() - action_started) * 1000, 1)
                state["metrics"]["browser_latency_ms"] = duration
                landing_rejection = self._browser_navigation_landing_rejection(
                    task.goal,
                    latest_observation["url"],
                    after["url"],
                    trusted_domains,
                )
                landing_rejection = popup_rejection or landing_rejection
                if landing_rejection:
                    action_error = landing_rejection
                    stop_reason = "OFFICIAL_DOMAIN_UNVERIFIED"
                cart_verified = chosen["action_type"] == "add_to_cart" and self._browser_cart_verified(
                    before_cart, after["cart"]
                )
                state_changed = after["state_hash"] != current_hash
                expected_verified = self._browser_expected_effect_observed(
                    chosen.get("expected_effect", ""),
                    " ".join([after["url"], after["title"], after["text"], after["accessibility_tree"]]),
                )
                if chosen["action_type"] == "add_to_cart":
                    effect_verified = cart_verified
                elif chosen["action_type"] in {"fill", "select"}:
                    current_element = next(
                        (item for item in after["elements"] if item.get("id") == chosen.get("target_id")), {}
                    )
                    effect_verified = (
                        bool(
                            chosen.get("value") and str(current_element.get("value") or "") == str(chosen.get("value"))
                        )
                        or state_changed
                        and expected_verified
                    )
                elif chosen["action_type"] == "inspect":
                    effect_verified = True
                else:
                    effect_verified = (state_changed or after["url"] != latest_observation["url"]) and (
                        expected_verified or not chosen.get("expected_effect")
                    )
                if action_error:
                    action_status = "failed"
                    state["metrics"]["failed_actions"] += 1
                    if stop_reason != "OFFICIAL_DOMAIN_UNVERIFIED":
                        stop_reason = "ACTION_FAILED"
                elif (
                    chosen.get("_search_submit") or chosen["action_type"] == "press_key"
                ) and self._browser_search_requests_enter(after):
                    action_status = "partial"
                    state["metrics"].setdefault("partial_actions", 0)
                    state["metrics"]["partial_actions"] += 1
                elif effect_verified:
                    action_status = "success"
                    state["metrics"]["browser_action_success"] += 1
                elif chosen["action_type"] in {"wait", "inspect"}:
                    action_status = "partial"
                    state["metrics"].setdefault("partial_actions", 0)
                    state["metrics"]["partial_actions"] += 1
                else:
                    action_status = "unexpected"
                    state["metrics"]["failed_actions"] += 1
                    stop_reason = "UNEXPECTED_STATE"
                if decision_provider == "jev" and effect_verified and action_status == "success":
                    state["metrics"]["jev_correct"] += 1
                screenshot = await self.context.artifact(
                    task,
                    "browser_agent",
                    f"browser-action-{len(state['history']) + 1:02d}.png",
                    "SCREENSHOT",
                    await page.screenshot(type="png"),
                    "image/png",
                )
                await self.context.persist_browser_agent_artifact(task.id, screenshot)
                action_result = {
                    "action": chosen["action_type"],
                    "target": chosen["target"],
                    "target_tag": selected_element.get("tag"),
                    "target_id": chosen.get("target_id"),
                    "value": chosen.get("value"),
                    "locator": selected_locator,
                    "locator_verified": bool(selected_locator)
                    or chosen["action_type"] in {"back", "scroll", "wait", "inspect"},
                    "candidate_id": chosen["candidate_id"],
                    "candidate_count": len(valid_candidates),
                    "decision_provider": decision_provider,
                    "decision_model": decision_sample["model"],
                    "decision_confidence": decision_sample["confidence"],
                    "decision_rationale": SensitiveRedactor.redact_text(
                        str(
                            (getattr(jev_result, "reason", None) if decision_provider == "jev" else fallback_reason)
                            or chosen["reason_summary"]
                        )
                    )[:500],
                    "expected_effect": chosen["expected_effect"],
                    "progress_evidence": (
                        "页面仍提示按回车键发起检索，Agent 将继续处理。"
                        if (chosen.get("_search_submit") or chosen["action_type"] == "press_key")
                        and self._browser_search_requests_enter(after)
                        else None
                    ),
                    "reason_summary": chosen["reason_summary"],
                    "risk": chosen["risk"],
                    "status": action_status,
                    "error_type": action_error,
                    "url_before": latest_observation["url"],
                    "url_after": after["url"],
                    "opened_tabs": [SensitiveRedactor.redact_url(item.url) for item in opened_pages],
                    "state_hash_before": current_hash,
                    "state_hash_after": after["state_hash"],
                    "state_changed": state_changed,
                    "expected_effect_observed": expected_verified,
                    "cart_verified": cart_verified,
                    "cart_before": before_cart if chosen["action_type"] == "add_to_cart" else None,
                    "cart_after": after["cart"] if chosen["action_type"] == "add_to_cart" else None,
                    "duration_ms": duration,
                    "screenshot_artifact_id": screenshot["artifact_id"],
                    "network": after["network"],
                }
                decision_sample["action_status"] = action_status
                decision_sample["effect_verified"] = effect_verified
                decision_sample["duration_ms"] = duration
                state["history"].append(action_result)
                state["history"] = state["history"][-20:]
                await self.context.persist_browser_agent_evidence(
                    task.id,
                    EvidenceType.SCREENSHOT,
                    "playwright.browser_agent",
                    f"{chosen['action_type']} {chosen['target']!r}: {action_status}.",
                    json.dumps(action_result, ensure_ascii=False),
                    action_result,
                    screenshot["artifact_id"],
                )
                await self.context.browser_agent_event(
                    task.id,
                    "browser.action_completed",
                    f"{action_status.title()}：{chosen['action_type']} · {chosen['target'] or '页面'}",
                    action_result["progress_evidence"] or chosen["expected_effect"],
                    status="COMPLETED" if effect_verified else "PARTIAL" if action_status == "partial" else "FAILED",
                    duration_ms=duration,
                    metadata={
                        "action": chosen["action_type"],
                        "locator": json.dumps(selected_locator, ensure_ascii=False) if selected_locator else "page",
                        "url": after["url"],
                        "artifact_id": screenshot["artifact_id"],
                        "candidate_id": chosen["candidate_id"],
                        "verified": effect_verified,
                        "expected_effect": chosen["expected_effect"],
                    },
                )
                await self.context.browser_agent_event(
                    task.id,
                    "browser.observation",
                    "已重新观察页面",
                    f"{after['title']} · {after['url']}",
                    status="COMPLETED" if state_changed else "UNEXPECTED",
                    duration_ms=duration,
                    metadata={
                        "url": after["url"],
                        "title": after["title"],
                        "state_hash": after["state_hash"],
                        "network_requests": after["network"]["requests"],
                        "network_failed": after["network"]["failed"],
                        "artifact_id": screenshot["artifact_id"],
                    },
                )
                state["current_url"] = after["url"]
                state["metrics"]["total_duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
                if landing_rejection:
                    latest_observation = after
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.official_domain_unverified",
                        "导航落地未通过可信校验，已停止 Agent",
                        "页面发生了跨域重定向、HTTPS 降级或未通过校验的新标签页；Agent 已停止。",
                        status="BLOCKED",
                        metadata={
                            "url_before": current_url,
                            "url_after": popup_landed_url or after.get("url"),
                            "trusted_domains": trusted_domains,
                        },
                    )
                    break
                if action_status in {"failed", "unexpected"}:
                    state["metrics"]["recovery_count"] += 1
                    if state["metrics"]["recovery_count"] > max_recoveries:
                        stop_reason = "ACTION_FAILED" if action_error else "UNEXPECTED_STATE"
                        latest_observation = after
                        break
                elif effect_verified:
                    state["metrics"]["recovery_count"] = max(0, state["metrics"]["recovery_count"] - 1)

                goal_completed = self._browser_goal_verified(
                    task.goal,
                    plan,
                    after,
                    state["history"],
                    criteria,
                    cart_intent,
                    trusted_domains=trusted_domains,
                )
                if goal_completed:
                    stop_reason = "OBSERVED_GOAL_EVIDENCE"
                    state["metrics"]["goal_completion"] = True
                    latest_observation = after
                    break
                if plan.goal_status == "completed" and self._browser_official_site_brand(task.goal):
                    stop_reason = "OFFICIAL_DOMAIN_UNVERIFIED"
                    latest_observation = after
                    await self.context.browser_agent_event(
                        task.id,
                        "browser.official_domain_unverified",
                        "官网域名尚未验证",
                        "请填写可信域名，并确认当前 HTTPS 主机名与之匹配后再标记完成。",
                        status="BLOCKED",
                        metadata={"url": after.get("url"), "trusted_domains": trusted_domains},
                    )
                    break

                state["pause_state_hash"] = after["state_hash"]
                await self.context.persist_browser_agent_state(
                    task.id,
                    state,
                    title="QA Agent 正在浏览网页",
                    summary=f"当前目标：{state['current_subgoal']}；最近结果：{action_status} · {chosen['target'] or chosen['action_type']}。",
                )
                latest_observation = after
                fresh, _ = await self.context.load_task(task.id)
                if fresh and fresh.status == TaskStatus.PAUSING.value:
                    state["pause_count"] = int(state.get("pause_count", 0)) + 1
                    await self.context.persist_browser_agent_state(
                        task.id,
                        state,
                        title="Agent 已在浏览器动作边界暂停",
                        summary="你可以在同一浏览器页面手动完成一步，再恢复 Agent。恢复时会重新观察当前页面。",
                        status="PAUSED",
                        event_type="browser.agent_paused",
                    )
                    return {"_pause_after_step": True, "current_url": after["url"]}

            state["metrics"]["total_duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            if stop_reason != "OFFICIAL_DOMAIN_UNVERIFIED":
                state["current_url"] = latest_observation.get("url") or state.get("current_url")
            state["stop_reason"] = stop_reason
            state["metrics"]["goal_completion"] = bool(goal_completed)
            await self.context.persist_browser_agent_state(
                task.id,
                state,
                title="浏览目标已验证" if goal_completed else "浏览 Agent 暂停并交由人工检查",
                summary=(
                    f"目标已由页面证据确认；当前 URL：{state['current_url']}"
                    if goal_completed
                    else f"停止原因：{stop_reason}；当前 URL：{state['current_url']}"
                ),
                status="COMPLETED" if goal_completed else "BLOCKED",
                event_type="browser.goal_completed" if goal_completed else "browser.goal_blocked",
            )
            sample_artifact = await self.context.artifact(
                task,
                "browser_agent",
                "jev-browser-decision-samples.json",
                "DECISION_SAMPLES",
                json.dumps(state["decision_samples"], ensure_ascii=False, indent=2).encode("utf-8"),
                "application/json",
            )
            await self.context.persist_browser_agent_artifact(task.id, sample_artifact)
            if not goal_completed:
                failure_type = (
                    stop_reason
                    if stop_reason
                    in {
                        "NO_CANDIDATE",
                        "NO_SAFE_HISTORY",
                        "HTTP_STATUS_ERROR",
                        "JEV_NO_DECISION",
                        "LOCATOR_INVALID",
                        "ACTION_FAILED",
                        "UNEXPECTED_STATE",
                        "PAGE_TIMEOUT",
                        "NAVIGATION_FAILED",
                        "LOOP_DETECTED",
                        "APPROVAL_REQUIRED",
                        "GOAL_NOT_REACHED",
                        "HUMAN_VERIFICATION_REQUIRED",
                        "PAGE_UNSTABLE",
                        "OFFICIAL_DOMAIN_UNVERIFIED",
                    }
                    else "GOAL_NOT_REACHED"
                )
                decision_failure = state["metrics"].get("last_jev_error") or "原因未记录"
                if decision_failure == "task_ai_budget_exhausted":
                    failure_type = "AI_BUDGET_EXHAUSTED"
                decision_confidence = state["metrics"].get("last_jev_confidence")
                decision_threshold = state["metrics"].get("last_jev_minimum_confidence")
                if decision_failure == "below_minimum_confidence" and decision_confidence is not None:
                    threshold = f" {decision_threshold:.2f}" if decision_threshold is not None else ""
                    jev_blocked_message = (
                        f"Jev 置信度 {decision_confidence:.2f} 低于配置阈值{threshold}；未执行浏览操作。"
                    )
                else:
                    jev_blocked_message = f"Jev 未能给出可靠决策（{decision_failure}）；未执行浏览操作。"
                message = (
                    "浏览操作需要用户确认；Agent 已停止，请在浏览器中接管。"
                    if stop_reason == "APPROVAL_REQUIRED"
                    else "没有找到可靠的下一步浏览操作。"
                    if stop_reason == "NO_CANDIDATE"
                    else (
                        "目标网站要求人工安全验证；原浏览器会话没有连接到工作台，无法在该任务中继续操作。"
                        + (
                            "验证页截图已保存。"
                            if (state.get("human_verification") or {}).get("artifact_id")
                            else "验证页文本与可访问性证据已保留。"
                        )
                        + "请从工作台的“浏览器”视图启动带项目会话的 Agent，再由人工完成验证后继续。"
                        if not (state.get("human_verification") or {}).get("resume_available")
                        else "目标网站要求人工安全验证；原浏览器会话已暂停，请完成人工验证后恢复任务。"
                    )
                    if stop_reason == "HUMAN_VERIFICATION_REQUIRED"
                    else "页面在分析期间持续变化；旧定位器已丢弃，请稍后重试或先稳定页面。"
                    if stop_reason == "PAGE_UNSTABLE"
                    else "官网身份未验证；请在自然语言操作流程中填写可信域名并保持 HTTPS，再重新运行。"
                    if stop_reason == "OFFICIAL_DOMAIN_UNVERIFIED"
                    else f"起始页面返回 HTTP {initial_http_status}；已停止，没有执行浏览操作。请检查目标网址。"
                    if stop_reason == "HTTP_STATUS_ERROR"
                    else "当前浏览任务没有观察到可安全返回的上一页；已停止，没有执行后退操作。请换用有效起始网址，或在浏览器中选择目标页面。"
                    if stop_reason == "NO_SAFE_HISTORY"
                    else jev_blocked_message
                    if stop_reason == "JEV_NO_DECISION"
                    else "页面证据尚未证明浏览目标完成。"
                )
                raise TaskBlocked(
                    message,
                    failure_type=failure_type,
                    details={
                        "current_url": state["current_url"],
                        "stop_reason": stop_reason,
                        "initial_http_status": initial_http_status if stop_reason == "HTTP_STATUS_ERROR" else None,
                        "decision_failure": decision_failure if stop_reason == "JEV_NO_DECISION" else None,
                        "jev_confidence": decision_confidence if stop_reason == "JEV_NO_DECISION" else None,
                        "jev_minimum_confidence": decision_threshold if stop_reason == "JEV_NO_DECISION" else None,
                        "jev_attempted_choice": state["metrics"].get("last_jev_attempted_choice")
                        if stop_reason == "JEV_NO_DECISION"
                        else None,
                        "action_executed": stop_reason
                        not in {"JEV_NO_DECISION", "NO_SAFE_HISTORY", "HTTP_STATUS_ERROR"},
                        "trusted_domains_required": stop_reason == "OFFICIAL_DOMAIN_UNVERIFIED",
                        "metrics": state["metrics"],
                        "manual_resume_available": bool(
                            (state.get("human_verification") or {}).get("resume_available")
                        ),
                        "verification_artifact_id": (state.get("human_verification") or {}).get("artifact_id"),
                        "decision_samples_artifact_id": sample_artifact["artifact_id"],
                    },
                )
            final_haystack = " ".join(
                [
                    str(latest_observation.get("url") or ""),
                    str(latest_observation.get("title") or ""),
                    str(latest_observation.get("text") or ""),
                    str(latest_observation.get("accessibility_tree") or ""),
                ]
            ).casefold()
            verified_text_criteria = [
                value for value in criteria if isinstance(value, str) and value.casefold() in final_haystack
            ]
            verified_completion_evidence = [
                value
                for value in plan.completion_evidence
                if isinstance(value, str) and value.strip() and value.casefold() in final_haystack
            ]
            result = {
                "verified": True,
                "kind": "ai_jev_browser_agent",
                "goal": task.goal,
                "final_url": state["current_url"],
                "final_title": latest_observation.get("title", ""),
                "goal_evidence": {
                    "source": "live_page_observation",
                    "cart_verified": bool(state["history"] and state["history"][-1].get("cart_verified")),
                    "visible_text_criteria": verified_text_criteria,
                    "completion_evidence": verified_completion_evidence,
                },
                "subgoals": state["subgoals"],
                "actions": state["history"],
                "decision_samples": state["decision_samples"],
                "decision_samples_artifact_id": sample_artifact["artifact_id"],
                "metrics": state["metrics"],
                "stop_reason": stop_reason,
                "recorder_session_id": recorder_session_id or None,
            }
            return result
        finally:
            if owns_browser_session and browser_session_id:
                await self.browser_runtime.close_session(browser_session_id)

    @staticmethod
    def _browser_repeats_same_target(history: list[dict[str, Any]], candidate: dict[str, Any]) -> bool:
        action = str(candidate.get("action_type") or "")
        if action in {"scroll", "wait", "inspect"} or len(history) < 2:
            return False
        signature = (action, candidate.get("target_id"))
        return all((item.get("action"), item.get("target_id")) == signature for item in history[-2:])

    @staticmethod
    def _browser_url_loop(urls: list[str]) -> bool:
        return len(urls) >= 5 and urls[-1] == urls[-3] == urls[-5] and urls[-2] == urls[-4] and urls[-1] != urls[-2]

    @staticmethod
    def _browser_has_safe_back_target(urls: list[str]) -> bool:
        current = urls[-1] if urls else ""
        return any(
            previous != current and urlparse(previous).scheme in {"http", "https"} and urlparse(previous).hostname
            for previous in reversed(urls[:-1])
        )

    @staticmethod
    def _browser_navigation_failure(error: Exception, requested_url: str) -> TaskBlocked:
        error_message = SensitiveRedactor.redact_text(str(error)).strip()[:500]
        reason = f" 浏览器错误：{error_message}" if error_message else ""
        return TaskBlocked(
            f"无法打开目标页面。{reason}",
            failure_type="NAVIGATION_FAILED",
            details={
                "stage": "page_navigation",
                "error_type": type(error).__name__,
                "error_message": error_message or None,
                "requested_url": SensitiveRedactor.redact_url(requested_url),
            },
        )

    @staticmethod
    def _browser_jev_needed(candidate_count: int, explicitly_required: bool) -> bool:
        """Run Jev for ambiguity, or for every action when the workflow requires it."""
        return explicitly_required or candidate_count > 1

    @staticmethod
    def _browser_official_site_brand(goal: str) -> str | None:
        match = re.search(r"([a-z0-9][a-z0-9.-]{1,40})\s*(?:官网|官方网站|official\s+(?:website|site))", goal, re.I)
        return match.group(1).casefold().strip(".-") if match else None

    @staticmethod
    def _browser_trusted_domains(value: Any) -> list[str]:
        """Normalize only explicitly configured hostnames used for official-site verification."""
        if not isinstance(value, list):
            return []
        domains = []
        for item in value[:20]:
            raw = str(item or "").strip().casefold()
            if not raw or "*" in raw or "@" in raw:
                continue
            parsed = urlparse(raw if "://" in raw else f"https://{raw}")
            host = (parsed.hostname or "").rstrip(".")
            if host and "." in host and not any(char.isspace() for char in host):
                domains.append(host.removeprefix("www."))
        return list(dict.fromkeys(domains))

    @staticmethod
    def _browser_host_matches_trusted_domain(host: str, trusted_domains: list[str]) -> bool:
        normalized = host.casefold().rstrip(".").removeprefix("www.")
        return any(normalized == domain or normalized.endswith(f".{domain}") for domain in trusted_domains)

    @staticmethod
    def _browser_is_search_source_host(host: str) -> bool:
        normalized = host.casefold().rstrip(".").removeprefix("www.")
        search_domains = (
            "baidu.com",
            "bing.com",
            "duckduckgo.com",
            "ecosia.org",
            "google.com",
            "google.co.uk",
            "google.co.jp",
            "google.com.au",
            "google.co.in",
            "google.com.br",
            "google.com.hk",
            "google.de",
            "google.fr",
            "google.ca",
            "google.es",
            "google.it",
            "startpage.com",
            "yahoo.com",
        )
        return normalized in search_domains

    @staticmethod
    def _browser_official_entry_url_allowed(url: str, trusted_domains: list[str]) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        return parsed.scheme == "https" and (
            TaskBrowserExecutor._browser_host_matches_trusted_domain(host, trusted_domains)
            or TaskBrowserExecutor._browser_is_search_source_host(host)
        )

    @staticmethod
    def _browser_navigation_target_allowed(
        goal: str, current_url: str, target_url: str, trusted_domains: list[str]
    ) -> bool:
        if not TaskBrowserExecutor._browser_official_site_brand(goal):
            return True
        current = urlparse(current_url)
        target = urlparse(target_url)
        current_host = (current.hostname or "").casefold()
        target_host = (target.hostname or "").casefold()
        if target.scheme != "https" or not current_host or not target_host:
            return False
        trusted_destination = TaskBrowserExecutor._browser_host_matches_trusted_domain(target_host, trusted_domains)
        same_verified_site = current_host.removeprefix("www.") == target_host.removeprefix("www.") and (
            TaskBrowserExecutor._browser_host_matches_trusted_domain(current_host, trusted_domains)
            or TaskBrowserExecutor._browser_is_search_source_host(current_host)
        )
        return same_verified_site or trusted_destination

    @staticmethod
    def _browser_navigation_candidate_rejection(
        goal: str,
        current_url: str,
        action_type: str,
        element: dict[str, Any],
        trusted_domains: list[str],
    ) -> str | None:
        is_navigation = action_type in {"navigate", "open_product"} or (
            action_type == "click" and element.get("tag") == "a"
        )
        if not is_navigation or not TaskBrowserExecutor._browser_official_site_brand(goal):
            return None
        target_url = str(element.get("_href") or element.get("href") or "")
        if TaskBrowserExecutor._browser_navigation_target_allowed(goal, current_url, target_url, trusted_domains):
            return None
        return "navigation_target_not_trusted"

    @staticmethod
    def _browser_navigation_landing_rejection(
        goal: str,
        url_before: str,
        url_after: str,
        trusted_domains: list[str],
    ) -> str | None:
        if not TaskBrowserExecutor._browser_official_site_brand(goal):
            return None
        before = urlparse(url_before)
        after = urlparse(url_after)
        before_host = (before.hostname or "").casefold().removeprefix("www.")
        after_host = (after.hostname or "").casefold().removeprefix("www.")
        if after.scheme == "https" and TaskBrowserExecutor._browser_host_matches_trusted_domain(
            after_host, trusted_domains
        ):
            return None
        same_search_source = before_host == after_host and TaskBrowserExecutor._browser_is_search_source_host(
            before_host
        )
        if after.scheme == "https" and same_search_source:
            return None
        return "navigation_landed_not_trusted"

    @staticmethod
    def _browser_rule_fallback_plan(
        goal: str,
        observation: dict[str, Any],
        history: list[dict[str, Any]],
        *,
        trusted_domains: list[str] | None = None,
    ) -> BrowserAgentPlan | None:
        """Offer only explicit search and official-site actions from the current page."""
        brand = TaskBrowserExecutor._browser_official_site_brand(goal)
        if brand:
            trusted_domains = trusted_domains or []
            current_url = str(observation.get("url") or "")
            current_host = (urlparse(current_url).hostname or "").casefold()
            last_action = history[-1] if history else {}
            navigated_url = str(last_action.get("url_after") or "")
            navigated_host = (urlparse(navigated_url).hostname or "").casefold()
            page_text = " ".join((str(observation.get("title") or ""), str(observation.get("text") or "")))
            if (
                last_action.get("action") == "navigate"
                and last_action.get("status") == "success"
                and navigated_host == current_host
                and urlparse(current_url).scheme == "https"
                and TaskBrowserExecutor._browser_host_matches_trusted_domain(current_host, trusted_domains)
                and re.search(re.escape(brand), str(last_action.get("target") or ""), re.I)
                and re.search(re.escape(brand), page_text, re.I)
            ):
                return BrowserAgentPlan(
                    current_subgoal=f"已打开并验证 {brand} 官网",
                    goal_status="completed",
                    completion_evidence=[current_host, brand],
                )

        elements = [
            item
            for item in observation.get("elements", [])
            if item.get("id") and item.get("visible") and item.get("enabled")
        ]
        if not elements:
            return None

        if brand:
            links = [
                item
                for item in elements
                if item.get("tag") == "a"
                and urlparse(str(item.get("_href") or item.get("href") or "")).scheme == "https"
                and TaskBrowserExecutor._browser_host_matches_trusted_domain(
                    (urlparse(str(item.get("_href") or item.get("href") or "")).hostname or "").casefold(),
                    trusted_domains,
                )
                and re.search(re.escape(brand), str(item.get("name") or item.get("text") or ""), re.I)
            ]
            unique_links = {}
            for link in links:
                host = (urlparse(str(link.get("_href") or link.get("href") or "")).hostname or "").casefold()
                unique_links.setdefault(host.removeprefix("www."), link)
            if unique_links:
                candidates = []
                for index, link in enumerate(list(unique_links.values())[:3], start=1):
                    label = str(link.get("name") or link.get("text") or brand)
                    href = str(link.get("_href") or link.get("href") or "")
                    candidates.append(
                        BrowserActionCandidate(
                            candidate_id=f"rule_official_{index}",
                            action_type="navigate",
                            target_id=str(link["id"]),
                            target=label[:200],
                            reason_summary="可见链接匹配任务明确提供的可信 HTTPS 域名。",
                            expected_effect=f"打开 {brand} 官方站点。",
                            risk="LOW",
                            evidence=[f"observed link: {label[:100]}", href[:200]],
                        )
                    )
                return BrowserAgentPlan(current_subgoal=f"打开 {brand} 官网", candidates=candidates)

        match = re.search(
            r"\b(?:search|query|look\s+up)\b\s*(?:for\s*)*[\"'“]?(.+)|(?:搜索|查询|查找)\s*(.+)",
            goal,
            re.I,
        )
        if not match:
            return None
        query = re.split(
            r"[,，。;；]|\b(?:then|and|open|visit|go\s+to)\b|然后|再|并|进入|打开|官网",
            match.group(1) or match.group(2),
            maxsplit=1,
            flags=re.I,
        )[0].strip(" \"'“”’。，;；")[:160]
        if not query:
            return None

        editable = [
            item
            for item in elements
            if item.get("tag") in {"input", "textarea"} and item.get("type") in {None, "", "text", "search"}
        ]
        search_inputs = [
            item
            for item in editable
            if item.get("type") == "search"
            or re.search(r"search|搜索|查询|查找", f"{item.get('name', '')} {item.get('placeholder', '')}", re.I)
        ]
        search_buttons = [
            item
            for item in elements
            if item.get("role") in {"button", "link"}
            and re.search(r"search|搜索|查询|查找|百度一下", str(item.get("name") or ""), re.I)
        ]
        if not search_inputs and len(editable) == 1 and len(search_buttons) == 1:
            search_inputs = editable
        search_input = search_inputs[0] if len(search_inputs) == 1 else None
        if not search_input:
            return None

        normalized_query = query.casefold()
        filled = str(search_input.get("value") or "").strip().casefold() == normalized_query or any(
            item.get("action") == "fill"
            and str(item.get("value") or "").strip().casefold() == normalized_query
            and item.get("status") in {"success", "partial"}
            for item in history[-6:]
        )
        submitted = any(
            item.get("action") == "press_key"
            or item.get("action") in {"click", "filter"}
            and re.search(r"search|搜索|查询|查找|百度一下", str(item.get("target") or ""), re.I)
            for item in history[-6:]
        )
        if submitted:
            waits = sum(item.get("action") == "wait" for item in history[-6:])
            if waits >= 2:
                return None
            action, target, value = "wait", "", "700"
            expected = "搜索结果或目标站点链接出现在当前页面。"
        elif not filled:
            action, target, value = (
                "fill",
                str(search_input.get("name") or search_input.get("placeholder") or "搜索框"),
                query,
            )
            expected = f"搜索框中显示 {query}。"
        else:
            buttons = search_buttons
            if len(buttons) > 1:
                return BrowserAgentPlan(
                    current_subgoal=f"提交 {query} 搜索",
                    candidates=[
                        BrowserActionCandidate(
                            candidate_id=f"rule_search_submit_{index}",
                            action_type="click",
                            target_id=str(item["id"]),
                            target=str(item.get("name") or "搜索")[:200],
                            reason_summary="目标搜索词已填入；此候选是当前页面观察到的搜索控件。",
                            expected_effect=f"显示 {query} 的搜索结果。",
                            risk="LOW",
                        )
                        for index, item in enumerate(buttons[:3], start=1)
                    ],
                )
            button = buttons[0] if buttons else None
            action = "click" if button else "press_key"
            target = str(button.get("name") or "搜索") if button else str(search_input.get("name") or "搜索框")
            value = None if button else "Enter"
            expected = f"显示 {query} 的搜索结果。"

        candidate = BrowserActionCandidate(
            candidate_id=f"rule_search_{action}",
            action_type=action,
            target_id=str((button if action == "click" else search_input).get("id")) if action != "wait" else None,
            target=target[:200],
            value=value,
            reason_summary="规则仅使用用户明确指定的查询词和当前页面唯一匹配的搜索控件。",
            expected_effect=expected,
            risk="LOW",
            evidence=[f"query: {query}", f"page: {observation.get('url', '')[:160]}"],
        )
        return BrowserAgentPlan(current_subgoal=f"{action} · {query}", candidates=[candidate])

    @staticmethod
    def _choose_browser_candidate(
        candidates: list[dict[str, Any]],
        preferred_candidate_id: str | None,
        *,
        jev_result: Any = None,
        jev_error: str | None = None,
    ) -> tuple[dict[str, Any], str, str | None]:
        chosen = None
        reason = None
        if jev_result and jev_result.provider == "jev" and not jev_result.fallback_used:
            if jev_result.choice == "abstain":
                reason = "jev_abstain"
            else:
                chosen = next((item for item in candidates if item["candidate_id"] == jev_result.choice), None)
                if chosen is None:
                    reason = "jev_invalid_candidate"
        else:
            reason = (jev_result.reason if jev_result else None) or jev_error or "jev_unavailable"
        if chosen:
            return chosen, "jev", None
        if len(candidates) == 1:
            return candidates[0], "single-candidate", reason or "single_candidate_no_decision_needed"
        chosen = next(
            (item for item in candidates if item["candidate_id"] == preferred_candidate_id),
            candidates[0],
        )
        provider = "ai-ranking" if chosen["candidate_id"] == preferred_candidate_id else "local-heuristic"
        return chosen, provider, reason or "jev_unavailable"

    @staticmethod
    def _browser_expected_effect_observed(expected: str, observed: str) -> bool:
        expected = str(expected or "").casefold().strip()
        if not expected:
            return False
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]{3,}|[\u4e00-\u9fff]{2,}", expected)
            if token
            not in {
                "the",
                "and",
                "with",
                "from",
                "page",
                "into",
                "detail",
                "details",
                "product",
                "results",
                "listing",
                "loaded",
                "opens",
                "appears",
                "shown",
                "visible",
                "selected",
                "now",
                "当前",
                "页面",
                "进入",
                "打开",
            }
        ]
        if not tokens:
            return expected in observed.casefold()
        haystack = observed.casefold()
        matches = sum(token in haystack for token in tokens)
        return matches >= min(2, len(tokens)) and matches / len(tokens) >= 0.5

    @staticmethod
    def _browser_goal_verified(
        goal: str,
        plan: BrowserAgentPlan,
        observation: dict[str, Any],
        history: list[dict[str, Any]],
        criteria: list[str],
        cart_intent: bool,
        *,
        trusted_domains: list[str] | None = None,
    ) -> bool:
        if TaskBrowserExecutor._browser_official_site_brand(goal):
            current_url = urlparse(str(observation.get("url") or ""))
            host = (current_url.hostname or "").casefold()
            if current_url.scheme != "https" or not TaskBrowserExecutor._browser_host_matches_trusted_domain(
                host, trusted_domains or []
            ):
                return False
        haystack = " ".join(
            [str(observation.get("url") or ""), str(observation.get("title") or ""), str(observation.get("text") or "")]
        ).casefold()
        if cart_intent:
            return any(item.get("action") == "add_to_cart" and item.get("cart_verified") is True for item in history)
        if criteria:
            return bool(history) and all(value.casefold() in haystack for value in criteria)
        completion_visible = any(
            str(value).strip().casefold() in haystack for value in plan.completion_evidence if str(value).strip()
        )
        goal_tokens = [
            token
            for token in re.findall(r"[a-z0-9]{3,}|[\u4e00-\u9fff]{2,}", goal.casefold())
            if token
            not in {
                "please",
                "open",
                "find",
                "show",
                "with",
                "from",
                "this",
                "that",
                "the",
                "and",
                "for",
                "添加",
                "打开",
                "进入",
                "找到",
                "一个",
                "一下",
            }
        ]
        goal_visible = bool(goal_tokens) and all(token in haystack for token in goal_tokens)
        return bool(
            history
            and history[-1].get("status") == "success"
            and plan.goal_status == "completed"
            and (completion_visible or goal_visible)
        )

    async def _browser_inspect(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        url = str(self.context.input(task, "url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise TaskBlocked("Browser exploration requires an http(s) URL without embedded credentials.")
        recorder_state = await self.context.recorder_storage_state(task)
        browser_session = await self.browser_runtime.create_session(storage_state=recorder_state)
        try:
            http_status = await self.browser_runtime.navigate(browser_session.id, url, timeout_ms=20_000)
            snapshot = await self.browser_runtime.snapshot(browser_session.id, full_page=True)
            candidates = snapshot.controls
            for candidate in candidates:
                candidate["risk"] = classify_browser_action(
                    "click",
                    name=candidate.get("name", ""),
                    tag=candidate.get("tag", ""),
                    href=candidate.get("href") or "",
                    input_type=candidate.get("type", ""),
                )
                candidate["safe"] = candidate["risk"] in {"READ_ONLY", "SAFE_INTERACTION"}
            artifact = await self.context.artifact(
                task, "inspect", "page.png", "SCREENSHOT", snapshot.screenshot or b"", "image/png"
            )
            return {
                "url": snapshot.url,
                "title": snapshot.title,
                "http_status": http_status,
                "accessibility_tree": snapshot.accessibility_tree,
                "candidates": candidates,
                "screenshot_artifact_id": artifact["artifact_id"],
                "_artifacts": [artifact],
                "_evidence": [
                    await self.context.evidence(
                        task,
                        "inspect",
                        EvidenceType.ACCESSIBILITY_TREE,
                        "browser_runtime.snapshot",
                        f"Page {snapshot.title!r} at {snapshot.url}; {len(candidates)} interactive candidates.",
                        snapshot.accessibility_tree,
                        {
                            "url": snapshot.url,
                            "title": snapshot.title,
                            "http_status": http_status,
                            "recorder_state_applied": recorder_state is not None,
                        },
                    ),
                    await self.context.evidence(
                        task,
                        "inspect",
                        EvidenceType.DOM_SNAPSHOT,
                        "browser_runtime.snapshot",
                        "Visible page text snapshot.",
                        snapshot.text,
                        {"candidate_count": len(candidates)},
                    ),
                    await self.context.evidence(
                        task,
                        "inspect",
                        EvidenceType.RUNTIME_METADATA,
                        "browser_runtime.navigate",
                        "Browser navigation completed.",
                        None,
                        {"requested_url": url, "final_url": snapshot.url, "http_status": http_status},
                    ),
                ],
            }
        finally:
            await self.browser_runtime.close_session(browser_session.id)

    async def _decision_select(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        observed = outputs.get("inspect", {})
        observed_controls = [
            item
            for item in observed.get("candidates", [])
            if item.get("safe") and item.get("role") and item.get("name")
        ]
        trace_run_id = uuid4().hex
        raw_candidates = [
            {
                "kind": "role",
                "value": str(item["role"]),
                "name": str(item["name"])[:180],
                "exact": True,
                "task_candidate_index": int(item["index"]),
                "evidence": {"uniqueness": True},
            }
            for item in observed_controls
        ]
        event = {
            "tag": "control",
            "action": "click",
            "url": SensitiveRedactor.redact_url(str(observed.get("url") or ""))[:500],
            "target": {"task_goal": task.goal[:500], "accessible_name": "safe page action", "action": "inspect"},
            "context": {"page_title": str(observed.get("title") or "")[:200], "task_goal": task.goal[:500]},
            "candidates": raw_candidates,
        }
        if not raw_candidates:
            event_trace = make_trace_event(
                trace_run_id,
                "decision_completed",
                stage="decision",
                title="Local Strategy found no safe candidate",
                metadata={"provider": "local-strategy", "candidate_count": 0, "verified": False},
            )
            await self.context.record_ai_trace(task.id, event_trace)
            return {
                "choice": "none",
                "candidate": None,
                "provider": "local-strategy",
                "confidence": None,
                "rationale": "No safe named control was observed.",
                "_decision": {
                    "name": "explore_next_action",
                    "provider": "local-strategy",
                    "choice": "none",
                    "confidence": None,
                    "rationale": "No safe named control was observed.",
                },
                "_evidence": [],
            }

        from app.services.locator_decision_service import LocatorDecisionService

        can_call_provider = await self.ai_service.reserve_ai_call(task.id)
        decision_provider = self.decision_service.locator_provider(budget_available=can_call_provider)
        pipeline = LocatorDecisionService(
            decision_service=decision_provider,
            repository_scope=self.context.repository_scope,
        )
        candidates = LocatorDecisionService.generate_candidates(event)
        try:
            selection = await self._run_locator_decision(task, observed, event, candidates, pipeline, trace_run_id)
        except Exception as error:
            selection = None
            logger.info(
                "Browser locator verification unavailable task_id=%s error_type=%s error=%s",
                task.id,
                type(error).__name__,
                SensitiveRedactor.redact_text(str(error))[:300],
            )

        if selection:
            for item in selection["trace"]:
                await self.context.record_ai_trace(task.id, item)
        selected_candidate = (selection or {}).get("selected_candidate")
        summary = (selection or {}).get("summary") or {"engine": "Local Strategy", "verified": False}
        if not summary.get("verified"):
            selected_candidate = None
        original = next(
            (
                item
                for item in observed_controls
                if selected_candidate and int(item["index"]) == selected_candidate.get("task_candidate_index")
            ),
            None,
        )
        provider = "jev" if summary.get("engine") == "Jev" else "local-strategy"
        confidence = summary.get("confidence") if provider == "jev" else None
        rationale = (
            f"{summary.get('engine', 'Local Strategy')} selected and Playwright verified {summary.get('candidate_id')}."
            if original
            else "No candidate passed Playwright verification."
        )
        if provider == "jev":
            async with self.context.repository_scope() as repositories:
                repo = repositories.tasks
                fresh = await repo.get(task.id)
                if fresh:
                    await repo.update_context(task.id, jev_calls=int((fresh.context or {}).get("jev_calls", 0)) + 1)
                    await repositories.commit()
        if original:
            final_event = make_trace_event(
                trace_run_id,
                "decision_completed",
                stage="decision",
                title=f"{summary['engine']} selected and verified action",
                message=f"{original.get('role')} {original.get('name')}",
                metadata={
                    "provider": provider,
                    "model": summary.get("model"),
                    "latency_ms": summary.get("latency_ms"),
                    "candidate_id": summary.get("candidate_id"),
                    "candidate_count": summary.get("candidate_count"),
                    "confidence": confidence,
                    "verified": True,
                    "selected_action": {"role": original.get("role"), "name": original.get("name")},
                },
            )
            await self.context.record_ai_trace(task.id, final_event)
        decision = {
            "name": "explore_next_action",
            "provider": provider,
            "choice": str(original.get("index")) if original else "none",
            "confidence": confidence,
            "rationale": rationale,
            "candidate_id": summary.get("candidate_id"),
            "verified": bool(original),
            "model": summary.get("model") if provider == "jev" else None,
            "latency_ms": summary.get("latency_ms") if provider == "jev" else None,
        }
        return {
            "choice": decision["choice"],
            "candidate": original,
            "provider": provider,
            "confidence": confidence,
            "rationale": rationale,
            "_decision": {key: decision[key] for key in ("name", "provider", "choice", "confidence", "rationale")},
            "_evidence": [
                await self.context.evidence(
                    task,
                    "decide",
                    EvidenceType.LOCATOR_CANDIDATES,
                    "locator_decision_service",
                    f"{summary.get('engine', 'Local Strategy')} selected candidate {summary.get('candidate_id')}; verified={bool(original)}.",
                    json.dumps(
                        [
                            {
                                "candidate_id": item["candidate_id"],
                                "locator": item["locator"],
                                "static_score": item["static_score"],
                            }
                            for item in candidates
                        ],
                        ensure_ascii=False,
                    ),
                    {"provider": provider, "verified": bool(original), "candidate_id": summary.get("candidate_id")},
                )
            ],
        }

    async def _run_locator_decision(self, task, observed, event, candidates, pipeline, trace_run_id):
        browser_session_id = observed.get("_browser_session_id")
        if browser_session_id:
            return await pipeline.decide(
                run_id=trace_run_id,
                event=event,
                candidates=candidates,
                browser_session_id=browser_session_id,
                step_id=f"task:{task.id}",
            )
        url = str(observed.get("url") or "")
        recorder_state = await self.context.recorder_storage_state(task)
        browser_session = await self.browser_runtime.create_session(storage_state=recorder_state)
        try:
            await self.browser_runtime.navigate(browser_session.id, url, timeout_ms=12_000)
            return await pipeline.decide(
                run_id=trace_run_id,
                event=event,
                candidates=candidates,
                browser_session_id=browser_session.id,
                step_id=f"task:{task.id}",
            )
        finally:
            await self.browser_runtime.close_session(browser_session.id)

    async def _browser_act(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        selected = outputs.get("decide", {}).get("candidate")
        inspected = outputs.get("inspect", {})
        if not selected:
            return {"action": "skipped", "reason": "No safe candidate was available."}
        if not selected.get("safe"):
            raise TaskBlocked("The selected browser action is not classified as safe.")
        risk = classify_browser_action(
            "click",
            name=selected.get("name", ""),
            tag=selected.get("tag", ""),
            href=selected.get("href") or "",
            input_type=selected.get("type", ""),
        )
        if risk not in {"READ_ONLY", "SAFE_INTERACTION"}:
            raise TaskBlocked(f"Browser action requires explicit approval: {risk}.")
        recorder_state = await self.context.recorder_storage_state(task)
        from app.services.locator_decision_service import LocatorDecisionService

        browser_session = await self.browser_runtime.create_session(storage_state=recorder_state)
        try:
            await self.browser_runtime.navigate(browser_session.id, inspected["url"], timeout_ms=20_000)
            page = await self.browser_runtime.get_page(browser_session.id)
            observed_steps, evidence, artifacts = [], [], []
            visited = set()
            criteria = self.context.input(task, "observable_text_criteria", [])
            criteria = [str(value)[:200] for value in criteria[:10]] if isinstance(criteria, list) else []
            max_actions = max(1, min(3, int(self.context.input(task, "max_browser_actions", 3))))
            stop_reason = "action_limit_reached"
            goal_validated = False
            for index in range(max_actions):
                role, name = selected.get("role"), selected.get("name")
                risk = classify_browser_action(
                    "click",
                    name=name or "",
                    tag=selected.get("tag", ""),
                    href=selected.get("href") or "",
                    input_type=selected.get("type", ""),
                )
                if risk not in {"READ_ONLY", "SAFE_INTERACTION"}:
                    stop_reason = "approval_required"
                    break
                key = (page.url, role, name)
                if key in visited:
                    stop_reason = "repeated_action"
                    break
                visited.add(key)
                started = time.perf_counter()
                candidate = {"kind": "role", "value": role, "name": name, "exact": True}
                verification = await self.browser_runtime.verify_locator(
                    browser_session.id, candidate, {"action": "click"}
                )
                if not verification["verified"]:
                    stop_reason = "candidate_verification_failed"
                    break
                before_url = page.url
                await self.browser_runtime.execute_action(
                    browser_session.id,
                    candidate,
                    {"type": "click", "timeout_ms": 10_000},
                )
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                title = await page.title()
                text = (await page.locator("body").inner_text())[:6000]
                screenshot = await self.context.artifact(
                    task,
                    "act",
                    f"observe-{index + 1}.png",
                    "SCREENSHOT",
                    await page.screenshot(type="png"),
                    "image/png",
                )
                artifacts.append(screenshot)
                goal_validated = bool(criteria) and all(value in text for value in criteria)
                observation = {
                    "step": index + 1,
                    "action": "click",
                    "risk": risk,
                    "locator": LocatorDecisionService.format_locator(candidate),
                    "from_url": before_url,
                    "url": page.url,
                    "title": title,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "status": "PASSED",
                    "goal_validated": goal_validated,
                    "screenshot_artifact_id": screenshot["artifact_id"],
                }
                observed_steps.append(observation)
                evidence.append(
                    await self.context.evidence(
                        task,
                        "act",
                        EvidenceType.RUNTIME_METADATA,
                        "playwright.safe_click",
                        f"Observed safe action {index + 1}: {role} {name!r}.",
                        text,
                        observation,
                        screenshot["artifact_id"],
                    )
                )
                await self.context.record_ai_trace(
                    task.id,
                    {
                        "type": "browser.observation",
                        "stage": "observe",
                        "title": f"Observed browser action {index + 1}",
                        "metadata": observation,
                    },
                )
                if goal_validated:
                    stop_reason = "explicit_observation_criteria_matched"
                    break
                if index + 1 == max_actions:
                    break
                candidates = await page.locator("a[href],button,[role=button],[role=link]").evaluate_all(
                    r"""els => els.slice(0,60).map((el,index) => ({index,tag:el.tagName.toLowerCase(),role:el.getAttribute('role') || (el.tagName==='A'?'link':'button'),name:(el.innerText || el.getAttribute('aria-label') || '').trim().replace(/\s+/g,' ').slice(0,120),href:el.getAttribute('href'),type:el.getAttribute('type') || ''}))"""
                )
                for item in candidates:
                    item["risk"] = classify_browser_action(
                        "click",
                        name=item["name"],
                        tag=item["tag"],
                        href=item["href"] or "",
                        input_type=item["type"],
                    )
                    item["safe"] = (
                        item["risk"] in {"READ_ONLY", "SAFE_INTERACTION"}
                        and (page.url, item["role"], item["name"]) not in visited
                    )
                decision = await self._decision_select(
                    task,
                    {
                        "inspect": {
                            "url": page.url,
                            "title": title,
                            "candidates": candidates,
                            "_browser_session_id": browser_session.id,
                        }
                    },
                )
                selected = decision.get("candidate")
                if not selected:
                    stop_reason = "no_verified_safe_candidate"
                    break
            return {
                "action": "clicked" if observed_steps else "skipped",
                "goal_validated": goal_validated,
                "validation_scope": "explicit_observed_text" if criteria else "observations_only",
                "stop_reason": stop_reason,
                "url": page.url,
                "title": await page.title(),
                "steps": observed_steps,
                "_evidence": evidence,
                "_artifacts": artifacts,
            }
        finally:
            await self.browser_runtime.close_session(browser_session.id)

    async def _browser_verify(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        before = outputs.get("inspect", {})
        after = outputs.get("act", {})
        explicit_criteria = after.get("validation_scope") == "explicit_observed_text"
        verified = bool(
            before.get("title") and after.get("steps") and (not explicit_criteria or after.get("goal_validated"))
        )
        if not verified:
            raise TaskBlocked("Browser observations did not satisfy the requested goal criteria.")
        return {
            "verified": verified,
            "kind": "browser_exploration",
            "initial_url": before.get("url"),
            "initial_title": before.get("title"),
            "action_result": after,
            "observations": 1 + len(after.get("steps", [])),
            "goal_validated": after.get("goal_validated", False),
            "validation_scope": after.get("validation_scope", "observations_only"),
            "result": "COMPLETED" if verified else "INCOMPLETE",
        }

    async def _execute_browser_candidate(self, browser_session_id: str, candidate: dict[str, Any]) -> None:
        action = candidate["action_type"]
        element = candidate.get("_element") or {}
        locator_data = candidate.get("locator") or {}
        kind = str(locator_data.get("kind") or "")
        value = str(locator_data.get("value") or "")
        locator = {
            "kind": kind,
            "value": value,
            "name": locator_data.get("name"),
            "exact": locator_data.get("exact", True),
        }
        if kind == "id":
            locator = {**locator, "kind": "css", "value": f"[id={json.dumps(value)}]"}
        if action == "inspect":
            return
        if action == "navigate":
            target = str(element.get("_href") or element.get("href") or "")
            parsed = urlparse(target)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise TaskBlocked("观察到的链接不是安全的 http(s) 目标。", failure_type="NAVIGATION_FAILED")
            await self.browser_runtime.execute_action(
                browser_session_id, {}, {"type": "navigate", "url": target, "timeout_ms": 20_000}
            )
            return
        if action in {"click", "open_product", "filter", "choose_variant", "add_to_cart"}:
            operation = (
                "select" if action in {"filter", "choose_variant"} and element.get("tag") == "select" else "click"
            )
            payload = candidate.get("value") if operation == "select" else None
        elif action == "fill":
            operation, payload = "fill", str(candidate.get("value") or "")[:300]
        elif action == "press_key":
            if candidate.get("value") != "Enter":
                raise TaskBlocked("键盘操作仅允许对已验证的搜索框按 Enter。", failure_type="AI_OUTPUT_INVALID")
            operation, payload = "press", "Enter"
        elif action == "select":
            operation, payload = "select", candidate.get("value")
        elif action == "hover":
            operation, payload = "hover", None
        elif action == "scroll":
            operation, payload = "scroll", str(candidate.get("value") or "down").lower()
        elif action == "wait":
            try:
                payload = max(100, min(5000, int(candidate.get("value") or 700)))
            except (ValueError, TypeError):
                payload = 700
            operation = "wait"
        elif action == "back":
            operation, payload = "back", None
        else:
            raise TaskBlocked("AI 提议了不支持的浏览动作。", failure_type="AI_OUTPUT_INVALID")
        await self.browser_runtime.execute_action(
            browser_session_id,
            locator,
            {"type": operation, "value": payload, "timeout_ms": 10_000},
        )
