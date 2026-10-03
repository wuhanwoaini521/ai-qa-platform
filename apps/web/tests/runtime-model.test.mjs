import test from 'node:test';
import assert from 'node:assert/strict';
import {
  durationLabel,
  spanDuration,
  currentSteps,
  overviewFacts,
} from '../src/features/runtime/runtimeModel.ts';

test('Runtime header shows unavailable timings without inventing zeros', () => {
  assert.equal(durationLabel(null), '—');
  assert.equal(durationLabel(NaN), '—');
  assert.equal(durationLabel(2000), '2.0s');
  assert.equal(
    spanDuration(
      { status: 'RUNNING', started_at: null, duration_ms: null },
      1000,
    ),
    null,
  );
});
test('Overview derives progress, actual next dependencies, slowest step and test aggregates', () => {
  const facts = overviewFacts({
    steps: [
      { id: 'inspect', key: 'inspect', status: 'COMPLETED', duration_ms: 2000 },
      { id: 'run', key: 'run', status: 'RUNNING', duration_ms: null },
      { id: 'verify', key: 'verify', status: 'PENDING', duration_ms: null },
    ],
    summary: { active_step_ids: ['run'], next_step_ids: [] },
    runs: [{ total: 4, passed: 3, failed: 1 }],
  });
  assert.deepEqual(
    facts.active.map((step) => step.id),
    ['run'],
  );
  assert.equal(facts.next.length, 0);
  assert.equal(facts.slowest.id, 'inspect');
  assert.deepEqual(facts.tests, { total: 4, passed: 3, failed: 1 });
});
test('Runtime elapsed uses actual recorded start and freezes terminal duration', () => {
  assert.equal(
    spanDuration(
      {
        status: 'RUNNING',
        started_at: '2026-10-02T00:00:00Z',
        duration_ms: null,
      },
      Date.parse('2026-10-02T00:00:05Z'),
    ),
    5000,
  );
  assert.equal(
    spanDuration(
      {
        status: 'COMPLETED',
        started_at: '2026-10-02T00:00:00Z',
        duration_ms: 2400,
      },
      Date.now(),
    ),
    2400,
  );
});
test('Header supports multiple real active siblings without inventing a current step', () => {
  const snapshot = {
    steps: [
      { id: 'a', key: 'source' },
      { id: 'b', key: 'browser' },
      { id: 'c', key: 'decision' },
    ],
    summary: { active_step_ids: ['a', 'b'] },
  };
  assert.deepEqual(
    currentSteps(snapshot).map((step) => step.key),
    ['source', 'browser'],
  );
});

test('Finished AI timings freeze and lowercase browser timings grow only while running', () => {
  assert.equal(
    spanDuration(
      {
        status: 'SUCCESS',
        started_at: '2026-10-02T00:00:00Z',
        finished_at: '2026-10-02T00:00:02Z',
        duration_ms: 2000,
      },
      Date.now(),
    ),
    2000,
  );
  assert.equal(
    spanDuration(
      {
        status: 'running',
        started_at: '2026-10-02T00:00:00Z',
        finished_at: null,
        duration_ms: null,
      },
      Date.parse('2026-10-02T00:00:05Z'),
    ),
    5000,
  );
  assert.equal(
    spanDuration(
      {
        status: 'PENDING',
        started_at: null,
        finished_at: null,
        duration_ms: null,
      },
      Date.now(),
    ),
    null,
  );
});
test('Overview keeps child runs separate from parent chain test totals', () => {
  const snapshot = {
    steps: [],
    summary: { active_step_ids: [], next_step_ids: [] },
    runs: [{ total: 1, passed: 1, failed: 0 }],
    run_ancestors: [{ total: 7, passed: 3, failed: 4 }],
  };
  assert.equal(overviewFacts(snapshot).tests.total, 1);
});
