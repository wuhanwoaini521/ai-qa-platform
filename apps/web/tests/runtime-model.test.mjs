import test from 'node:test';
import assert from 'node:assert/strict';
import {
  durationLabel,
  spanDuration,
  currentSteps,
  overviewFacts,
  stepCounts,
  nextAction,
  retryActionLabel,
  retryGuidance,
  runtimeStatusKey,
  runtimeNeedsTerminalRefresh,
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

test('Blocked repair remains the current step and downstream pending work is identified as blocked', () => {
  const keys = ['collect', 'classify', 'inspect', 'diagnose', 'repair', 'approval', 'apply', 'validate', 'target_run', 'regression', 'verify'];
  const steps = keys.map((key, index) => ({
    id: key,
    key,
    status: index < 4 ? 'COMPLETED' : index === 4 ? 'FAILED' : 'PENDING',
    dependencies: index === 0 ? [] : [keys[index - 1]],
  }));
  const snapshot = {
    status: 'BLOCKED',
    blocking: { step_id: 'repair', step_key: 'repair', recovery_actions: ['retry_step', 'replan'] },
    task: { current_step_id: 'repair' },
    steps,
    summary: { active_step_ids: [], next_step_ids: [] },
  };
  assert.deepEqual(currentSteps(snapshot).map((step) => step.key), ['repair']);
  assert.deepEqual(stepCounts(snapshot), {
    completed: 4, failed: 1, pending: 6, blocked: 6, blockedStepIds: ['approval', 'apply', 'validate', 'target_run', 'regression', 'verify'], skipped: 0, remaining: 6, total: 11,
  });
  assert.equal(nextAction(snapshot), 'retry');
});

test('Skipped steps are terminal work and do not remain in the pending total', () => {
  assert.deepEqual(stepCounts({ steps: [
    { id: 'done', key: 'done', status: 'COMPLETED' },
    { id: 'skip', key: 'skip', status: 'SKIPPED' },
    { id: 'pending', key: 'pending', status: 'PENDING' },
  ] }), {
    completed: 1, failed: 0, pending: 1, blocked: 0, blockedStepIds: [], skipped: 1, remaining: 1, total: 3,
  });
});

test('Sub-100ms timings are shown as markers instead of rounded zero', () => {
  assert.equal(durationLabel(0), '<100ms');
  assert.equal(durationLabel(99), '<100ms');
  assert.equal(durationLabel(100), '0.1s');
});

test('Recovery labels and prompts follow the task type', () => {
  assert.equal(retryActionLabel('CREATE_TEST'), 'retryCreateTest');
  assert.equal(retryActionLabel('FIX_FAILURE'), 'retryRepair');
  assert.match(retryGuidance('CREATE_TEST'), /test-generation step/);
  assert.match(retryGuidance('OPTIMIZE_TEST'), /test-optimization step/);
  assert.match(retryGuidance('EXPLORE_PAGE'), /page-exploration step/);
  assert.match(retryGuidance('REVIEW_TEST'), /test-review step/);
  assert.match(retryGuidance('UNKNOWN'), /workflow step/);
});

test('Runtime status labels normalize known workflow states', () => {
  assert.equal(runtimeStatusKey('WAITING_FOR_APPROVAL'), 'waitingApproval');
  assert.equal(runtimeStatusKey('PENDING'), 'pending');
  assert.equal(runtimeStatusKey('QUEUED'), 'queued');
  assert.equal(runtimeStatusKey('SUCCESS'), 'success');
  assert.equal(runtimeNeedsTerminalRefresh('BLOCKED'), true);
  assert.equal(runtimeNeedsTerminalRefresh('FAILED'), true);
  assert.equal(runtimeNeedsTerminalRefresh('COMPLETED'), false);
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
