import test from 'node:test';
import assert from 'node:assert/strict';
import { appendProgress } from '../src/features/runtime/progressModel.ts';
test('Progress keeps actual stages bounded, deduplicated and excludes model content/results', () => {
  let events = [];
  for (let i = 0; i < 600; i++)
    events = appendProgress(events, {
      event_id: String(i),
      type: 'model.started',
      title: 'Actual request',
      content: 'private',
    });
  assert.equal(events.length, 500);
  assert.equal(events[0].event_id, '100');
  assert.ok(!Object.hasOwn(events[0], 'content'));
  assert.equal(appendProgress(events, events[0]), events);
  assert.equal(
    appendProgress(events, {
      event_id: 'delta',
      type: 'model.delta',
      content: 'hidden',
    }),
    events,
  );
  assert.equal(
    appendProgress(events, {
      event_id: 'result',
      type: 'operation.result',
      content: 'code',
    }),
    events,
  );
});
