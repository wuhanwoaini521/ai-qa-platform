import test from 'node:test';
import assert from 'node:assert/strict';
import { decisionFacts } from '../src/features/runtime/jevModel.ts';
test('JEV attempt remains in trace and fallback summary does not carry old confidence', () => {
  const events = [
    {
      metadata: {
        provider: 'jev',
        candidate_id: 'first',
        confidence: 0.9,
        candidate_count: 2,
      },
    },
    { metadata: { verified: false } },
    {
      metadata: {
        provider: 'local-strategy',
        candidate_id: 'second',
        confidence: null,
        verified: true,
        fallback_used: true,
        fallback_reason: 'selected_candidate_failed_verification',
      },
    },
  ];
  const facts = decisionFacts(events);
  assert.equal(events[0].metadata.provider, 'jev');
  assert.equal(facts.provider, 'local-strategy');
  assert.equal(facts.confidence, null);
  assert.equal(facts.candidate_count, 2);
  assert.equal(facts.verified, true);
  assert.equal(facts.fallback_used, true);
  assert.ok(!Object.hasOwn(facts, 'scores'));
});
