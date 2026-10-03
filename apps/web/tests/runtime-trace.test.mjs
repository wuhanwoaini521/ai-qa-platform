import test from 'node:test';
import assert from 'node:assert/strict';
import {
  filterTrace,
  traceAdapter,
} from '../src/features/runtime/traceModel.ts';
const events = [
  {
    id: 'a',
    type: 'decision_completed',
    category: 'decision',
    status: 'COMPLETED',
    step_id: 's',
    trace_run_id: 'trace',
    test_run_id: 'test',
    timestamp: null,
    metadata: { provider: 'jev', verified: false },
  },
  { id: 'b', category: 'ai', status: 'COMPLETED', step_id: null, metadata: {} },
];
test('Trace filters actual categories and verification failures without changing order', () => {
  assert.deepEqual(
    filterTrace(events, 'Decision', true).map((e) => e.id),
    ['a'],
  );
  assert.equal(filterTrace(events, 'AI', true).length, 0);
  assert.equal(filterTrace(events, 'All', false, 's').length, 1);
});
test('Trace adapter preserves trace identity and unavailable time', () => {
  assert.equal(traceAdapter(events[0]).run_id, 'trace');
  assert.equal(traceAdapter(events[0]).timestamp, null);
  assert.equal(traceAdapter(events[1]).run_id, '');
  assert.equal(traceAdapter(events[0]).metadata.verified, false);
});
test('Shared selection filters only explicit step IDs and clearing restores unassigned events', () => {
  assert.deepEqual(
    filterTrace(events, 'All', false, 's').map((e) => e.id),
    ['a'],
  );
  assert.equal(filterTrace(events, 'All', false).length, 2);
  assert.equal(filterTrace(events, 'All', false, 'missing').length, 0);
});

test('Browser error filter includes actual HTTP status and console errors', () => {
  const records = [
    { category: 'browser', metadata: { status: 500 } },
    { category: 'browser', metadata: { level: 'error' } },
    { category: 'browser', metadata: { status: 200 } },
  ];
  assert.equal(filterTrace(records, 'Browser', true).length, 2);
});
