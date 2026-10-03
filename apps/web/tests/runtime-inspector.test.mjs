import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectorContext } from '../src/features/runtime/runtimeModel.ts';

test('Inspector only links recorded step IDs and never guesses unassociated AI ownership', () => {
  const snapshot = {
    steps: [{ id: 'inspect' }, { id: 'decide' }],
    decisions: [{ id: 'd', step_id: 'decide' }],
    evidence: [{ id: 'e', step_id: 'inspect' }],
    artifacts: [{ id: 'a', step_id: 'inspect' }],
    events: [
      { id: 'ai', step_id: null },
      { id: 'started', step_id: 'inspect' },
    ],
    runs: [{ id: 'run', step_id: 'decide' }],
  };
  const selected = inspectorContext(snapshot, 'inspect');
  assert.equal(selected.step.id, 'inspect');
  assert.equal(selected.artifacts.length, 1);
  assert.equal(selected.decisions.length, 0);
  assert.deepEqual(
    selected.events.map((event) => event.id),
    ['started'],
  );
  assert.equal(inspectorContext(snapshot, 'missing').step, null);
  assert.equal(inspectorContext(snapshot, null).events.length, 0);
});
