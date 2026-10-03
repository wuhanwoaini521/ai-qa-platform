import type { AITraceEvent } from '../../types';

const completions: Record<string, string> = {
  'run.started': 'run.completed',
  'step.started': 'step.completed',
  'model.started': 'model.completed',
  'tool.started': 'tool.completed',
  'decision.started': 'decision.completed',
  'validation.started': 'validation.completed',
  analysis_started: 'diagnosis_completed',
  decision_started: 'decision_completed',
  verification_started: 'verification_completed',
};

export function traceState(
  events: AITraceEvent[],
  index: number,
  running: boolean,
): 'done' | 'active' | 'error' | 'pending' {
  const event = events[index];
  const status = (
    event.status ?? String(event.metadata?.status ?? '')
  ).toUpperCase();
  if (
    ['FAILED', 'BLOCKED', 'ERROR'].includes(status) ||
    Number(event.metadata?.status_code ?? event.metadata?.status) >= 400 ||
    event.metadata?.level === 'error' ||
    event.type.endsWith('.failed') ||
    event.type === 'failed' ||
    (event.type === 'verification_completed' &&
      event.metadata?.verified === false)
  )
    return 'error';
  if (
    ['PENDING', 'SKIPPED', 'CANCELLED', 'UNVERIFIED'].includes(status) ||
    event.type === 'run.cancelled'
  )
    return 'pending';
  const completion = completions[event.type];
  if (completion) {
    const related = events
      .slice(index + 1)
      .filter(
        (candidate) =>
          candidate.run_id === event.run_id &&
          candidate.step_id === event.step_id &&
          candidate.metadata?.test_run_id === event.metadata?.test_run_id &&
          candidate.metadata?.runtime_id === event.metadata?.runtime_id,
      );
    if (related.some((candidate) => candidate.type === completion))
      return 'done';
    if (
      related.some(
        (candidate) =>
          candidate.type === event.type.replace(/started$/, 'failed'),
      )
    )
      return 'error';
    return running ? 'active' : 'pending';
  }
  if (
    ['COMPLETED', 'SUCCESS', 'PASSED'].includes(status) ||
    [
      '_collected',
      '_generated',
      '_completed',
      '_suggested',
      '.completed',
      '.collected',
      '.loaded',
    ].some((suffix) => event.type.endsWith(suffix))
  )
    return 'done';
  return running && ['RUNNING', 'VERIFYING', 'RETRYING'].includes(status)
    ? 'active'
    : 'pending';
}
