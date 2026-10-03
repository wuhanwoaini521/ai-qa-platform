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
  return snapshot.steps.filter((step) =>
    snapshot.summary.active_step_ids.includes(step.id),
  );
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
