import type { RuntimeSnapshot, RuntimeSpan } from '../../types/runtime';

export const runtimeActive = (status: string) =>
  ![
    'COMPLETED',
    'SUCCESS',
    'PASSED',
    'FAILED',
    'ERROR',
    'BLOCKED',
    'CANCELLED',
    'CANCELED',
    'SKIPPED',
    'ABORTED',
  ].includes(status.toUpperCase());
export const runtimeNeedsTerminalRefresh = (status: string) =>
  ['BLOCKED', 'FAILED'].includes(status.toUpperCase());
export const liveSpan = (span: Pick<RuntimeSpan, 'status' | 'finished_at'>) =>
  !span.finished_at &&
  [
    'RUNNING',
    'VERIFYING',
    'RETRYING',
    'WAITING',
    'WAITING_FOR_APPROVAL',
  ].includes(span.status.toUpperCase());
export function durationLabel(duration: number | null | undefined) {
  if (duration == null || !Number.isFinite(duration) || duration < 0)
    return '—';
  const seconds = duration / 1000;
  if (duration < 100) return '<100ms';
  return seconds < 60
    ? `${seconds.toFixed(1)}s`
    : `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60)
        .toString()
        .padStart(2, '0')}`;
}
export function spanDuration(
  span: Pick<
    RuntimeSpan,
    'started_at' | 'finished_at' | 'duration_ms' | 'status'
  >,
  now: number,
) {
  if (liveSpan(span) && span.started_at) {
    const start = Date.parse(span.started_at);
    return Number.isFinite(start) ? Math.max(0, now - start) : null;
  }
  return span.duration_ms;
}
export function currentSteps(snapshot: RuntimeSnapshot) {
  const active = snapshot.steps.filter((step) =>
    snapshot.summary.active_step_ids.includes(step.id),
  );
  if (active.length) return active;
  if (snapshot.status === 'BLOCKED' || snapshot.status === 'FAILED') {
    const blocker = snapshot.blocking?.step_id ?? snapshot.task?.current_step_id;
    const failed = snapshot.steps.find((step) => step.id === blocker);
    if (failed) return [failed];
  }
  return [];
}

export function stepCounts(snapshot: RuntimeSnapshot) {
  const completed = snapshot.steps.filter((step) => step.status === 'COMPLETED').length;
  const failed = snapshot.steps.filter((step) => step.status === 'FAILED').length;
  const skipped = snapshot.steps.filter((step) => step.status === 'SKIPPED').length;
  const pending = snapshot.steps.filter((step) => step.status === 'PENDING');
  const blockedKeys = new Set<string>();
  const blockingKey = snapshot.blocking?.step_key;
  if (snapshot.status === 'BLOCKED' && blockingKey) blockedKeys.add(blockingKey);
  let changed = true;
  while (changed) {
    changed = false;
    for (const step of pending) {
      if (!blockedKeys.has(step.key) && (step.dependencies ?? []).some((key) => blockedKeys.has(key))) {
        blockedKeys.add(step.key);
        changed = true;
      }
    }
  }
  const blockedSteps = pending.filter((step) => blockedKeys.has(step.key));
  const blocked = blockedSteps.length;
  return {
    completed,
    failed,
    pending: pending.length,
    blocked,
    blockedStepIds: blockedSteps.map((step) => step.id),
    skipped,
    remaining: Math.max(0, snapshot.steps.length - completed - failed - skipped),
    total: snapshot.steps.length,
  };
}

export function nextAction(snapshot: RuntimeSnapshot) {
  if (snapshot.status === 'WAITING' || snapshot.summary.approval) return 'approval';
  if (snapshot.status === 'BLOCKED') {
    return snapshot.blocking?.recovery_actions.includes('retry_step') ? 'retry' :
      snapshot.blocking?.recovery_actions.includes('replan') ? 'replan' : 'none';
  }
  if (snapshot.summary.next_step_ids.length) return 'run_next';
  if (snapshot.steps.some((step) => step.status === 'RUNNING')) return 'running';
  if (['COMPLETED', 'PASSED', 'FAILED', 'CANCELLED'].includes(snapshot.status)) return 'none';
  return 'waiting';
}

const retryActionLabels: Record<string, string> = {
  ANALYZE_REQUIREMENT: 'retryAnalyzeRequirement',
  CREATE_TEST: 'retryCreateTest',
  FIX_FAILURE: 'retryRepair',
  OPTIMIZE_TEST: 'retryOptimizeTest',
  EXPLORE_PAGE: 'retryExplorePage',
  RUN_REGRESSION: 'retryRegression',
  REVIEW_TEST: 'retryReviewTest',
};

export function retryActionLabel(taskType: string | null | undefined) {
  return retryActionLabels[taskType ?? ''] ?? 'retry';
}

export function retryGuidance(taskType: string | null | undefined) {
  switch (taskType) {
    case 'ANALYZE_REQUIREMENT':
      return 'Retry requirement analysis from the persisted requirement and current project context. Do not invent findings or modify requirement inputs.';
    case 'CREATE_TEST':
      return 'Retry the failed test-generation step for the original request. Return executable test source in the format expected by this step, use the collected evidence, and do not apply source changes.';
    case 'FIX_FAILURE':
      return 'Retry the failed repair step using the existing collected evidence. Return an executable source proposal when evidence supports it; do not apply source changes without approval.';
    case 'OPTIMIZE_TEST':
      return 'Retry the failed test-optimization step for the original request. Preserve the test behavior, return executable optimized test source in the format expected by this step, and do not apply source changes.';
    case 'EXPLORE_PAGE':
      return 'Retry the failed page-exploration step for the original request. Use the collected browser evidence and return findings in the format expected by this step; do not apply source changes.';
    case 'RUN_REGRESSION':
      return 'Retry the failed regression step for the original request. Preserve the requested test scope and return the expected regression results or test proposal; do not apply source changes.';
    case 'REVIEW_TEST':
      return 'Retry the failed test-review step for the original request. Use the collected evidence and return structured findings in the format expected by this step; do not apply source changes.';
    default:
      return 'Retry the failed workflow step for the original request using collected evidence. Return output in the format expected by this step and do not apply source changes.';
  }
}

export function runtimeStatusKey(status: string) {
  switch (status.toUpperCase()) {
    case 'WAITING_FOR_APPROVAL':
    case 'WAITING':
      return 'waitingApproval';
    case 'PENDING':
      return 'pending';
    case 'QUEUED':
      return 'queued';
    default:
      return status.toLowerCase();
  }
}

export function overviewFacts(snapshot: RuntimeSnapshot) {
  return {
    active: currentSteps(snapshot),
    next: snapshot.steps.filter((step) =>
      snapshot.summary.next_step_ids.includes(step.id),
    ),
    failed: snapshot.steps.filter((step) => step.status === 'FAILED'),
    slowest: snapshot.steps
      .filter((step) => step.duration_ms !== null)
      .reduce<RuntimeSnapshot['steps'][number] | null>(
        (longest, step) =>
          !longest || step.duration_ms! > longest.duration_ms! ? step : longest,
        null,
      ),
    aiTimeMs: (snapshot.ai_invocations ?? []).reduce(
      (total, invocation) => total + (invocation.duration_ms ?? 0),
      0,
    ),
    counts: stepCounts(snapshot),
    tests: snapshot.runs.reduce(
      (total, run) => ({
        total: total.total + run.total,
        passed: total.passed + run.passed,
        failed: total.failed + run.failed,
      }),
      { total: 0, passed: 0, failed: 0 },
    ),
  };
}
export function inspectorContext(
  snapshot: RuntimeSnapshot,
  stepId: string | null,
) {
  return {
    step: snapshot.steps.find((step) => step.id === stepId) ?? null,
    decisions: snapshot.decisions.filter((item) => item.step_id === stepId),
    evidence: snapshot.evidence.filter((item) => item.step_id === stepId),
    artifacts: snapshot.artifacts.filter((item) => item.step_id === stepId),
    events: snapshot.events.filter(
      (item) => stepId !== null && item.step_id === stepId,
    ),
    runs: snapshot.runs.filter((item) => item.step_id === stepId),
  };
}
