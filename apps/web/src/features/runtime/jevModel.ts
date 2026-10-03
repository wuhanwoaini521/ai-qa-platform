import type { RuntimeEvent } from '../../types/runtime';
export function decisionFacts(events: RuntimeEvent[]) {
  const facts: Record<string, unknown> = {};
  for (const event of events) {
    for (const key of [
      'provider',
      'model',
      'candidate_count',
      'candidate_id',
      'selected_locator',
      'confidence',
      'latency_ms',
      'verified',
      'fallback_reason',
      'fallback_used',
    ]) {
      if (Object.hasOwn(event.metadata, key)) facts[key] = event.metadata[key];
    }
  }
  return facts;
}
