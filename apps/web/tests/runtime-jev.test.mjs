import test from 'node:test';
import assert from 'node:assert/strict';
import { decisionFacts } from '../src/features/runtime/jevModel.ts';
test('AI candidate metadata is not mixed with the JEV decision result', () => {
  const events = [
    {
      type: 'step.progress',
      category: 'step',
      metadata: {
        operation: 'browser_action_candidates',
        provider: 'openai-compatible',
        model: 'deepseek-flash',
        fallback_used: false,
        latency_ms: 3557,
      },
    },
    {
      type: 'candidates_generated',
      category: 'decision',
      metadata: {
        provider: 'openai-compatible',
        model: 'deepseek-flash',
        candidate_count: 1,
        candidate_summary: '[{"candidate_id":"fill_search_selenium"}]',
        rejected_count: 0,
      },
    },
    {
      type: 'decision_started',
      category: 'decision',
      metadata: { candidate_count: 1, jev_attempted: true },
    },
    {
      type: 'browser.decision_blocked',
      category: 'browser',
      status: 'BLOCKED',
      metadata: {
        confidence: 0.24,
        minimum_confidence: 0.6,
        attempted_choice: 'fill_search_selenium',
        failure_reason: 'below_minimum_confidence',
        action_executed: false,
      },
    },
  ];
  const facts = decisionFacts(events);
  assert.equal(facts.candidateGeneration.provider, 'openai-compatible');
  assert.equal(facts.candidateGeneration.model, 'deepseek-flash');
  assert.equal(facts.candidateGeneration.fallback_used, false);
  assert.equal(facts.candidateGeneration.latency_ms, 3557);
  assert.equal(facts.candidateGeneration.candidate_count, 1);
  assert.equal(facts.jevDecision.provider, 'jev');
  assert.equal(facts.jevDecision.confidence, 0.24);
  assert.equal(facts.jevDecision.minimum_confidence, 0.6);
  assert.equal(facts.jevDecision.attempted_choice, 'fill_search_selenium');
  assert.equal(facts.jevDecision.failure_reason, 'below_minimum_confidence');
  assert.ok(!Object.hasOwn(facts.jevDecision, 'fallback_reason'));
  assert.equal(facts.jevDecision.status, 'BLOCKED');
  assert.equal(facts.jevDecision.action_executed, false);
  assert.ok(!Object.hasOwn(facts.jevDecision, 'model'));
  assert.ok(!Object.hasOwn(facts.jevDecision, 'fallback_used'));
});
