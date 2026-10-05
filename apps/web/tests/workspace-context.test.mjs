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
  const params = writeWorkspaceContext('?tab=coverage&caseId=old&line=2', {
    projectId: 'project-a',
    requirementId: 'req-a',
    testCaseId: 'case-a',
    stage: 'cases',
  });
  assert.equal(params.get('tab'), 'coverage');
  assert.equal(params.get('requirementId'), 'req-a');
  assert.equal(params.get('caseId'), 'case-a');
  assert.equal(params.get('line'), null);
});

test('builds deep links for Workspace, Workflow and Studio with one context', () => {
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
  assert.match(buildWorkflowHref(context), /^\/workflow\?/);
  assert.match(buildStudioHref(context), /^\/projects\/project-a\/studio\/file\/tests%2Ftest_login.py\?/);
  for (const href of [buildWorkspaceHref(context), buildWorkflowHref(context), buildStudioHref(context)]) {
    const query = new URLSearchParams(href.slice(href.indexOf('?') + 1));
    assert.equal(query.get('requirementId'), 'req-a');
    assert.equal(query.get('caseId'), 'case-a');
    assert.equal(query.get('failureId'), 'failure-a');
    assert.equal(query.get('line'), '28');
  }
});
