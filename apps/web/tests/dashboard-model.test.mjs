import test from 'node:test';
import assert from 'node:assert/strict';

const { dashboardExecutionHref, isExecutableTestCase, isUnfinishedTask } = await import('../src/pages/dashboardModel.ts');

test('Dashboard execution links preserve run project and exact node, with selected-project fallback', () => {
  const nodeId = 'tests/test_login.py::test_login';
  const runProjectHref = dashboardExecutionHref(
    { id: 'run-1', project_id: 'project-run' },
    { nodeid: nodeId },
    'project-selected',
  );
  assert.ok(runProjectHref);
  const runProjectParams = new URLSearchParams(runProjectHref.slice(runProjectHref.indexOf('?') + 1));
  assert.equal(runProjectHref.split('?')[0], '/workspace/project-run');
  assert.equal(runProjectParams.get('projectId'), 'project-run');
  assert.equal(runProjectParams.get('runId'), 'run-1');
  assert.equal(runProjectParams.get('nodeid'), nodeId);
  assert.equal(runProjectParams.get('file'), 'tests/test_login.py');
  assert.equal(runProjectParams.get('stage'), 'result');
  assert.equal(runProjectParams.get('view'), 'results');

  const fallbackHref = dashboardExecutionHref({ id: 'run-2', project_id: null }, { nodeid: nodeId }, 'project-selected');
  assert.ok(fallbackHref);
  assert.equal(fallbackHref.split('?')[0], '/workspace/project-selected');
  const fallbackParams = new URLSearchParams(fallbackHref.slice(fallbackHref.indexOf('?') + 1));
  assert.equal(fallbackParams.get('nodeid'), nodeId);
  assert.equal(fallbackParams.get('file'), 'tests/test_login.py');
  assert.equal(dashboardExecutionHref({ id: 'run-3', project_id: null }, { nodeid: nodeId }, null), null);
});

test('only active bindings with a node id expose the runnable-test entry', () => {
  assert.equal(isExecutableTestCase({ binding: { status: 'ACTIVE', nodeid: 'tests/test_login.py::test_login' } }), true);
  assert.equal(isExecutableTestCase({ binding: { status: 'STALE', nodeid: 'tests/test_login.py::test_login' } }), false);
  assert.equal(isExecutableTestCase({ binding: { status: 'ACTIVE', nodeid: '' } }), false);
  assert.equal(isExecutableTestCase({ binding: null }), false);
});

test('only non-terminal tasks are offered as work to resume', () => {
  assert.equal(isUnfinishedTask({ status: 'RUNNING' }), true);
  assert.equal(isUnfinishedTask({ status: 'WAITING' }), true);
  for (const status of ['COMPLETED', 'FAILED', 'BLOCKED', 'CANCELLED']) {
    assert.equal(isUnfinishedTask({ status }), false);
  }
});
