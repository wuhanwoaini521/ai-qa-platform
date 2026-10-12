import test from 'node:test';
import assert from 'node:assert/strict';

const { workspaceRunDockState } = await import('../src/features/workspace/workspaceRunModel.ts');

test('a completed AI task without a TestRun is not presented as a passed test run', () => {
  assert.deepEqual(workspaceRunDockState(null, 'COMPLETED'), {
    status: 'task-completed', active: false, failed: false, passed: false, taskTerminal: true,
  });
});

test('saved TestRun outcome takes precedence over task status', () => {
  assert.deepEqual(workspaceRunDockState('PASSED', 'COMPLETED'), {
    status: 'passed', active: false, failed: false, passed: true, taskTerminal: false,
  });
});

test('task failure and block states remain distinct from TestRun failure', () => {
  assert.equal(workspaceRunDockState(null, 'FAILED').status, 'task-failed');
  assert.equal(workspaceRunDockState(null, 'FAILED').failed, true);
  assert.equal(workspaceRunDockState(null, 'ERROR').status, 'task-failed');
  assert.equal(workspaceRunDockState(null, 'ERROR').taskTerminal, true);
  assert.equal(workspaceRunDockState(null, 'BLOCKED').status, 'task-blocked');
  assert.equal(workspaceRunDockState(null, 'BLOCKED').failed, true);
  assert.equal(workspaceRunDockState('FAILED', null).status, 'failed');
});

test('active task state is represented as workflow activity, not a terminal run result', () => {
  assert.deepEqual(workspaceRunDockState(null, 'PLANNING'), {
    status: 'preparing', active: true, failed: false, passed: false, taskTerminal: false,
  });
  assert.equal(workspaceRunDockState(null, 'RUNNING').status, 'running');
  assert.equal(workspaceRunDockState(null, 'CANCELLED').status, 'task-cancelled');
});

test('no task or run remains ready for a run', () => {
  assert.deepEqual(workspaceRunDockState(null, null), {
    status: 'idle', active: false, failed: false, passed: false, taskTerminal: false,
  });
});

test('workspace run dock uses a case id when the display id is empty', async () => {
  const { workspaceRunCaseLabel } = await import('../src/features/workspace/workspaceRunModel.ts');
  assert.equal(workspaceRunCaseLabel('', 'tc_5cfd067c80a0'), '7C80A0');
  assert.equal(workspaceRunCaseLabel('TC-017', 'tc_5cfd067c80a0'), 'TC-017');
  assert.equal(workspaceRunCaseLabel(undefined, undefined, 'Failure · 12AB'), 'Failure · 12AB');
  assert.equal(workspaceRunCaseLabel('', undefined), '');
});
