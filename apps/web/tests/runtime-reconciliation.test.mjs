import test from 'node:test';
import assert from 'node:assert/strict';
import { reconcileSnapshot } from '../src/features/runtime/reconcileSnapshot.ts';
test('Unchanged snapshots preserve identity and a new event preserves all graph records', () => {
  const before = {
    id: 't',
    kind: 'task',
    steps: [
      { id: 's1', status: 'RUNNING' },
      { id: 's2', status: 'PENDING' },
    ],
    events: [],
    summary: { failures: 0 },
  };
  assert.equal(reconcileSnapshot(before, structuredClone(before)), before);
  const incoming = structuredClone(before);
  incoming.events.push({ id: 'e1' });
  const after = reconcileSnapshot(before, incoming);
  assert.equal(after.steps, before.steps);
  assert.equal(after.summary, before.summary);
  assert.notEqual(after.events, before.events);
});
test('A changed node updates only that node, and the new runtime cannot retain old records', () => {
  const before = {
    id: 't',
    kind: 'task',
    steps: [
      { id: 's1', status: 'RUNNING' },
      { id: 's2', status: 'PENDING' },
    ],
  };
  const incoming = structuredClone(before);
  incoming.steps[0].status = 'COMPLETED';
  const after = reconcileSnapshot(before, incoming);
  assert.notEqual(after.steps[0], before.steps[0]);
  assert.equal(after.steps[1], before.steps[1]);
  assert.equal(
    reconcileSnapshot(before, { ...incoming, id: 'another' }).id,
    'another',
  );
});
