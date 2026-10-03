import test from 'node:test';
import assert from 'node:assert/strict';
import { traceState } from '../src/features/runtime/traceState.ts';
const event = (type, run_id, step_id) => ({
  type,
  run_id,
  step_id,
  metadata: {},
});
test('A completed parallel invocation cannot complete another trace or step', () => {
  const events = [
    event('model.started', 'trace-a', 'step-a'),
    event('model.started', 'trace-b', 'step-b'),
    event('model.completed', 'trace-b', 'step-b'),
  ];
  assert.equal(traceState(events, 0, true), 'active');
  assert.equal(traceState(events, 1, true), 'done');
  assert.equal(traceState(events, 0, false), 'pending');
});
test('Explicit step completion and failure pair only with the same runtime step', () => {
  assert.equal(
    traceState(
      [event('step.started', '', 's1'), event('step.failed', '', 's1')],
      0,
      false,
    ),
    'error',
  );
  assert.equal(
    traceState(
      [event('step.started', '', 's1'), event('step.completed', '', 's1')],
      0,
      false,
    ),
    'done',
  );
});

test('Different real TestRuns cannot complete each other when no AI or step ID exists', () => {
  const events = [
    {
      ...event('run.started', '', null),
      metadata: { test_run_id: 'one', runtime_id: 'task' },
    },
    {
      ...event('run.completed', '', null),
      metadata: { test_run_id: 'two', runtime_id: 'task' },
    },
  ];
  assert.equal(traceState(events, 0, true), 'active');
  events.push({
    ...event('run.completed', '', null),
    metadata: { test_run_id: 'one', runtime_id: 'task' },
  });
  assert.equal(traceState(events, 0, true), 'done');
});

test('Recorded HTTP failures and console errors are visible without invented lifecycle events', () => {
  assert.equal(
    traceState(
      [
        {
          ...event('browser.network_logs', '', null),
          metadata: { status: 503 },
        },
      ],
      0,
      false,
    ),
    'error',
  );
  assert.equal(
    traceState(
      [
        {
          ...event('browser.console_logs', '', null),
          metadata: { level: 'error' },
        },
      ],
      0,
      false,
    ),
    'error',
  );
});
