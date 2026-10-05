import type { RuntimeEvent, RuntimeSnapshot } from '../../types/runtime';

export interface TraceSummaryGroup {
  id: string;
  stepId: string | null;
  category: string;
  title: string;
  status: string | null;
  timestamp: string | null;
  durationMs: number | null;
  evidenceCount: number;
  events: RuntimeEvent[];
}

const eventTime = (event: RuntimeEvent) => event.timestamp ? Date.parse(event.timestamp) : Number.POSITIVE_INFINITY;

export function summarizeTrace(events: RuntimeEvent[], snapshot: RuntimeSnapshot): TraceSummaryGroup[] {
  const groups = new Map<string, RuntimeEvent[]>();
  for (const event of events) {
    const key = event.step_id
      ? `step:${event.step_id}`
      : event.category === 'lifecycle'
        ? 'lifecycle:task'
        : `${event.category}:${event.trace_run_id ?? event.test_run_id ?? event.id}`;
    const group = groups.get(key);
    if (group) group.push(event);
    else groups.set(key, [event]);
  }
  return [...groups.entries()].map(([id, rows]) => {
    const ordered = [...rows].sort((a, b) => eventTime(a) - eventTime(b));
    const stepId = ordered.find((event) => event.step_id)?.step_id ?? null;
    const step = snapshot.steps.find((item) => item.id === stepId);
    const terminalError = [...ordered].reverse().find((event) =>
      ['FAILED', 'BLOCKED', 'ERROR'].includes((event.status ?? '').toUpperCase()) ||
      event.type.endsWith('.failed') || event.type === 'failed',
    );
    const latest = [...ordered].reverse().find((event) => event.status) ?? ordered.at(-1)!;
    const duration = step?.duration_ms ?? [...ordered].reverse().find((event) => event.duration_ms != null)?.duration_ms ?? null;
    const first = ordered.find((event) => event.timestamp)?.timestamp ?? null;
    const summary = {
      id,
      stepId,
      category: step ? 'step' : ordered[0]?.category ?? 'system',
      title: step?.title ?? (id === 'lifecycle:task' ? 'Task lifecycle' : ordered.find((event) => event.title)?.title ?? 'Runtime event'),
      status: terminalError?.status?.toUpperCase() === 'BLOCKED' ? 'BLOCKED' : terminalError ? 'FAILED' : latest?.status ?? null,
      timestamp: first,
      durationMs: duration,
      evidenceCount: ordered.filter((event) => event.type === 'evidence.created' || event.type.endsWith('.collected') || event.category === 'artifact').length,
      events: ordered,
    } satisfies TraceSummaryGroup;
    return summary;
  }).sort((a, b) => eventTime({ timestamp: a.timestamp } as RuntimeEvent) - eventTime({ timestamp: b.timestamp } as RuntimeEvent));
}

export function eventLabelKey(type: string) {
  const labels: Record<string, string> = {
    'task.created': 'eventTaskCreated', 'task.started': 'eventTaskStarted', 'task.planning': 'eventTaskPlanning',
    'task.blocked': 'eventTaskBlocked', 'task.completed': 'eventTaskCompleted', 'task.replanning': 'eventTaskReplanning',
    'step.started': 'eventStepStarted', 'step.completed': 'eventStepCompleted', 'step.failed': 'eventStepFailed',
    'evidence.created': 'eventEvidenceCreated', 'decision.created': 'eventDecisionCreated',
    'run.started': 'eventRunStarted', 'run.completed': 'eventRunCompleted', 'run.failed': 'eventRunFailed',
    'model.started': 'eventModelStarted', 'model.completed': 'eventModelCompleted', 'validation.failed': 'eventValidationFailed',
    'analysis_started': 'eventAgentUnderstanding', 'candidates_generated': 'eventAgentCandidates',
    'decision_started': 'eventAgentDecision', 'decision_completed': 'eventAgentDecision',
    'decision.fallback': 'eventAgentFallback',
    'browser.agent_progress': 'eventBrowserAgentProgress', 'browser.action_started': 'eventBrowserActionStarted',
    'browser.action_completed': 'eventBrowserActionCompleted', 'browser.observation': 'eventBrowserObservation',
    'browser.agent_paused': 'eventBrowserAgentPaused', 'browser.human_takeover': 'eventBrowserHumanTakeover',
    'browser.goal_completed': 'eventBrowserGoalCompleted', 'browser.goal_blocked': 'eventBrowserGoalBlocked',
    'browser.action_blocked': 'eventBrowserActionBlocked', 'browser.loop_detected': 'eventBrowserLoopDetected',
  };
  return labels[type] ?? 'unknownEvent';
}
