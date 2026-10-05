"""SELECT-only aggregation of existing Task and TestRun trees. No execution dependencies."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from qa_core.failure.redactor import SensitiveRedactor
from sqlalchemy import Text, literal, or_, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.persistence.models import (
    AIInvocationORM,
    ArtifactORM,
    BrowserSessionORM,
    ExternalArtifactReferenceORM,
    FailureAnalysisORM,
    FailureRecordORM,
    TaskArtifactORM,
    TaskDecisionORM,
    TaskEventORM,
    TaskEvidenceORM,
    TaskORM,
    TaskStepORM,
    TestExecutionORM,
    TestRunORM,
)
from app.services.event_normalizer import normalize_event
from app.services.runtime_models import (
    RuntimeArtifact,
    RuntimeBlocking,
    RuntimeBrowser,
    RuntimeDecision,
    RuntimeEvidence,
    RuntimeFailure,
    RuntimeRun,
    RuntimeSnapshot,
    RuntimeSpan,
    RuntimeStep,
    RuntimeStepDetail,
    RuntimeSummary,
    RuntimeTask,
)


def safe_text(value: object, limit: int = 500) -> str:
    return SensitiveRedactor.redact_text(str(value or ""))[:limit]


def elapsed(start: datetime | None, end: datetime | None) -> float | None:
    return max(0.0, (end - start).total_seconds() * 1000) if start and end else None


def fields_summary(value: dict | None) -> str:
    """List field names only. Full inputs/outputs belong to a separately scoped detail read."""
    return ", ".join(
        safe_text(key, 60)
        for key in (value or {})
        if not SensitiveRedactor.SENSITIVE_KEYS.search(key)
        and key not in {"prompt", "reasoning", "scratchpad", "content", "chain_of_thought"}
    )[:300]


STEP_FIELDS = frozenset(
    {
        "url",
        "title",
        "http_status",
        "status",
        "verified",
        "file_path",
        "test_name",
        "test_case_id",
        "run_id",
        "nodeids",
        "summary",
        "action",
        "locator",
        "provider",
        "model",
        "confidence",
        "latency_ms",
        "candidate_count",
        "selected_locator",
        "fallback_reason",
        "fallback_used",
        "failure_type",
        "response_fields",
        "validation_error",
        "screenshot_artifact_id",
        "reason",
        "before_url",
        "after_url",
    }
)


def public_step_payload(value: dict | None) -> dict:
    result = {}
    for key, item in (value or {}).items():
        if key in STEP_FIELDS and isinstance(item, (str, int, float, bool, type(None))):
            result[key] = safe_text(item, 2000) if isinstance(item, str) else item
        elif key == "nodeids" and isinstance(item, list):
            result[key] = [safe_text(nodeid) for nodeid in item[:100] if isinstance(nodeid, str)]
        elif key == "candidate" and isinstance(item, dict):
            result[key] = {
                field: safe_text(candidate) if isinstance(candidate, str) else candidate
                for field, candidate in item.items()
                if field in {"candidate_id", "locator", "kind", "name", "selector", "safe", "risk", "index", "verified"}
                and isinstance(candidate, (str, int, float, bool, type(None)))
            }
        elif key == "candidates" and isinstance(item, list):
            result["candidate_count"] = len(item)
    return SensitiveRedactor.redact_value(result)


class RuntimeProjection:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def step_detail(self, task_id: str, step_id: str, owner_id: str) -> RuntimeStepDetail | None:
        row = (
            await self.session.scalars(
                select(TaskStepORM)
                .join(TaskORM, TaskORM.id == TaskStepORM.task_id)
                .where(TaskStepORM.id == step_id, TaskStepORM.task_id == task_id, TaskORM.owner_id == owner_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return RuntimeStepDetail(
            id=row.id, inputs=public_step_payload(row.inputs), outputs=public_step_payload(row.outputs)
        )

    async def _legacy_task(self, run_id: str, project_id: str) -> TaskORM | None:
        # Read the Text decorator without database JSON casts. Its result processor already
        # tolerates malformed historical JSON. Bound the search and never guess on overflow.
        candidates = list(
            (
                await self.session.scalars(
                    select(TaskORM)
                    .options(noload("*"))
                    .where(
                        TaskORM.project_id == project_id,
                        type_coerce(TaskORM.context, Text).contains(run_id, autoescape=True),
                    )
                    .limit(201)
                )
            ).all()
        )
        if len(candidates) > 200:
            return None
        matches = [row for row in candidates if isinstance(row.context, dict) and row.context.get("run_id") == run_id]
        return matches[0] if len(matches) == 1 else None

    async def task(self, task_id: str, owner_id: str) -> RuntimeSnapshot | None:
        task = (
            await self.session.execute(select(TaskORM).where(TaskORM.id == task_id, TaskORM.owner_id == owner_id))
        ).scalar_one_or_none()
        if task is None:
            return None
        run_id = task.context.get("run_id") if isinstance(task.context, dict) else None
        relation = TestRunORM.task_id == task.id
        if (
            isinstance(run_id, str)
            and (legacy := await self._legacy_task(run_id, task.project_id)) is not None
            and legacy.id == task.id
        ):
            relation = or_(relation, (TestRunORM.id == run_id) & TestRunORM.task_id.is_(None))
        runs = list(
            (
                await self.session.scalars(
                    select(TestRunORM)
                    .options(noload("*"))
                    .where(relation, TestRunORM.project_id == task.project_id)
                    .order_by(TestRunORM.created_at)
                )
            ).all()
        )
        return await self._snapshot(task, runs, "task")

    async def run(self, run_id: str, owner_id: str) -> RuntimeSnapshot | None:
        run = (
            await self.session.scalars(select(TestRunORM).options(noload("*")).where(TestRunORM.id == run_id))
        ).one_or_none()
        if run is None:
            return None
        if run.task_id:
            task = (
                await self.session.scalars(
                    select(TaskORM).where(
                        TaskORM.id == run.task_id, TaskORM.owner_id == owner_id, TaskORM.project_id == run.project_id
                    )
                )
            ).one_or_none()
            return await self._snapshot(task, [run], "run")
        # Cross-owner ambiguity is still ambiguity; ownership is checked after matching.
        legacy = await self._legacy_task(run_id, run.project_id)
        task = legacy if legacy and legacy.owner_id == owner_id else None
        return await self._snapshot(task, [run], "run")

    async def _snapshot(self, task: TaskORM | None, runs: list[TestRunORM], kind: str) -> RuntimeSnapshot:
        root = task if kind == "task" else runs[0]
        snapshot = RuntimeSnapshot(
            id=root.id,
            kind=kind,
            status=root.status,
            title=safe_text(task.goal if kind == "task" else f"Test Run {root.id}"),
            created_at=root.created_at,
            started_at=root.started_at,
            finished_at=root.finished_at,
            duration_ms=elapsed(root.started_at, root.finished_at),
        )
        if task:
            rows = list(
                (
                    await self.session.scalars(
                        select(TaskEventORM)
                        .where(TaskEventORM.task_id == task.id)
                        .order_by(TaskEventORM.id.desc())
                        .limit(501)
                    )
                ).all()
            )
            snapshot.events_truncated = len(rows) > 500
            rows = list(reversed(rows[:500]))
            snapshot.event_cursor = rows[-1].id if rows else 0
            for row in rows:
                event = normalize_event(
                    {"type": row.type, "payload": row.payload, "created_at": row.created_at, "step_id": row.step_id},
                    source="task",
                    source_id=str(row.id),
                    runtime_id=root.id,
                    task_id=task.id,
                )
                if event:
                    snapshot.events.append(event)
            snapshot.task = RuntimeTask(
                id=task.id,
                kind="task",
                task_id=task.id,
                title=safe_text(task.goal),
                type=task.type,
                status=task.status,
                started_at=task.started_at,
                finished_at=task.finished_at,
                duration_ms=elapsed(task.started_at, task.finished_at),
                current_step_id=task.current_step_id,
                retry_count=task.retry_count or 0,
                failure_reason=safe_text(task.failure_reason) if task.failure_reason else None,
                replan_count=task.replan_count or 0,
                max_replans=task.max_replans or 0,
                recorder_session_id=(task.inputs or {}).get("recorder_session_id")
                if isinstance((task.inputs or {}).get("recorder_session_id"), str)
                else None,
            )
            steps = list(
                (
                    await self.session.scalars(
                        select(TaskStepORM)
                        .where(TaskStepORM.task_id == task.id)
                        .order_by(TaskStepORM.position, TaskStepORM.id)
                    )
                ).all()
            )
            snapshot.steps = [
                RuntimeStep(
                    id=row.id,
                    kind="step",
                    task_id=task.id,
                    step_id=row.id,
                    key=row.key,
                    title=safe_text(row.name),
                    tool=row.tool,
                    status=row.status,
                    dependencies=row.dependencies or [],
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                    duration_ms=(
                        elapsed(row.started_at, row.finished_at)
                        if row.finished_at and row.duration_ms in (None, 0)
                        else row.duration_ms
                        if row.finished_at
                        else None
                    ),
                    retry_count=row.retry_count or 0,
                    inputs_summary=fields_summary(row.inputs),
                    outputs_summary=fields_summary(row.outputs),
                    error=safe_text(row.error) if row.error else None,
                    failure_type=safe_text((row.outputs or {}).get("failure_type"))
                    if isinstance(row.outputs, dict) and row.outputs.get("failure_type")
                    else None,
                    ai_provider=safe_text((row.outputs or {}).get("provider"))
                    if isinstance(row.outputs, dict) and row.outputs.get("provider")
                    else None,
                    ai_model=safe_text((row.outputs or {}).get("model"))
                    if isinstance(row.outputs, dict) and row.outputs.get("model")
                    else None,
                    validation_error=safe_text((row.outputs or {}).get("validation_error"))
                    if isinstance(row.outputs, dict) and row.outputs.get("validation_error")
                    else None,
                )
                for row in steps
            ]
            if task.status in {"BLOCKED", "FAILED"}:
                blocked_step = next(
                    (step for step in snapshot.steps if step.id == task.current_step_id),
                    next((step for step in reversed(snapshot.steps) if step.status == "FAILED"), None),
                )
                reason = (blocked_step.error if blocked_step else None) or task.failure_reason or "Task is blocked."
                lowered_reason = reason.lower()
                invalid_ai_output = (blocked_step.failure_type == "AI_OUTPUT_INVALID") if blocked_step else False
                invalid_ai_output = invalid_ai_output or any(
                    marker in lowered_reason
                    for marker in ("suggested_code", "executable source code", "structured output")
                )
                failure_type = "AI_OUTPUT_INVALID" if invalid_ai_output else "STEP_BLOCKED"
                if blocked_step and invalid_ai_output:
                    # Older task rows predate the typed failure metadata. Put the
                    # compatible classification on the step so every consumer
                    # (including the inspector) sees the same blocker state.
                    blocked_step.failure_type = failure_type
                changed_source = any(
                    step.status == "COMPLETED" and step.tool in {"source.write_generated", "source.apply_repair"}
                    for step in snapshot.steps
                )
                safe_retry = bool(invalid_ai_output and blocked_step and blocked_step.status == "FAILED")
                recoverable = bool(
                    safe_retry and not changed_source and (task.replan_count or 0) < (task.max_replans or 0)
                )
                actions = []
                if invalid_ai_output:
                    actions.append("inspect_ai_output")
                if recoverable and blocked_step and blocked_step.status == "FAILED":
                    actions.append("retry_step")
                if recoverable and blocked_step and blocked_step.status == "FAILED":
                    actions.append("replan")
                snapshot.blocking = RuntimeBlocking(
                    step_id=blocked_step.id if blocked_step else None,
                    step_key=blocked_step.key if blocked_step else None,
                    failure_type=failure_type,
                    reason=safe_text(reason, 2000),
                    recoverable=recoverable,
                    recovery_actions=actions,
                )
            valid_step_ids = {step.id for step in snapshot.steps}
            for event in snapshot.events:
                if event.step_id not in valid_step_ids:
                    event.step_id = None
            decisions = (
                await self.session.scalars(
                    select(TaskDecisionORM)
                    .where(TaskDecisionORM.task_id == task.id)
                    .order_by(TaskDecisionORM.created_at)
                )
            ).all()
            snapshot.decisions = [
                RuntimeDecision(
                    id=row.id,
                    step_id=row.step_id,
                    name=safe_text(row.name),
                    provider=row.provider,
                    selected=safe_text(row.choice),
                    confidence=row.confidence if row.provider == "jev" or row.confidence else None,
                    created_at=row.created_at,
                )
                for row in decisions
            ]
            evidence = (
                await self.session.scalars(
                    select(TaskEvidenceORM)
                    .where(TaskEvidenceORM.task_id == task.id)
                    .order_by(TaskEvidenceORM.created_at)
                )
            ).all()
            snapshot.evidence = [
                RuntimeEvidence(
                    id=row.id,
                    step_id=row.step_id,
                    type=row.type,
                    source=safe_text(row.source),
                    summary=safe_text(row.summary),
                    artifact_id=row.artifact_id,
                    created_at=row.created_at,
                )
                for row in evidence
            ]
            artifacts = (
                await self.session.execute(
                    select(TaskArtifactORM, ArtifactORM)
                    .outerjoin(ArtifactORM, ArtifactORM.id == TaskArtifactORM.artifact_id)
                    .where(TaskArtifactORM.task_id == task.id)
                )
            ).all()
            snapshot.artifacts = [
                RuntimeArtifact(
                    id=row.id,
                    artifact_id=stored.id if stored else None,
                    name=safe_text(row.name),
                    type=row.kind,
                    source="task",
                    step_id=row.step_id,
                    created_at=row.created_at,
                    size_bytes=stored.size_bytes if stored else None,
                    content_type=stored.content_type if stored else None,
                )
                for row, stored in artifacts
            ]
        run_ids = [run.id for run in runs]
        snapshot.runs = [
            RuntimeRun(
                id=row.id,
                kind="run",
                test_run_id=row.id,
                task_id=task.id if task else None,
                title=f"Test Run {row.id}",
                status=row.status,
                started_at=row.started_at,
                finished_at=row.finished_at,
                duration_ms=elapsed(row.started_at, row.finished_at),
                relationship_source="foreign_key" if row.task_id else "legacy_context" if task else "standalone",
                parent_run_id=row.parent_run_id,
                origin_failure_id=row.origin_failure_id,
                total=row.total or 0,
                passed=row.passed or 0,
                failed=row.failed or 0,
                skipped=row.skipped or 0,
            )
            for row in runs
        ]
        if run_ids:
            chain = (
                select(TestRunORM.id, TestRunORM.parent_run_id, literal(0).label("depth"))
                .where(TestRunORM.id.in_(run_ids))
                .cte("runtime_ancestors", recursive=True)
            )
            chain = chain.union_all(
                select(TestRunORM.id, TestRunORM.parent_run_id, chain.c.depth + 1)
                .join(chain, TestRunORM.id == chain.c.parent_run_id)
                .where(chain.c.depth < 16, TestRunORM.project_id == runs[0].project_id)
            )
            ancestors = (
                (
                    await self.session.scalars(
                        select(TestRunORM)
                        .join(chain, TestRunORM.id == chain.c.id)
                        .where(chain.c.depth > 0, TestRunORM.id.not_in(run_ids))
                        .order_by(chain.c.depth.desc())
                        .options(noload("*"))
                    )
                )
                .unique()
                .all()
            )
            snapshot.run_ancestors = [
                RuntimeRun(
                    id=row.id,
                    kind="run",
                    title=f"Test Run {row.id}",
                    status=row.status,
                    test_run_id=row.id,
                    parent_run_id=row.parent_run_id,
                    origin_failure_id=row.origin_failure_id,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                    duration_ms=elapsed(row.started_at, row.finished_at),
                    relationship_source="foreign_key" if row.task_id else "standalone",
                )
                for row in ancestors
            ]
            if task:
                for run in snapshot.runs:
                    associated = {step.id for step in steps if (step.outputs or {}).get("run_id") == run.id}
                    associated.update(
                        event.step_id
                        for event in snapshot.events
                        if event.test_run_id == run.id and event.step_id in valid_step_ids
                    )
                    if len(associated) == 1:
                        run.step_id = next(iter(associated))
            executions = (
                await self.session.scalars(
                    select(TestExecutionORM).where(TestExecutionORM.run_id.in_(run_ids)).options(noload("*"))
                )
            ).all()
            # Until timestamp repair, old executions with equal timestamps and positive duration
            # must be visibly unavailable rather than rendered as misleading zero-width spans.
            snapshot.executions = [
                RuntimeSpan(
                    id=row.id,
                    kind="test",
                    title=safe_text(row.nodeid),
                    status=row.status,
                    test_run_id=row.run_id,
                    duration_ms=row.duration_ms,
                    started_at=row.started_at if row.started_at != row.finished_at or not row.duration_ms else None,
                    finished_at=row.finished_at,
                    timestamp_source="unavailable"
                    if row.started_at == row.finished_at and row.duration_ms
                    else row.timestamp_source or "recorded",
                )
                for row in executions
            ]
            browsers = (
                await self.session.scalars(
                    select(BrowserSessionORM).where(BrowserSessionORM.run_id.in_(run_ids)).options(noload("*"))
                )
            ).all()
            snapshot.browser_sessions = [
                RuntimeBrowser(
                    id=row.id,
                    kind="browser",
                    browser_session_id=row.browser_session_id,
                    test_run_id=row.run_id,
                    title=safe_text(row.case_name or row.nodeid),
                    status=row.status,
                    current_url=SensitiveRedactor.redact_url(row.current_url),
                    case_execution_id=row.case_execution_id,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                    duration_ms=elapsed(row.started_at, row.finished_at),
                )
                for row in browsers
            ]
            for row in browsers:
                try:
                    page_evidence = json.loads(row.page_evidence_json or "{}")
                except (ValueError, TypeError):
                    page_evidence = {}
                if not isinstance(page_evidence, dict):
                    continue
                for channel in ["recent_steps", "network_logs", "console_logs"]:
                    entries = page_evidence.get(channel, [])
                    if not isinstance(entries, list):
                        continue
                    for entry in entries[-100:]:
                        if not isinstance(entry, dict):
                            continue
                        identity = hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()[
                            :16
                        ]
                        event = normalize_event(
                            {
                                "type": f"browser.{channel}",
                                "timestamp": entry.get("timestamp"),
                                **{key: value for key, value in entry.items() if key != "type"},
                            },
                            source="browser",
                            source_id=f"{row.id}:{channel}:{identity}",
                            runtime_id=root.id,
                            task_id=task.id if task else None,
                            test_run_id=row.run_id,
                        )
                        if event:
                            snapshot.events.append(event)
            failures = (
                await self.session.scalars(
                    select(FailureRecordORM).where(FailureRecordORM.run_id.in_(run_ids)).options(noload("*"))
                )
            ).all()
            snapshot.failures = [
                RuntimeFailure(
                    id=row.id,
                    test_run_id=row.run_id,
                    execution_id=row.execution_id,
                    title=safe_text(row.test_name),
                    classification=row.classification,
                    message=safe_text(row.error_message),
                    created_at=row.created_at,
                )
                for row in failures
            ]
            if failures:
                analyses = (
                    await self.session.scalars(
                        select(FailureAnalysisORM).where(
                            FailureAnalysisORM.failure_id.in_([row.id for row in failures])
                        )
                    )
                ).all()
                failure_runs = {row.id: row.run_id for row in failures}
                for analysis in analyses:
                    for index, raw in enumerate((analysis.events or [])[-500:]):
                        if not isinstance(raw, dict):
                            continue
                        event = normalize_event(
                            raw,
                            source="ai",
                            source_id=f"{analysis.id}:{raw.get('event_id') or index}",
                            runtime_id=root.id,
                            task_id=task.id if task else None,
                            test_run_id=failure_runs[analysis.failure_id],
                        )
                        if event:
                            snapshot.events.append(event)
            refs = (
                await self.session.scalars(
                    select(ExternalArtifactReferenceORM)
                    .where(ExternalArtifactReferenceORM.run_id.in_(run_ids))
                    .options(noload("*"))
                )
            ).all()
            artifact_ids = [
                row.metadata_json.get("artifact_id")
                for row in refs
                if row.metadata_json and isinstance(row.metadata_json.get("artifact_id"), str)
            ]
            stored = (
                {
                    row.id: row
                    for row in (
                        await self.session.scalars(select(ArtifactORM).where(ArtifactORM.id.in_(artifact_ids)))
                    ).all()
                }
                if artifact_ids
                else {}
            )
            for ref in refs:
                artifact = stored.get((ref.metadata_json or {}).get("artifact_id"))
                snapshot.artifacts.append(
                    RuntimeArtifact(
                        id=ref.id,
                        artifact_id=artifact.id if artifact else None,
                        name=safe_text(ref.name),
                        type=ref.type,
                        source="run",
                        test_run_id=ref.run_id,
                        created_at=ref.created_at,
                        size_bytes=artifact.size_bytes if artifact else None,
                        content_type=artifact.content_type if artifact else None,
                        url=SensitiveRedactor.redact_url(ref.url)
                        if ref.url.startswith(("http://", "https://"))
                        else None,
                    )
                )
        completed = {step.key for step in snapshot.steps if step.status in {"COMPLETED", "SKIPPED"}}
        # Reconstruct lifecycle facts from persisted rows; source IDs document provenance.
        for run in snapshot.runs:
            for event_type, timestamp in [("RUN_STARTED", run.started_at), ("RUN_FINISHED", run.finished_at)]:
                if timestamp:
                    event = normalize_event(
                        {
                            "type": event_type,
                            "timestamp": timestamp,
                            "status": run.status if event_type == "RUN_FINISHED" else "RUNNING",
                        },
                        source="run",
                        source_id=f"{run.id}:{event_type}",
                        runtime_id=root.id,
                        task_id=task.id if task else None,
                        test_run_id=run.id,
                    )
                    if event:
                        snapshot.events.append(event)
        for execution in snapshot.executions:
            if execution.finished_at:
                event = normalize_event(
                    {
                        "type": "TEST_FINISHED",
                        "nodeid": execution.title,
                        "status": execution.status,
                        "duration_ms": execution.duration_ms,
                        "timestamp": execution.finished_at,
                    },
                    source="run",
                    source_id=execution.id,
                    runtime_id=root.id,
                    task_id=task.id if task else None,
                    test_run_id=execution.test_run_id,
                )
                if event:
                    snapshot.events.append(event)
        snapshot.events.sort(key=lambda event: (event.timestamp.isoformat() if event.timestamp else "", event.id))
        if len(snapshot.events) > 500:
            snapshot.events = snapshot.events[-500:]
            snapshot.events_truncated = True
        invocations = (
            (
                await self.session.scalars(
                    select(AIInvocationORM)
                    .where(AIInvocationORM.task_id == task.id)
                    .order_by(AIInvocationORM.started_at)
                )
            ).all()
            if task
            else []
        )
        trace_steps = {}
        for event in snapshot.events:
            if event.trace_run_id and event.step_id:
                trace_steps.setdefault(event.trace_run_id, set()).add(event.step_id)

        def invocation_step_id(row: AIInvocationORM) -> str | None:
            linked = trace_steps.get(row.run_id, set())
            if len(linked) == 1:
                return next(iter(linked))
            if not row.started_at or row.duration_ms is None:
                return None
            invocation_finished = row.started_at + timedelta(milliseconds=row.duration_ms)
            matches = [
                step.id
                for step in snapshot.steps
                if step.started_at
                and step.finished_at
                and step.started_at <= row.started_at
                and invocation_finished <= step.finished_at
            ]
            return matches[0] if len(matches) == 1 else None

        snapshot.ai_invocations = [
            RuntimeSpan(
                id=row.id,
                kind="ai",
                title=safe_text(f"{row.task} · {row.provider} · {row.model}"),
                status=row.status,
                task_id=task.id,
                started_at=row.started_at,
                finished_at=row.started_at + timedelta(milliseconds=row.duration_ms)
                if row.started_at and row.duration_ms is not None
                else None,
                duration_ms=row.duration_ms,
                timestamp_source="derived",
                operation=safe_text(row.task),
                provider=safe_text(row.provider),
                model=safe_text(row.model),
                step_id=invocation_step_id(row),
            )
            for row in invocations
        ]
        invocations_by_step: dict[str, list[RuntimeSpan]] = {}
        for invocation in snapshot.ai_invocations:
            if invocation.step_id:
                invocations_by_step.setdefault(invocation.step_id, []).append(invocation)
        for step in snapshot.steps:
            associated = invocations_by_step.get(step.id, [])
            if not associated:
                continue
            providers = {row.provider for row in associated if row.provider}
            models = {row.model for row in associated if row.model}
            if len(providers) == 1 and not step.ai_provider:
                step.ai_provider = next(iter(providers))
            if len(models) == 1 and not step.ai_model:
                step.ai_model = next(iter(models))
        run_steps = {run.id: run.step_id for run in snapshot.runs}
        valid_step_ids = {step.id for step in snapshot.steps}
        for event in snapshot.events:
            if event.step_id not in valid_step_ids:
                event.step_id = run_steps.get(event.test_run_id)
        for invocation in snapshot.ai_invocations:
            if invocation.step_id not in valid_step_ids:
                invocation.step_id = None
        for span in [*snapshot.executions, *snapshot.browser_sessions]:
            span.step_id = run_steps.get(span.test_run_id)
        snapshot.summary = RuntimeSummary(
            completed_steps=len(completed),
            total_steps=len(snapshot.steps),
            active_step_ids=[step.id for step in snapshot.steps if step.status == "RUNNING"],
            next_step_ids=[
                step.id for step in snapshot.steps if step.status == "PENDING" and set(step.dependencies) <= completed
            ],
            failures=len(snapshot.failures) + sum(step.status == "FAILED" for step in snapshot.steps),
            retries=sum(step.retry_count for step in snapshot.steps)
            + len({run.id for run in [*snapshot.runs, *snapshot.run_ancestors] if run.parent_run_id}),
            ai_calls=len(invocations) if task else None,
            artifacts=len(snapshot.artifacts),
            approval=any(step.status == "WAITING_FOR_APPROVAL" for step in snapshot.steps),
        )
        return snapshot
