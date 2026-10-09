import type { RuntimeEvent } from '../../types/runtime';
const AI_CANDIDATE_FIELDS = [
  'provider',
  'model',
  'fallback_used',
  'latency_ms',
  'input_tokens',
  'output_tokens',
  'candidate_count',
  'candidate_summary',
  'candidate_scores',
  'rejected_count',
  'ai_preference',
  'planner_mode',
] as const;

const JEV_DECISION_FIELDS = [
  'provider',
  'model',
  'candidate_count',
  'candidate_id',
  'selected_locator',
  'choice',
  'attempted_choice',
  'confidence',
  'minimum_confidence',
  'latency_ms',
  'verified',
  'fallback_reason',
  'fallback_used',
  'failure_reason',
  'action_executed',
  'jev_attempted',
] as const;

function mergeFields(events: RuntimeEvent[], keys: readonly string[]) {
  const result: Record<string, unknown> = {};
  for (const event of events) {
    for (const key of keys) {
      if (Object.hasOwn(event.metadata, key)) result[key] = event.metadata[key];
    }
  }
  return result;
}

export function decisionFacts(events: RuntimeEvent[]) {
  const candidateEvents = events.filter(
    (event) =>
      event.metadata.operation === 'browser_action_candidates' ||
      event.type === 'candidates_generated',
  );
  const jevEvents = events.filter(
    (event) =>
      (event.category === 'decision' && event.type !== 'candidates_generated') ||
      event.type === 'browser.decision_blocked',
  );
  const jevDecision = mergeFields(jevEvents, JEV_DECISION_FIELDS);
  const jevAttempted = jevEvents.some((event) => event.metadata.jev_attempted === true);
  if (jevAttempted && !jevDecision.provider) jevDecision.provider = 'jev';
  if (jevAttempted) jevDecision.jev_attempted = true;

  const blocked = [...jevEvents].reverse().find((event) => event.type === 'browser.decision_blocked');
  if (blocked) {
    if (jevDecision.status === undefined) jevDecision.status = blocked.status ?? 'BLOCKED';
  }

  return {
    candidateGeneration: mergeFields(candidateEvents, AI_CANDIDATE_FIELDS),
    jevDecision,
  };
}
