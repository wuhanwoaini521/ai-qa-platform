import test from 'node:test';
import assert from 'node:assert/strict';
import {
  mergeObservedLog,
  emptyRunState,
  reconcileRun,
  runEventReducer,
  createRunStore,
  MAX_TRACE_EVENTS,
  MAX_LOG_ENTRIES,
  MAX_LOG_CHARACTERS,
  MAX_NETWORK_EVENTS,
  MAX_BROWSER_SESSIONS,
} from '../src/features/runs/runStore.ts';

const run = (status = 'QUEUED') => ({
  id: 'run-1',
  status,
  executions: [],
  total: 2,
  passed: 0,
  failed: 0,
  duration_ms: 0,
});
const initial = () => reconcileRun(emptyRunState(), run());
test('Run lifecycle follows actual started, finished, error and cancellation events', () => {
  const started = runEventReducer(initial(), { type: 'RUN_STARTED', total: 3 });
  assert.equal(started.run.status, 'RUNNING');
  assert.equal(started.run.total, 3);
  const finished = runEventReducer(started, {
    type: 'RUN_FINISHED',
    status: 'PASSED',
    passed: 3,
    duration_ms: 42,
  });
  assert.equal(finished.run.status, 'PASSED');
  assert.equal(finished.run.duration_ms, 42);
  assert.equal(
    runEventReducer(initial(), { type: 'RUN_ERROR', error: 'failed' }).run
      .status,
    'ERROR',
  );
  assert.equal(
    runEventReducer(initial(), { type: 'RUN_CANCELLED' }).run.status,
    'CANCELLED',
  );
});
test('Repeated test events upsert results without inventing execution timestamps', () => {
  const event = {
    type: 'TEST_FINISHED',
    nodeid: 'tests/a.py::test_a',
    status: 'PASSED',
    duration_ms: 21,
  };
  const state = runEventReducer(runEventReducer(initial(), event), event);
  assert.equal(state.run.executions.length, 1);
  assert.equal(state.run.executions[0].started_at, null);
});
test('Unknown and malformed events are ignored, identified duplicates and cross-run events are rejected', () => {
  const state = initial();
  assert.equal(runEventReducer(state, { type: 'future_event' }), state);
  assert.equal(runEventReducer(state, null), state);
  assert.equal(
    runEventReducer(state, { type: 'LOG_STREAM', run_id: 'other', log: 'x' }),
    state,
  );
  const event = { id: 42, type: 'LOG_STREAM', log: 'hello' };
  const next = runEventReducer(state, event);
  assert.equal(runEventReducer(next, event), next);
});
test('Terminal state survives late RUN_STARTED and stale reconnect snapshots', () => {
  const state = runEventReducer(initial(), { type: 'RUN_CANCELLED' });
  assert.equal(runEventReducer(state, { type: 'RUN_STARTED' }), state);
  assert.equal(reconcileRun(state, run('RUNNING')).run.status, 'CANCELLED');
});
test('Logs, trace, telemetry and browser frames stay bounded; frames never enter trace', () => {
  let state = initial();
  state = runEventReducer(state, {
    type: 'BROWSER_SESSION',
    session: { browser_session_id: 's1', page_evidence: {} },
  });
  for (let i = 0; i < 800; i++) {
    state = runEventReducer(state, {
      type: 'LOG_STREAM',
      log: 'x'.repeat(100),
    });
    state = runEventReducer(state, {
      type: 'BROWSER_TELEMETRY',
      session_id: 's1',
      channel: 'network',
      entry: { url: `/${i}` },
    });
  }
  assert.equal(state.events.length, MAX_TRACE_EVENTS);
  assert.equal(state.logs.length, MAX_LOG_ENTRIES);
  assert.equal(state.run.log_output.length, MAX_LOG_CHARACTERS);
  assert.equal(
    state.sessions[0].page_evidence.network_logs.length,
    MAX_NETWORK_EVENTS,
  );
  const count = state.events.length;
  for (let i = 0; i < 80; i++)
    state = runEventReducer(state, {
      type: 'BROWSER_FRAME',
      session_id: `frame-${i}`,
      frame: 'abcd',
      prompt: 'secret',
    });
  assert.equal(Object.keys(state.frames).length, MAX_BROWSER_SESSIONS);
  assert.equal(state.events.length, count);
  assert.ok(!JSON.stringify(state.events).includes('abcd'));
});
test('Reconnect preserves logs, frames and live browser evidence missing from snapshot', () => {
  let state = runEventReducer(initial(), {
    type: 'BROWSER_SESSION',
    session: { browser_session_id: 's1', page_evidence: {} },
  });
  state = runEventReducer(state, {
    type: 'BROWSER_TELEMETRY',
    session_id: 's1',
    channel: 'step',
    entry: { action: 'click' },
  });
  state = runEventReducer(state, {
    type: 'BROWSER_FRAME',
    session_id: 's1',
    frame: 'abcd',
  });
  state = runEventReducer(state, { type: 'LOG_STREAM', log: 'hello' });
  const next = reconcileRun(
    runEventReducer(state, { type: 'CONNECTED' }),
    run('RUNNING'),
  );
  assert.equal(next.run.log_output, 'hello');
  assert.equal(next.frames.s1, state.frames.s1);
  assert.equal(next.sessions[0].page_evidence.recent_steps.length, 1);
});
test('Two consumers share one transport and teardown waits for the final unsubscribe', async () => {
  let opened = 0,
    closed = 0,
    onEvent,
    onError;
  const store = createRunStore('run-1', {
    getRun: async () => run('RUNNING'),
    stream: (_id, event, error) => {
      opened++;
      onEvent = event;
      onError = error;
      return () => closed++;
    },
    permanentError: () => false,
  });
  const a = store.subscribe(() => {}),
    b = store.subscribe(() => {});
  await store.refresh();
  assert.equal(opened, 1);
  onEvent({ type: 'LOG_STREAM', log: 'visible from both' });
  onError(new Error('disconnect'));
  assert.equal(store.getSnapshot().streamStatus, 'reconnecting');
  assert.equal(store.getSnapshot().run.log_output, 'visible from both');
  a();
  assert.equal(closed, 0);
  b();
  assert.equal(closed, 1);
});
test('A slow initial snapshot cannot overwrite newer live events; callbacks after dispose are inert', async () => {
  let resolve, onEvent;
  const store = createRunStore('run-1', {
    getRun: () => new Promise((done) => (resolve = done)),
    stream: (_id, event) => {
      onEvent = event;
      return () => {};
    },
    permanentError: () => false,
  });
  const off = store.subscribe(() => {});
  onEvent({ type: 'RUN_STARTED' });
  resolve(run('RUNNING'));
  await store.refresh();
  onEvent({ type: 'LOG_STREAM', log: 'saved' });
  off();
  const saved = store.getSnapshot();
  onEvent({ type: 'LOG_STREAM', log: 'discard' });
  assert.equal(store.getSnapshot(), saved);
});
test('Terminal event before initial fetch is preserved and final durable details are reconciled', async () => {
  let resolve,
    onEvent,
    calls = 0;
  const store = createRunStore('run-1', {
    getRun: () =>
      ++calls === 1
        ? new Promise((done) => (resolve = done))
        : Promise.resolve({ ...run('ERROR'), log_output: 'durable failure' }),
    stream: (_id, event) => {
      onEvent = event;
      return () => {};
    },
    permanentError: () => false,
  });
  const off = store.subscribe(() => {});
  onEvent({ type: 'RUN_ERROR', error: 'runner failed' });
  resolve(run('RUNNING'));
  await store.refresh();
  assert.equal(store.getSnapshot().run.status, 'ERROR');
  assert.equal(store.getSnapshot().run.log_output, 'durable failure');
  off();
});

test('Concurrent log already included in a slow durable snapshot is not appended twice', async () => {
  for (const included of [true, false]) {
    let resolve, onEvent;
    const store = createRunStore('run-1', {
      getRun: () => new Promise((done) => (resolve = done)),
      stream: (_id, event) => {
        onEvent = event;
        return () => {};
      },
      permanentError: () => false,
    });
    const off = store.subscribe(() => {});
    onEvent({ type: 'LOG_STREAM', log: 'one actual line\n' });
    resolve({
      ...run('RUNNING'),
      log_output: included ? 'one actual line\n' : '',
    });
    await store.refresh();
    assert.equal(store.getSnapshot().run.log_output, 'one actual line\n');
    off();
  }
});

test('Rolling log observations align overlap while retaining genuinely repeated lines', () => {
  assert.equal(
    mergeObservedLog('old\nshared\n', 'shared\nnew\n'),
    'old\nshared\nnew\n',
  );
  assert.equal(mergeObservedLog('same\n', 'same\nsame\n'), 'same\nsame\n');
  assert.equal(mergeObservedLog('same\nsame\n', 'same\n'), 'same\nsame\n');
});

test('Equal-length browser buffers retain newer recorded entries and terminal session state', () => {
  const old = { url: '/same', timestamp: '2026-10-02T00:00:00Z' },
    later = { url: '/same', timestamp: '2026-10-02T00:00:01Z' };
  const state = {
    ...initial(),
    sessions: [
      {
        browser_session_id: 's',
        status: 'finished',
        finished_at: '2026-10-02T00:00:02Z',
        page_evidence: { network_logs: [later] },
      },
    ],
  };
  const reconciled = reconcileRun(state, {
    ...run('RUNNING'),
    browser_sessions: [
      {
        browser_session_id: 's',
        status: 'running',
        page_evidence: { network_logs: [old] },
      },
    ],
  });
  assert.deepEqual(reconciled.sessions[0].page_evidence.network_logs, [
    old,
    later,
  ]);
  assert.equal(reconciled.sessions[0].status, 'finished');
});


test('Equal-length rolling log snapshots retain the newest tail and replacement frames are idempotent', () => {
  const oldLog = 'a'.repeat(MAX_LOG_CHARACTERS - 4) + 'old!';
  const newLog = 'a'.repeat(MAX_LOG_CHARACTERS - 4) + 'new!';
  let state = reconcileRun(initial(), { ...run('RUNNING'), log_output: oldLog });
  state = reconcileRun(state, { ...run('RUNNING'), log_output: newLog });
  assert.equal(state.run.log_output, newLog);
  state = runEventReducer(state, { type: 'LOG_STREAM', log: newLog, replace: true });
  state = runEventReducer(state, { type: 'LOG_STREAM', log: newLog, replace: true });
  assert.equal(state.run.log_output, newLog);
  const latest = 'b'.repeat(MAX_LOG_CHARACTERS);
  state = runEventReducer(state, { type: 'LOG_STREAM', log: latest, replace: true });
  assert.equal(reconcileRun(state, { ...run('RUNNING'), log_output: oldLog }, true).run.log_output, latest);
});
