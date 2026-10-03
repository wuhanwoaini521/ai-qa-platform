import type { AITraceEvent } from '../../types';
import type { RuntimeEvent } from '../../types/runtime';
export const TRACE_FILTERS = [
  'All',
  'AI',
  'Decision',
  'Browser',
  'Test',
  'Failure',
  'Artifact',
] as const;
export type TraceFilter = (typeof TRACE_FILTERS)[number];
export function filterTrace(
  events: RuntimeEvent[],
  filter: TraceFilter,
  errorOnly: boolean,
  stepId: string | null = null,
) {
  return events.filter(
    (event) =>
      (filter === 'All' || event.category === filter.toLowerCase()) &&
      (!errorOnly ||
        ['FAILED', 'BLOCKED', 'ERROR'].includes(
          (event.status ?? '').toUpperCase(),
        ) ||
        event.metadata.verified === false ||
        Number(event.metadata.status_code ?? event.metadata.status) >= 400 ||
        event.metadata.level === 'error') &&
      (!stepId || event.step_id === stepId),
  );
}
export function traceAdapter(event: RuntimeEvent): AITraceEvent {
  return {
    run_id: event.trace_run_id ?? '',
    event_id: event.id,
    type: event.type,
    timestamp: event.timestamp,
    step_id: event.step_id,
    status: event.status ?? undefined,
    duration_ms: event.duration_ms,
    stage: event.category,
    title: event.title,
    message: event.summary,
    metadata: {
      ...event.metadata,
      category: event.category,
      test_run_id: event.test_run_id ?? null,
      runtime_id: event.runtime_id,
    },
  };
}
