import test from 'node:test';
import assert from 'node:assert/strict';
import { summarizeTrace } from '../src/features/runtime/traceSummaryModel.ts';

const event = (id, type, extra = {}) => ({
  id,
  type,
  category: type.startsWith('step.') || type === 'evidence.created' ? 'step' : 'lifecycle',
  status: type.endsWith('completed') ? 'COMPLETED' : type.endsWith('failed') ? 'FAILED' : 'RUNNING',
  step_id: type.startsWith('task.') ? null : 'collect',
  timestamp: `2026-10-03T09:40:0${id}Z`,
  duration_ms: null,
  metadata: {},
  ...extra,
});

test('Summary Trace groups step lifecycle and evidence while retaining expandable raw events', () => {
  const snapshot = {
    steps: [{ id: 'collect', key: 'collect', title: 'Collect failure evidence', status: 'COMPLETED', duration_ms: 110 }],
  };
  const groups = summarizeTrace([
    event('1', 'step.started'),
    event('2', 'evidence.created'),
    event('3', 'step.completed', { duration_ms: 110 }),
  ], snapshot);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].title, 'Collect failure evidence');
  assert.equal(groups[0].status, 'COMPLETED');
  assert.equal(groups[0].durationMs, 110);
  assert.equal(groups[0].evidenceCount, 1);
  assert.equal(groups[0].events.length, 3);
});

test('Blocked repair stays a failed human-readable group with the actual error attached at the step', () => {
  const snapshot = {
    steps: [{ id: 'repair', key: 'repair', title: 'Prepare repair proposal', status: 'FAILED', duration_ms: null, error: 'AI did not return executable source code.' }],
  };
  const groups = summarizeTrace([event('1', 'step.started', { step_id: 'repair' }), event('2', 'step.failed', { step_id: 'repair', status: 'FAILED' })], snapshot);
  assert.equal(groups[0].title, 'Prepare repair proposal');
  assert.equal(groups[0].status, 'FAILED');
});

test('Task lifecycle keeps an explicit blocked terminal state in the trace summary', () => {
  const snapshot = { steps: [] };
  const groups = summarizeTrace([
    event('1', 'task.started', { step_id: null }),
    event('2', 'task.blocked', { step_id: null, status: 'BLOCKED' }),
  ], snapshot);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].status, 'BLOCKED');
});
