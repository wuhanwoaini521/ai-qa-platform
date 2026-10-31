import test from 'node:test';
import assert from 'node:assert/strict';

const {
  acknowledgeRecorderStepCommand,
  applyPendingRecorderStepCommands,
  pendingRecorderStepCommandsToSend,
  prepareNextPendingRecorderStepCommand,
  isRetryableRecorderStepCommandError,
  reconcilePendingRecorderStepSnapshot,
  restorePendingRecorderStepCommands,
  tryPersistPendingRecorderStepCommands,
  tryRestorePendingRecorderStepCommands,
} = await import('../src/pages/recorderStepSyncModel.ts');

const step = (id, description) => ({ id, action: 'click', description });

test('pending Recorder step edits survive reconnect reconciliation in command order', () => {
  const serverSteps = [step('first', 'Server value'), step('removed', 'Delete me')];
  const pending = [
    { command_id: 'add-1', action: 'add_step', step: step('added', 'New step') },
    { command_id: 'edit-1', action: 'edit_step', step: step('first', 'Local edit') },
    { command_id: 'delete-1', action: 'delete_step', id: 'removed' },
    { command_id: 'reorder-1', action: 'reorder', ids: ['added', 'first'] },
  ];

  assert.deepEqual(applyPendingRecorderStepCommands(serverSteps, pending), [
    step('added', 'New step'),
    step('first', 'Local edit'),
  ]);
  assert.deepEqual(pendingRecorderStepCommandsToSend(pending, new Set()), pending);
  assert.deepEqual(
    pendingRecorderStepCommandsToSend(pending, new Set(['add-1'])),
    pending.slice(1),
  );
});

test('replaying an unacknowledged add step does not duplicate an already applied step', () => {
  const serverSteps = [step('added', 'Server already applied it')];
  const pending = [
    { command_id: 'add-1', action: 'add_step', step: step('added', 'Pending add') },
    { command_id: 'edit-1', action: 'edit_step', step: step('added', 'Later edit') },
  ];

  assert.deepEqual(applyPendingRecorderStepCommands(serverSteps, pending), [step('added', 'Later edit')]);
});

test('error and navigating snapshots reconcile server steps and replay pending edits', () => {
  const pending = [{ command_id: 'edit-1', action: 'edit_step', step: step('first', 'Local edit') }];
  for (const type of ['error', 'navigating']) {
    const result = reconcilePendingRecorderStepSnapshot(
      { type, steps: [step('first', 'Server value')], steps_revision: 3 },
      pending,
      new Set(),
    );
    assert.deepEqual(result.steps, [step('first', 'Local edit')], type);
    assert.deepEqual(result.commandsToSend, pending, type);
  }
});

test('reconnect snapshot acknowledges applied replacements before optimistic replay', () => {
  const pending = [
    { command_id: 'replace-1', action: 'replace_steps', steps: [step('replacement', 'Old replacement')], base_steps_revision: 4 },
  ];
  const serverSteps = [step('replacement', 'Applied replacement'), step('captured', 'Captured later')];

  const result = reconcilePendingRecorderStepSnapshot(
    {
      type: 'error',
      steps: serverSteps,
      steps_revision: 6,
      applied_step_command_ids: ['replace-1'],
    },
    pending,
    new Set(),
  );

  assert.deepEqual(result.pending, []);
  assert.deepEqual(result.steps, serverSteps);
  assert.deepEqual(result.commandsToSend, []);
});

test('replacement queued before the first snapshot receives that snapshot revision', () => {
  const pending = [
    { command_id: 'replace-1', action: 'replace_steps', steps: [step('replacement', 'Generated') ] },
  ];
  const result = reconcilePendingRecorderStepSnapshot(
    { type: 'navigating', steps: [step('existing', 'Captured')], steps_revision: 8 },
    pending,
    new Set(),
  );

  assert.equal(result.pending[0].base_steps_revision, 8);
  assert.deepEqual(result.commandsToSend, result.pending);
});

test('persisted pending step commands restore and replay after a page refresh', () => {
  const stored = JSON.stringify({
    version: 1,
    commands: [
      { command_id: 'edit-1', action: 'edit_step', step: step('first', 'Local edit') },
      { command_id: 'replace-1', action: 'replace_steps', steps: [step('replacement', 'Generated')], base_steps_revision: 4 },
      { command_id: 'invalid', action: 'edit_step', step: { description: 'Missing id' } },
    ],
  });
  const restored = restorePendingRecorderStepCommands(stored);
  const result = reconcilePendingRecorderStepSnapshot(
    { type: 'frame', steps: [step('first', 'Server value')], steps_revision: 5 },
    restored,
    new Set(),
  );

  assert.deepEqual(restored, [
    { command_id: 'edit-1', action: 'edit_step', step: step('first', 'Local edit') },
    { command_id: 'replace-1', action: 'replace_steps', steps: [step('replacement', 'Generated')], base_steps_revision: 4 },
  ]);
  assert.deepEqual(result.steps, [step('replacement', 'Generated')]);
  assert.deepEqual(result.commandsToSend, restored);
});

test('queued replacements serialize and rebase against the latest acknowledged revision', () => {
  const pending = [
    { command_id: 'replace-1', action: 'replace_steps', steps: [step('one', 'first')], base_steps_revision: 4 },
    { command_id: 'replace-2', action: 'replace_steps', steps: [step('two', 'second')], base_steps_revision: 4 },
  ];

  const first = prepareNextPendingRecorderStepCommand(pending, new Set(), 4);
  assert.equal(first.command?.command_id, 'replace-1');
  assert.equal(first.command?.base_steps_revision, 4);
  assert.equal(prepareNextPendingRecorderStepCommand(first.pending, new Set(['replace-1']), 4).command, null);

  const second = prepareNextPendingRecorderStepCommand(
    acknowledgeRecorderStepCommand(first.pending, 'replace-1'),
    new Set(),
    5,
  );
  assert.equal(second.command?.command_id, 'replace-2');
  assert.equal(second.command?.base_steps_revision, 5);
  assert.equal(prepareNextPendingRecorderStepCommand(pending, new Set(), null).command, null);
});

test('a stale replacement conflict stays pending and rebases on the next canonical snapshot', () => {
  const pending = [
    { command_id: 'replace-1', action: 'replace_steps', steps: [step('replacement', 'Generated')], base_steps_revision: 4 },
  ];
  const conflict = { action: 'replace_steps', code: 'steps_revision_conflict' };

  assert.equal(isRetryableRecorderStepCommandError(conflict.action, conflict.code), true);
  assert.equal(isRetryableRecorderStepCommandError('edit_step', conflict.code), false);
  assert.equal(isRetryableRecorderStepCommandError('replace_steps', 'validation_error'), false);

  const canonical = reconcilePendingRecorderStepSnapshot(
    { type: 'frame', steps: [step('existing', 'Canonical')], steps_revision: 5 },
    pending,
    new Set(),
  );
  const retry = prepareNextPendingRecorderStepCommand(canonical.pending, new Set(), 5);

  assert.equal(retry.command?.command_id, 'replace-1');
  assert.equal(retry.command?.base_steps_revision, 5);
  assert.deepEqual(retry.command?.steps, [step('replacement', 'Generated')]);
});

test('Recorder outbox storage failures are explicit and never appear as successful persistence', () => {
  const unavailableStorage = {
    getItem() { throw new Error('storage blocked'); },
    setItem() { throw new Error('quota exceeded'); },
    removeItem() { throw new Error('storage blocked'); },
  };
  const pending = [{ command_id: 'edit-1', action: 'edit_step', step: step('one', 'edit') }];

  assert.deepEqual(tryRestorePendingRecorderStepCommands(unavailableStorage, 'outbox'), {
    commands: [],
    available: false,
  });
  assert.equal(tryPersistPendingRecorderStepCommands(unavailableStorage, 'outbox', pending), false);
  assert.equal(tryPersistPendingRecorderStepCommands(unavailableStorage, 'outbox', []), false);
});

test('acknowledgement removes only the matching pending Recorder command', () => {
  const pending = [
    { command_id: 'first', action: 'delete_step', id: 'a' },
    { command_id: 'second', action: 'delete_step', id: 'b' },
  ];

  assert.deepEqual(acknowledgeRecorderStepCommand(pending, 'second'), [pending[0]]);
  assert.deepEqual(acknowledgeRecorderStepCommand(pending, 'unknown'), pending);
});
