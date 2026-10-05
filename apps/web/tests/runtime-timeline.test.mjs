import test from 'node:test';
import assert from 'node:assert/strict';
import {
  spanBounds,
  timelineDomain,
  timelineRange,
  timelineSpans,
  isShortSpan,
} from '../src/features/runtime/timelineModel.ts';
const start = '2026-10-02T00:00:00Z',
  now = Date.parse(start) + 5000;
test('Running bars grow from actual start and completed spans freeze', () => {
  assert.equal(
    spanBounds({ started_at: start, status: 'RUNNING' }, now).end -
      spanBounds({ started_at: start, status: 'RUNNING' }, now).start,
    5000,
  );
  assert.equal(
    spanBounds(
      {
        started_at: start,
        finished_at: '2026-10-02T00:00:02Z',
        status: 'COMPLETED',
      },
      now + 9000,
    ).end,
    Date.parse(start) + 2000,
  );
});
test('Unavailable and invalid timestamps never become zero-width spans', () => {
  assert.equal(spanBounds({ status: 'PENDING', started_at: null }, now), null);
  assert.equal(
    spanBounds(
      { started_at: start, finished_at: 'bad', status: 'COMPLETED' },
      now,
    ),
    null,
  );
  assert.equal(timelineRange([], now), null);
  assert.equal(
    timelineRange([{ status: 'RUNNING', started_at: start }], now).duration,
    30000,
  );
});
test('Known sub-100ms spans use a marker threshold while missing timing stays unknown', () => {
  assert.equal(isShortSpan({ duration_ms: 0, status: 'FAILED' }, now), true);
  assert.equal(isShortSpan({ duration_ms: 99, status: 'COMPLETED' }, now), true);
  assert.equal(isShortSpan({ duration_ms: null, status: 'COMPLETED' }, now), false);
});
test('Unified lanes use only supplied domain records', () => {
  assert.deepEqual(
    timelineSpans({
      task: { id: 't' },
      steps: [{ id: 's' }],
      runs: [{ id: 'r' }],
      executions: [{ id: 'e' }],
      browser_sessions: [],
      ai_invocations: [],
    }).map((s) => s.id),
    ['t', 's', 'r', 'e'],
  );
  assert.equal(
    timelineSpans({
      task: null,
      steps: [],
      runs: [],
      executions: [],
      browser_sessions: [],
      ai_invocations: [],
    }).length,
    0,
  );
});

test('A real ten-minute active span remains in view without changing completed row scale each second', () => {
  const measured = timelineRange(
    [{ status: 'RUNNING', started_at: start }],
    Date.parse(start) + 600000,
  );
  const capacity = timelineDomain(30000, measured.duration, 1);
  assert.ok(capacity >= measured.duration);
  assert.equal(timelineDomain(30000, measured.duration + 1000, 1), capacity);
  assert.equal(timelineDomain(30000, measured.duration, 2), capacity / 2);
});
