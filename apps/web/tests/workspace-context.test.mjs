import test from 'node:test';
import assert from 'node:assert/strict';

const { buildStudioHref, buildWorkflowHref, buildWorkspaceHref, readWorkspaceContext, writeWorkspaceContext } =
  await import('../src/app/workspaceContext.ts');

test('reads legacy case and parent run params into the shared context', () => {
  const context = readWorkspaceContext(
    '?caseId=case-1&parentRunId=run-2&line=17&stage=failure',
    'project-3',
  );
  assert.deepEqual(
    {
      projectId: context.projectId,
      testCaseId: context.testCaseId,
      runId: context.runId,
      parentRunId: context.parentRunId,
      lineNumber: context.lineNumber,
      stage: context.stage,
    },
    {
      projectId: 'project-3',
      testCaseId: 'case-1',
      runId: 'run-2',
      parentRunId: 'run-2',
      lineNumber: 17,
      stage: 'failure',
    },
  );
});

test('context updates preserve unrelated view state and replace stale entity IDs', () => {
  const search = '?tab=coverage&caseId=old&line=2&stage=automation&view=code';
  const current = readWorkspaceContext(search, 'project-a');
  const params = writeWorkspaceContext(search, {
    ...current,
    projectId: 'project-a',
    requirementId: 'req-b',
    testCaseId: 'case-b',
    file: 'tests/test_case_b.py',
    lineNumber: undefined,
  });
  assert.equal(params.get('tab'), 'coverage');
  assert.equal(params.get('requirementId'), 'req-b');
  assert.equal(params.get('caseId'), 'case-b');
  assert.equal(params.get('stage'), 'automation');
  assert.equal(params.get('view'), 'code');
  assert.equal(params.get('file'), 'tests/test_case_b.py');
  assert.equal(params.get('line'), null);
});

test('round trips the Workspace Discover stage and view', () => {
  const context = readWorkspaceContext('?stage=discover&view=discover&requirementId=req-1', 'project-1');
  assert.equal(context.stage, 'discover');
  assert.equal(context.view, 'discover');
  const params = writeWorkspaceContext('', context);
  assert.equal(params.get('stage'), 'discover');
  assert.equal(params.get('view'), 'discover');
  assert.equal(params.get('requirementId'), 'req-1');
});

test('keeps Studio deep links inside Workspace with the same context', () => {
  const context = {
    projectId: 'project-a',
    requirementId: 'req-a',
    testCaseId: 'case-a',
    taskId: 'task-a',
    runId: 'run-a',
    failureId: 'failure-a',
    file: 'tests/test_login.py',
    lineNumber: 28,
    nodeId: 'tests/test_login.py::test_login',
    returnTo: 'workspace',
  };
  assert.match(buildWorkspaceHref(context), /^\/workspace\/project-a\?/);
  assert.match(buildWorkflowHref(context), /^\/workspace\/project-a\?/);
  assert.equal(new URLSearchParams(buildWorkflowHref(context).split('?')[1]).get('panel'), 'runtime');
  assert.match(buildStudioHref(context), /^\/workspace\/project-a\?/);
  for (const href of [buildWorkspaceHref(context), buildWorkflowHref(context), buildStudioHref(context)]) {
    const query = new URLSearchParams(href.slice(href.indexOf('?') + 1));
    assert.equal(query.get('requirementId'), 'req-a');
    assert.equal(query.get('caseId'), 'case-a');
    assert.equal(query.get('failureId'), 'failure-a');
    assert.equal(query.get('line'), '28');
  }
  const studioContext = new URLSearchParams(buildStudioHref(context).split('?')[1]);
  assert.equal(studioContext.get('view'), 'debug');
  assert.equal(studioContext.get('file'), 'tests/test_login.py');
});

test('opens run progress in the Workspace drawer instead of navigating to a second runtime page', () => {
  const href = buildWorkflowHref({ projectId: 'project-a', taskId: 'task-a' });
  assert.match(href, /^\/workspace\/project-a\?/);
  const params = new URLSearchParams(href.split('?')[1]);
  assert.equal(params.get('taskId'), 'task-a');
  assert.equal(params.get('view'), 'results');
  assert.equal(params.get('panel'), 'runtime');
  assert.equal(buildWorkflowHref({ projectId: 'project-a' }), '/runs/tasks?projectId=project-a');
});
