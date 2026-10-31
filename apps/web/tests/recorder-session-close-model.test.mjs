import test from 'node:test';
import assert from 'node:assert/strict';

const {
  canStartRecorderClose,
  canStartRecorderSessionWork,
  canSendRecorderSessionCommand,
  acknowledgeRecorderNavigationCommand,
  prepareNextPendingRecorderNavigationCommand,
  reconcilePendingRecorderNavigationCommands,
  tryPersistPendingRecorderNavigationCommandsForSession,
  tryRestorePendingRecorderNavigationCommandsForSession,
  shouldApplyRecorderSessionCloseCleanup,
  shouldReconcileRecorderCommands,
  shouldConnectRecorderSessionSocket,
  isRecorderSessionAlreadyClosed,
  canCloseRecorderSession,
  isRecorderCloseRetryBlocked,
  recorderBrowserCommandBlocksClose,
  recorderBrowserCommandMayNavigate,
  recorderNavigationPendingAfterCommand,
  recorderNavigationPendingAfterSnapshot,
  recorderNavigationPendingAfterError,
  recorderNavigationPendingAfterReconnect,
  isQueueableRecorderNavigationCommand,
  recorderStepSnapshotPendingAfterCommandError,
  recorderStepSnapshotPendingAfterSnapshot,
  recorderErrorRecoveryFor,
} = await import('../src/pages/recorderSessionCloseModel.ts');

test('session-bound work is blocked only for the session whose close is in flight', () => {
  assert.equal(canStartRecorderSessionWork('session-1', null), true);
  assert.equal(canStartRecorderSessionWork('session-1', 'session-1'), false);
  assert.equal(canStartRecorderSessionWork('session-2', 'session-1'), true);
  assert.equal(canStartRecorderSessionWork(null, null), false);
});

test('dispatching Recorder commands remains enabled for another session during close', () => {
  assert.equal(canSendRecorderSessionCommand('session-a', 'session-a'), false);
  assert.equal(canSendRecorderSessionCommand('session-b', 'session-a'), true);
  assert.equal(canSendRecorderSessionCommand(null, 'session-a'), false);
});

test('an earlier session close cannot tear down a newly selected Recorder session', () => {
  assert.equal(shouldApplyRecorderSessionCloseCleanup('session-a', 'session-a'), true);
  assert.equal(shouldApplyRecorderSessionCloseCleanup('session-b', 'session-a'), false);
  assert.equal(shouldApplyRecorderSessionCloseCleanup(null, 'session-a'), false);
});

test('unacknowledged Recorder commands reconcile only on the first snapshot after reconnect', () => {
  for (const type of ['frame', 'navigating', 'error']) {
    assert.equal(shouldReconcileRecorderCommands(false, type), true, type);
  }
  for (const type of ['command_success', 'command_error']) {
    assert.equal(shouldReconcileRecorderCommands(false, type), false, type);
  }
  assert.equal(shouldReconcileRecorderCommands(true, 'frame'), false);
});

test('Recorder close is single-flight for an active session', () => {
  assert.equal(canStartRecorderClose('session-1', null), true);
  assert.equal(canStartRecorderClose(null, null), false);
  assert.equal(canStartRecorderClose('session-1', 'session-1'), false);
  assert.equal(canStartRecorderClose('session-2', 'session-1'), false);
});

test('Recorder socket bootstrap is suppressed while closing, after close, or after effect cleanup', () => {
  assert.equal(shouldConnectRecorderSessionSocket('session-1', true, null, null), true);
  assert.equal(shouldConnectRecorderSessionSocket('session-1', false, null, null), false);
  assert.equal(shouldConnectRecorderSessionSocket('session-1', true, 'session-1', null), false);
  assert.equal(shouldConnectRecorderSessionSocket('session-1', true, null, 'session-1'), false);
  assert.equal(shouldConnectRecorderSessionSocket('session-2', true, 'session-1', 'session-1'), true);
});

test('a 404 during Recorder close means the session is already gone; other failures stay visible', () => {
  assert.equal(isRecorderSessionAlreadyClosed({ status: 404 }), true);
  assert.equal(isRecorderSessionAlreadyClosed({ status: 503 }), false);
  assert.equal(isRecorderSessionAlreadyClosed(new Error('network unavailable')), false);
});

test('Recorder close waits until page, Agent, and locator work has settled', () => {
  const ready = {
    closePending: false,
    pageBusy: false,
    taskStarting: false,
    taskRunning: false,
    agentGoalPending: false,
    locatorAnalysisBusy: false,
  };
  assert.equal(canCloseRecorderSession(ready), true);
  for (const activeField of Object.keys(ready)) {
    assert.equal(canCloseRecorderSession({ ...ready, [activeField]: true }), false, activeField);
  }
});

test('Recorder page work classifies state-changing WebSocket commands for the close gate', () => {
  for (const action of ['navigate', 'back', 'forward', 'reload', 'click', 'press', 'verify_locator']) {
    assert.equal(recorderBrowserCommandBlocksClose(action), true, action);
  }
  for (const action of ['move', 'wheel', 'clear_hover']) {
    assert.equal(recorderBrowserCommandBlocksClose(action), false, action);
  }
  for (const action of ['navigate', 'back', 'forward', 'reload', 'click', 'double_click', 'press']) {
    assert.equal(recorderBrowserCommandMayNavigate(action), true, action);
  }
  assert.equal(recorderBrowserCommandMayNavigate('fill'), false);
});

test('reconnect preserves unsent navigation and inherits active navigation from the first snapshot', () => {
  assert.equal(isQueueableRecorderNavigationCommand('navigate'), true);
  assert.equal(isQueueableRecorderNavigationCommand('back'), true);
  assert.equal(isQueueableRecorderNavigationCommand('reload'), true);
  assert.equal(isQueueableRecorderNavigationCommand('click'), false);
  assert.equal(isQueueableRecorderNavigationCommand('press'), false);

  assert.equal(recorderNavigationPendingAfterReconnect(2, 'frame'), 2);
  assert.equal(recorderNavigationPendingAfterReconnect(2, 'error'), 2);
  assert.equal(recorderNavigationPendingAfterReconnect(2, 'navigating'), 3);
  assert.equal(recorderNavigationPendingAfterReconnect(0, 'frame'), 0);
});

test('a sent navigation stays queued across disconnect and deduplicates after reconnect', () => {
  const pending = [
    { command_id: 'nav-1', action: 'reload', payload: {} },
    { command_id: 'nav-2', action: 'navigate', payload: { url: 'http://127.0.0.1:5183/' } },
  ];

  const sent = prepareNextPendingRecorderNavigationCommand(pending, false);
  assert.equal(sent.command?.command_id, 'nav-1');
  assert.deepEqual(sent.pending, pending);
  assert.equal(prepareNextPendingRecorderNavigationCommand(sent.pending, true).command, null);

  const afterDisconnect = reconcilePendingRecorderNavigationCommands(sent.pending, []);
  assert.deepEqual(afterDisconnect, pending);
  assert.equal(prepareNextPendingRecorderNavigationCommand(afterDisconnect, false).command?.command_id, 'nav-1');

  const afterAppliedSnapshot = reconcilePendingRecorderNavigationCommands(sent.pending, ['nav-1']);
  assert.deepEqual(afterAppliedSnapshot, [pending[1]]);
  assert.equal(prepareNextPendingRecorderNavigationCommand(afterAppliedSnapshot, false).command?.command_id, 'nav-2');
  assert.deepEqual(acknowledgeRecorderNavigationCommand(afterAppliedSnapshot, 'nav-2'), []);
});

test('navigation commands persist per session and restore after route or session changes', () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const pending = [
    { command_id: 'nav-pending-1', action: 'navigate', payload: { url: 'https://example.test/account?token=private' } },
  ];

  assert.equal(tryPersistPendingRecorderNavigationCommandsForSession(storage, 'session-1', pending), true);
  assert.deepEqual(tryRestorePendingRecorderNavigationCommandsForSession(storage, 'session-2'), {
    commands: [],
    available: true,
  });
  assert.deepEqual(tryRestorePendingRecorderNavigationCommandsForSession(storage, 'session-1'), {
    commands: pending,
    available: true,
  });
  assert.equal(tryPersistPendingRecorderNavigationCommandsForSession(storage, 'session-1', []), true);
  assert.deepEqual(tryRestorePendingRecorderNavigationCommandsForSession(storage, 'session-1'), {
    commands: [],
    available: true,
  });
});

test('navigation outbox reports unavailable storage instead of claiming persistence', () => {
  const storage = {
    getItem: () => { throw new Error('denied'); },
    setItem: () => { throw new Error('denied'); },
    removeItem: () => { throw new Error('denied'); },
  };

  assert.deepEqual(tryRestorePendingRecorderNavigationCommandsForSession(storage, 'session-1'), {
    commands: [],
    available: false,
  });
  assert.equal(tryPersistPendingRecorderNavigationCommandsForSession(storage, 'session-1', []), false);
});

test('an error snapshot settles only navigation commands processed before that snapshot', () => {
  let pending = 0;
  pending = recorderNavigationPendingAfterCommand(pending, 'click');
  pending = recorderNavigationPendingAfterCommand(pending, 'navigate');
  assert.equal(pending, 2);

  pending = recorderNavigationPendingAfterSnapshot(pending, 'error', 1);
  assert.equal(pending, 1);
  pending = recorderNavigationPendingAfterError(pending, 'navigate');
  assert.equal(pending, 1);
  pending = recorderNavigationPendingAfterSnapshot(pending, 'navigating', 1);
  assert.equal(pending, 1);
  pending = recorderNavigationPendingAfterSnapshot(pending, 'frame', 1);
  assert.equal(pending, 0);

  assert.equal(recorderNavigationPendingAfterSnapshot(2, 'error', 0), 2);
});

test('a rejected step edit keeps Recorder close blocked until canonical steps arrive', () => {
  let pending = recorderStepSnapshotPendingAfterCommandError(0, 'replace_steps');
  assert.equal(pending, 1);
  assert.equal(recorderStepSnapshotPendingAfterSnapshot(pending, false), 1);
  pending = recorderStepSnapshotPendingAfterCommandError(pending, 'edit_step');
  assert.equal(pending, 2);
  pending = recorderStepSnapshotPendingAfterSnapshot(pending, true);
  assert.equal(pending, 1);
  pending = recorderStepSnapshotPendingAfterSnapshot(pending, true);
  assert.equal(pending, 0);
  assert.equal(recorderStepSnapshotPendingAfterCommandError(0, 'navigate'), 0);
});

test('close retry is disabled only while its session has blocking work', () => {
  assert.equal(isRecorderCloseRetryBlocked('session-1', 'close', false), true);
  assert.equal(isRecorderCloseRetryBlocked('session-1', 'close', true), false);
  assert.equal(isRecorderCloseRetryBlocked('session-1', null, false), false);
  assert.equal(isRecorderCloseRetryBlocked(null, 'close', false), false);
});

test('Recorder retry intent persists across a close-session error snapshot only when requested', () => {
  assert.equal(recorderErrorRecoveryFor('DELETE failed', 'close'), 'close');
  assert.equal(recorderErrorRecoveryFor('Chrome error page', undefined, 'close', true), 'close');
  assert.equal(recorderErrorRecoveryFor('Chrome error page', undefined, 'close'), null);
  assert.equal(recorderErrorRecoveryFor('', 'close', 'close', true), null);
  assert.equal(recorderErrorRecoveryFor('Navigation failed'), null);
});
