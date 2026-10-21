from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from qa_core.ai.models import DiscoveryScenarioAnalysis
from qa_core.ai.provider import AIProviderError
from qa_core.failure.redactor import SensitiveRedactor

from app.domain.task_records import TaskRecord as TaskExecutionRecord
from app.services.discovery_evidence_analysis import CANDIDATE_GAP, UNDETERMINED, evidence_kind_facts
from app.services.discovery_evidence_capture import stable_identity
from app.services.task_ai_service import TaskAIService
from app.services.task_decision_service import TaskDecisionService
from app.services.task_errors import TaskBlocked
from app.services.task_execution_ports import TaskExecutionPorts

ANALYZED_SCENARIO_STATUSES = {CANDIDATE_GAP, UNDETERMINED}
MAX_EVIDENCE_PER_PROMPT = 12
MAX_CASES_PER_PROMPT = 12
MAX_SCENARIOS_PER_TASK = 5
SUFFICIENT_MIN_ROWS = 3


def digest(value: Any) -> str:
    """Stable hash of whatever the answer depends on, so an identical request is recognisable."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:32]


def sufficiency_from_rules(evidence_rows: int, kinds: list[str], associated: int, truncated: bool) -> str:
    """A deterministic reading of how much evidence exists; never derived from the model's own words."""
    if evidence_rows == 0:
        return "insufficient"
    if evidence_rows >= SUFFICIENT_MIN_ROWS and (associated > 0 or len(kinds) >= 2) and not truncated:
        return "sufficient"
    return "thin"


class TaskDiscoveryIntelligenceService:
    """Ask AI/Jev about the scenarios the deterministic matcher could not settle.

    The rule verdict stays untouched: a suggestion only records what the model read, what it
    proposed and how a human decided. Nothing here writes a test case or a source file.
    """

    def __init__(
        self,
        ports: TaskExecutionPorts,
        *,
        ai_service: TaskAIService,
        decision_service: TaskDecisionService,
    ) -> None:
        self.ports = ports
        self.ai_service = ai_service
        self.decision_service = decision_service

    async def _collect_gaps(self, task: TaskExecutionRecord, _outputs: dict[str, Any]) -> dict[str, Any]:
        run_id = str(task.inputs.get("discovery_run_id") or "").strip()
        if not run_id:
            raise TaskBlocked("A Quality Discovery run id is required.")
        async with self.ports.repository_scope() as repositories:
            run = await repositories.discovery.get(run_id)
            if run is None:
                raise TaskBlocked("The Quality Discovery run does not exist.")
            if (task.project_id and run.project_id != task.project_id) or run.status not in {
                "COMPLETED",
                "BLOCKED",
                "STOPPED",
                "FAILED",
                "BUDGET_EXHAUSTED",
            }:
                raise TaskBlocked("Only a finished Quality Discovery run can be analysed.")
            scenarios = await repositories.discovery_evidence.list_scenarios(run_id)
            evidence = await repositories.discovery_evidence.list_by_run(run_id, limit=4000)
            cases = await repositories.test_cases.list_by_project(run.project_id, limit=400)
        by_id = {row.evidence_id: row for row in evidence}
        run_evidence = set(by_id)
        requested = {str(item) for item in (task.inputs.get("scenario_ids") or [])}
        selected = [
            scenario
            for scenario in scenarios
            if str(scenario.coverage_status) in ANALYZED_SCENARIO_STATUSES
            or (requested and scenario.scenario_id in requested)
        ]
        selected.sort(key=lambda row: (str(row.coverage_status), str(row.scenario_id)))
        selected = selected[:MAX_SCENARIOS_PER_TASK]
        collected = []
        for scenario in selected:
            cited = [evidence_id for evidence_id in (scenario.evidence_ids or []) if evidence_id in run_evidence]
            collected.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "title": scenario.title,
                    "url_template": scenario.url_template,
                    "coverage_status": scenario.coverage_status,
                    "match_method": scenario.match_method,
                    "note": scenario.note,
                    "evidence_ids": cited,
                    "test_case_ids": list(scenario.test_case_ids or []),
                    "page_summary": self._page_summary(by_id, cited),
                    "evidence": [self._evidence_facts(by_id[evidence_id]) for evidence_id in cited],
                    "truncated": len(cited) > MAX_EVIDENCE_PER_PROMPT,
                }
            )
        return {
            "run_id": run_id,
            "project_id": run.project_id,
            "scenarios": collected,
            "considered_scenarios": len(selected),
            "unsettled_scenarios": len(
                [row for row in scenarios if str(row.coverage_status) in ANALYZED_SCENARIO_STATUSES]
            ),
            "evidence_rows": len(evidence),
            "cases": [
                {
                    "id": row.id,
                    "title": row.title,
                    "file_path": row.binding.file_path if row.binding else None,
                }
                for row in cases
                if row.id and row.title
            ][:400],
        }

    async def _analyze_gaps(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        collected = outputs.get("collect") or {}
        scenarios: list[dict[str, Any]] = list(collected.get("scenarios") or [])
        if not scenarios:
            return {"analyzed": 0, "completed": 0, "failed": 0, "skipped": 0, "suggestions": []}
        run_id = str(collected.get("run_id"))
        project_id = str(collected.get("project_id"))
        provider, model = self._provider_label()
        case_index = {row["id"]: row for row in collected.get("cases") or []}
        records: list[dict[str, Any]] = []
        for scenario in scenarios:
            start = time.perf_counter()
            input_hash = digest(
                {
                    "scenario": scenario["scenario_id"],
                    "status": scenario["coverage_status"],
                    "evidence": sorted(scenario["evidence_ids"]),
                    "cases": sorted(scenario["test_case_ids"]),
                    "provider": provider,
                    "model": model,
                    "prompt": "discovery_suggestion@v1.0",
                    "reanalyze": task.inputs.get("reanalyze_token"),
                }
            )
            suggestion_id = stable_identity("sugg", f"{scenario['scenario_id']}|{input_hash}")
            if not scenario["evidence"]:
                records.append(
                    {
                        "suggestion_id": suggestion_id,
                        "scenario_id": scenario["scenario_id"],
                        "input_hash": input_hash,
                        "analysis_status": "INSUFFICIENT_EVIDENCE",
                        "provider": provider,
                        "model": model,
                        "evidence_ids": [],
                        "related_case_ids": [],
                        "payload": {
                            "is_gap": None,
                            "reason": "No captured evidence was cited by this scenario, so no reading was attempted.",
                            "coverage_status": scenario["coverage_status"],
                            "fingerprint": "insufficient",
                        },
                        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                        "token_source": "not_requested",
                    }
                )
                continue
            prompt = self._prompt(scenario, case_index)
            try:
                response = await self.ai_service.analyze_discovery_scenario(task, prompt)
            except TaskBlocked:
                raise
            except (AIProviderError, TimeoutError) as error:
                records.append(
                    {
                        "suggestion_id": suggestion_id,
                        "scenario_id": scenario["scenario_id"],
                        "input_hash": input_hash,
                        "analysis_status": "FAILED",
                        "provider": provider,
                        "model": model,
                        "evidence_ids": [],
                        "related_case_ids": [],
                        "payload": {
                            "is_gap": None,
                            "fingerprint": "failed",
                            "coverage_status": scenario["coverage_status"],
                        },
                        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                        "error_type": type(error).__name__,
                        "error_detail": SensitiveRedactor.redact_text(str(error))[:400],
                        "token_source": "unknown",
                    }
                )
                continue
            record = self._validated(
                scenario,
                response,
                suggestion_id=suggestion_id,
                input_hash=input_hash,
                case_index=case_index,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            records.append(record)
        async with self.ports.repository_scope() as repositories:
            counts = await repositories.discovery_suggestions.upsert_many(run_id, project_id, records)
            await repositories.commit()
        return {
            "analyzed": len(records),
            "completed": len([row for row in records if row["analysis_status"] == "COMPLETED"]),
            "failed": len([row for row in records if row["analysis_status"] == "FAILED"]),
            "rejected": len([row for row in records if row["analysis_status"] == "REJECTED"]),
            "insufficient": len([row for row in records if row["analysis_status"] == "INSUFFICIENT_EVIDENCE"]),
            "skipped": 0,
            "write": counts,
            "suggestions": [
                {
                    "suggestion_id": row["suggestion_id"],
                    "scenario_id": row["scenario_id"],
                    "status": row["analysis_status"],
                }
                for row in records
            ],
        }

    async def _grade_suggestions(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        analysed = outputs.get("analyze") or {}
        run_id = str(task.inputs.get("discovery_run_id") or "")
        graded = 0
        fallbacks = 0
        if not analysed.get("suggestions"):
            return {"graded": 0, "fallbacks": 0, "grades": []}
        async with self.ports.repository_scope() as repositories:
            rows = await repositories.discovery_suggestions.list_by_run(run_id, limit=200)
        targets = [row for row in rows if row.analysis_status == "COMPLETED"][-MAX_SCENARIOS_PER_TASK:]
        grades = []
        for row in targets:
            payload = row.payload or {}
            kinds = sorted({str(item) for item in (payload.get("evidence_kinds") or [])})
            associated = int(payload.get("associated_requests") or 0)
            truncated = bool(payload.get("truncated"))
            rule_grade = sufficiency_from_rules(len(row.evidence_ids or []), kinds, associated, truncated)
            jev = await self._jev_grade(
                task,
                run_id=run_id,
                row=row,
                payload=payload,
                kinds=kinds,
                associated=associated,
                truncated=truncated,
                rule_grade=rule_grade,
            )
            async with self.ports.repository_scope() as repositories:
                await repositories.discovery_suggestions.set_jev(run_id, row.suggestion_id, jev)
                await repositories.commit()
            graded += 1
            fallbacks += 1 if jev.get("fallback_used") else 0
            grades.append({"suggestion_id": row.suggestion_id, "status": jev.get("status"), "grade": jev.get("grade")})
        return {"graded": graded, "fallbacks": fallbacks, "grades": grades}

    async def _summarize_task(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        run_id = str(task.inputs.get("discovery_run_id") or "")
        async with self.ports.repository_scope() as repositories:
            by_status = await repositories.discovery_suggestions.counts_by_status(run_id)
            by_review = await repositories.discovery_suggestions.counts_by_review(run_id)
        analyzed = outputs.get("analyze") or {}
        return {
            "run_id": run_id,
            "considered": (outputs.get("collect") or {}).get("considered_scenarios", 0),
            "by_status": by_status,
            "by_review": by_review,
            "pending_review": by_review.get("PENDING", 0),
            "accepted": by_review.get("ACCEPTED", 0),
            "rejected": by_review.get("REJECTED", 0),
            "failed_analyses": analyzed.get("failed", 0),
            "rejected_answers": analyzed.get("rejected", 0),
            "insufficient_evidence": analyzed.get("insufficient", 0),
        }

    def _validated(
        self,
        scenario: dict[str, Any],
        response: Any,
        *,
        suggestion_id: str,
        input_hash: str,
        case_index: dict[str, dict[str, Any]],
        duration_ms: float,
    ) -> dict[str, Any]:
        """Reject an answer that cites something the database does not hold."""
        base = {
            "suggestion_id": suggestion_id,
            "scenario_id": scenario["scenario_id"],
            "input_hash": input_hash,
            "provider": response.provider,
            "model": response.model,
            "duration_ms": duration_ms,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "token_source": "provider" if response.output_tokens else "unknown",
            "invocation_id": response.invocation_id,
            "task_id": None,
        }
        if response.fallback_used or response.provider in {"fake", "fallback"}:
            return {
                **base,
                "analysis_status": "DEGRADED",
                "evidence_ids": [],
                "related_case_ids": [],
                "payload": {
                    "is_gap": None,
                    "grounded": None,
                    "coverage_status": scenario["coverage_status"],
                    "fingerprint": "degraded",
                    "reason": "The AI provider answered from its fallback path, so nothing was proposed.",
                },
                "error_type": "AI_FALLBACK",
                "error_detail": "The provider reported a fallback answer.",
            }
        try:
            analysis = (
                DiscoveryScenarioAnalysis.model_validate(response.structured_data) if response.structured_data else None
            )
        except ValueError:
            analysis = None
        if analysis is None:
            return {
                **base,
                "analysis_status": "FAILED",
                "evidence_ids": [],
                "related_case_ids": [],
                "payload": {"is_gap": None, "coverage_status": scenario["coverage_status"], "fingerprint": "invalid"},
                "error_type": "AI_OUTPUT_INVALID",
                "error_detail": "The provider returned no structured analysis.",
            }
        cited = list(dict.fromkeys(str(item) for item in analysis.evidence_ids))
        citable = {str(item["id"]) for item in scenario["evidence"]}
        unknown = [item for item in cited if item not in citable]
        unknown_cases = [item for item in analysis.related_test_case_ids if item not in case_index]
        if unknown or unknown_cases:
            return {
                **base,
                "analysis_status": "REJECTED",
                "evidence_ids": [],
                "related_case_ids": [],
                "payload": {
                    "is_gap": None,
                    "coverage_status": scenario["coverage_status"],
                    "fingerprint": "rejected",
                    "unknown_evidence_ids": unknown[:10],
                    "unknown_test_case_ids": unknown_cases[:10],
                    "reason": "The answer cited a reference that does not exist, so it was not kept.",
                },
                "error_type": "UNKNOWN_EVIDENCE" if unknown else "UNKNOWN_TEST_CASE",
                "error_detail": f"unknown evidence: {unknown[:5]}, unknown cases: {unknown_cases[:5]}"[:400],
            }
        related = [case_index[item]["id"] for item in analysis.related_test_case_ids if item in case_index]
        kinds = sorted({str(item["kind"]) for item in scenario["evidence"] if str(item["id"]) in set(cited)})
        payload = {
            "is_gap": bool(analysis.is_gap),
            "summary": analysis.summary,
            "reasoning": analysis.reasoning,
            "grounded": True,
            "suggested_title": analysis.suggested_title,
            "suggested_steps": [step.model_dump() for step in analysis.suggested_steps],
            "uncertainty": analysis.uncertainty,
            "needs_human_review": bool(analysis.needs_human_review),
            "risk": analysis.risk,
            "coverage_status": scenario["coverage_status"],
            "match_method": scenario["match_method"],
            "scenario_title": scenario["title"],
            "url_template": scenario["url_template"],
            "evidence_kinds": kinds,
            "associated_requests": int(self._associated_requests(scenario) or 0),
            "truncated": bool(scenario.get("truncated")),
            "source": "ai",
        }
        payload["fingerprint"] = digest(
            {
                "is_gap": payload["is_gap"],
                "summary": payload["summary"],
                "reasoning": payload["reasoning"],
                "title": payload["suggested_title"],
                "steps": payload["suggested_steps"],
                "uncertainty": payload["uncertainty"],
                "evidence": cited,
                "cases": related,
            }
        )
        return {
            **base,
            "analysis_status": "COMPLETED",
            "evidence_ids": cited,
            "related_case_ids": related,
            "payload": payload,
            "error_type": None,
            "error_detail": None,
        }

    @staticmethod
    def _associated_requests(scenario: dict[str, Any]) -> int:
        return len(
            [
                item
                for item in scenario["evidence"]
                if item["kind"] == "network_request" and (item["payload"] or {}).get("action_evidence_id")
            ]
        )

    async def _jev_grade(
        self,
        task: TaskExecutionRecord,
        *,
        run_id: str,
        row: Any,
        payload: dict[str, Any],
        kinds: list[str],
        associated: int,
        truncated: bool,
        rule_grade: str,
    ) -> dict[str, Any]:
        from project_model.models import DecisionSignalRequest

        from app.services.jev_provider import DecisionProviderError

        record: dict[str, Any] = {
            "source": "rules",
            "status": "NOT_REQUESTED",
            "fallback_used": False,
            "calibrated": False,
            "rules": {
                "evidence_rows": len(row.evidence_ids or []),
                "kinds": kinds,
                "associated_requests": associated,
                "truncated": truncated,
            },
            "rule_grade": rule_grade,
            "grade": rule_grade,
        }
        state = (
            f"Scenario: {payload.get('scenario_title') or row.scenario_id}\n"
            f"Rule verdict: {payload.get('coverage_status')} ({payload.get('match_method') or 'no rule match'})\n"
            f"Observed action: {payload.get('summary') or 'not captured'}\n"
            f"Cited evidence rows: {len(row.evidence_ids or [])} of kinds {', '.join(kinds) or 'none'}\n"
            f"Requests tied to the action: {associated}\n"
            f"Collection truncated: {'yes' if truncated else 'no'}\n"
            f"Model uncertainty: {payload.get('uncertainty') or 'none stated'}"
        )
        request = DecisionSignalRequest(
            name=f"discovery_evidence_{row.suggestion_id}",
            state=state,
            instructions=(
                "Score from 0 to 1 how sufficient the cited evidence is to justify a real coverage gap: "
                "0 means the evidence cannot support any conclusion, 1 means the observed behaviour and its "
                "request are fully captured. Use only the supplied facts."
            ),
        )
        try:
            result = await self.decision_service.ask_score(request, task_id=task.id, run_id=run_id)
        except (DecisionProviderError, TimeoutError):
            record.update({"status": "JEV_UNAVAILABLE", "reason": "The Jev provider did not answer."})
            return record
        except TaskBlocked:
            raise
        except Exception as error:  # noqa: BLE001 - a grading failure must not fail the task
            record.update(
                {
                    "status": "JEV_UNAVAILABLE",
                    "reason": SensitiveRedactor.redact_text(str(error))[:200],
                    "error_type": type(error).__name__,
                }
            )
            return record
        fallback = bool(getattr(result, "fallback_used", False))
        record.update(
            {
                "provider": result.provider,
                "model": result.model,
                "score": result.score,
                "confidence": result.confidence,
                "fallback_used": fallback,
                "reason": result.reason,
                "score_source": "jev",
            }
        )
        if fallback:
            # Jev answered, but not confidently enough to accept. Keep what it said and say why.
            reason = result.reason or "unknown_error"
            status = {
                "below_minimum_confidence": "JEV_LOW_CONFIDENCE",
                "confidence_missing": "JEV_LOW_CONFIDENCE",
                "timeout": "JEV_TIMEOUT",
            }.get(reason, "JEV_FALLBACK")
            record.update({"status": status, "source": "rules", "reason": reason})
            return record
        record.update({"status": "JEV_GRADED", "source": "jev", "grade": self._grade_from_score(result.score)})
        return record

    @staticmethod
    def _grade_from_score(score: float | None) -> str:
        if score is None:
            return "unknown"
        if score >= 0.7:
            return "sufficient"
        if score >= 0.4:
            return "thin"
        return "insufficient"

    @staticmethod
    def _provider_label() -> tuple[str, str]:
        from qa_core.ai.registry import AIProviderRegistry

        config = AIProviderRegistry.runtime_values()
        return config.get("provider", "unknown"), config.get("model", "unknown")

    def _prompt(self, scenario: dict[str, Any], case_index: dict[str, dict[str, Any]]) -> str:
        from qa_core.prompts import DISCOVERY_SUGGESTION_PROMPT

        shown = scenario["evidence"][:MAX_EVIDENCE_PER_PROMPT]
        lines, redactions = self._scrub([self._evidence_line(item) for item in shown])
        cases, _ = self._scrub(
            [
                f"- {row['id']} · {row['title']} · {row.get('file_path') or 'unbound'}"
                for row in list(case_index.values())[:MAX_CASES_PER_PROMPT]
            ]
        )
        return DISCOVERY_SUGGESTION_PROMPT.format(
            scenario=f"{scenario['title']} ({scenario['scenario_id']}) at {scenario['url_template']}",
            verdict=f"{scenario['coverage_status']} via {scenario['match_method'] or 'no rule match'}"
            + (f" · note: {scenario['note']}" if scenario.get("note") else ""),
            page=scenario["page_summary"] or "no page summary captured",
            evidence="\n".join(lines) or "none captured",
            cases="\n".join(cases) or "no test case exists in this project",
            completeness=(
                f"{len(shown)} of {len(scenario['evidence'])} cited evidence rows shown"
                f"{' (truncated)' if scenario.get('truncated') else ''}; redactions applied: {redactions}"
            ),
        )

    @staticmethod
    def _scrub(lines: list[str]) -> tuple[list[str], int]:
        """Second pass over what leaves the process; the capture layer already redacted at write time."""
        cleaned = []
        redactions = 0
        for line in lines:
            redacted = SensitiveRedactor.redact_text(line)
            redactions += 1 if redacted != line else 0
            cleaned.append(redacted)
        return cleaned, redactions

    @staticmethod
    def _evidence_line(item: dict[str, Any]) -> str:
        facts = evidence_kind_facts(item["kind"], item.get("payload") or {})
        return f"- {item['id']} [{item['kind']}] {facts}"

    @staticmethod
    def _evidence_facts(row: Any) -> dict[str, Any]:
        payload = row.payload or {}
        return {"id": row.evidence_id, "kind": row.kind, "payload": payload}

    @staticmethod
    def _page_summary(by_id: dict[str, Any], cited: list[str]) -> str:
        parts = []
        for evidence_id in cited:
            row = by_id.get(evidence_id)
            if row is not None and row.kind == "page_state":
                parts.append(
                    f"{row.payload.get('url_template') or '页面'} · controls={row.payload.get('visible_controls')}"
                )
        return " / ".join(parts[:3])
