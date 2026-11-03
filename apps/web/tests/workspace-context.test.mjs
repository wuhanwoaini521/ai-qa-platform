import test from 'node:test';
import assert from 'node:assert/strict';

const {
  buildStudioHref,
  buildWorkflowHref,
  buildWorkspaceHref,
  buildWorkspaceHomeHref,
  buildScopedHref,
  readExplicitRunId,
  readWorkspaceContext,
  resolveCanonicalFile,
  resolveLineNumberForFile,
  shouldPreserveRunExecutionNode,
  workspaceModeForContext,
  writeWorkspaceContext,
} = await import('../src/app/workspaceContext.ts');
const { clearProjectBoundContext, withProjectId } = await import('../src/app/projectPaths.ts');

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

  const aliasContext = readWorkspaceContext('?testCaseId=legacy-case-alias', 'project-3');
  assert.equal(aliasContext.testCaseId, 'legacy-case-alias');
});

test('run island eligibility requires a non-empty explicit runId parameter', () => {
  assert.equal(readExplicitRunId('?parentRunId=parent-run'), undefined);
  assert.equal(readExplicitRunId('?runId=%20'), undefined);
  assert.equal(readExplicitRunId('?runId=selected-run&parentRunId=parent-run'), 'selected-run');
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

test('retains source line context only when opening the same file', () => {
  assert.equal(resolveLineNumberForFile('tests/test_a.py', 'tests/test_a.py', undefined, 12), 12);
  assert.equal(resolveLineNumberForFile('tests/test_b.py', 'tests/test_a.py', undefined, 12), undefined);
  assert.equal(resolveLineNumberForFile('tests/test_b.py', 'tests/test_a.py', 24, 12), 24);
  assert.equal(resolveLineNumberForFile(undefined, undefined, undefined, 12), undefined);
});

test('maps existing Workspace views to the four adaptive modes', () => {
  for (const view of ['requirement', 'discover', 'browser']) {
    assert.equal(workspaceModeForContext({ view }), 'explore');
  }
  for (const view of ['cases', 'code']) {
    assert.equal(workspaceModeForContext({ view }), 'write');
  }
  for (const view of ['debug', 'results']) {
    assert.equal(workspaceModeForContext({ view }), 'debug');
  }
  assert.equal(workspaceModeForContext({ stage: 'failure', view: 'results' }), 'repair');
});

test('preserves a selected run node in Results, Debug, and Write Tests only when that run contains it', () => {
  const nodeId = 'tests/test_login.py::test_login';
  const runNodeIds = [nodeId, 'tests/test_cart.py::test_cart'];

  assert.equal(shouldPreserveRunExecutionNode('results', nodeId, runNodeIds), true);
  assert.equal(shouldPreserveRunExecutionNode('debug', nodeId, runNodeIds), true);
  assert.equal(shouldPreserveRunExecutionNode('code', nodeId, runNodeIds), true);
  assert.equal(shouldPreserveRunExecutionNode('cases', nodeId, runNodeIds), false);
  assert.equal(shouldPreserveRunExecutionNode('debug', 'tests/test_other.py::test_other', runNodeIds), false);
  assert.equal(shouldPreserveRunExecutionNode('debug', undefined, runNodeIds), false);
  assert.equal(shouldPreserveRunExecutionNode('debug', nodeId, []), false);
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

test('switches Workspace project scope without retaining the previous workspace context', () => {
  assert.equal(withProjectId('/workspace/project-old', 'project-new'), '/workspace/project-new');
  assert.equal(withProjectId('/workspace', 'project-new'), '/workspace/project-new');
  assert.equal(withProjectId('/workspace/project-old', ''), '/projects');
  assert.equal(withProjectId('/workspace', ''), '/projects');
  assert.equal(withProjectId('/projects/project-old/requirements', 'project-new'), '/projects/project-new/requirements');
  assert.equal(withProjectId('/projects/project-old/requirements/req-old', 'project-new'), '/projects/project-new/requirements');
  assert.equal(withProjectId('/projects/project-old/test-cases/case-old', 'project-new'), '/projects/project-new/test-cases');
  assert.equal(withProjectId('/projects/project-old/studio/file/tests/test_old.py', 'project-new'), '/projects/project-new/studio');
  assert.equal(withProjectId('/projects/project-old', ''), '/projects');
  assert.equal(withProjectId('/runs', 'project-new'), '/runs');
});

test('clears project-bound query state while retaining the selected workspace view', () => {
  const params = clearProjectBoundContext(
    '?projectId=project-new&requirementId=req-old&testDesignId=design-old&caseId=case-old&testCaseId=legacy-case-old&bindingId=binding-old&taskId=task-old&runId=run-old&parentRunId=parent-old&failureId=failure-old&browserSessionId=browser-old&file=tests/test_old.py&line=17&nodeid=tests/test_old.py%3A%3Atest_old&nodeId=old-node&node=old-graph-node&step=step-old&target=old-target&panel=runtime&stage=automation&view=code&tab=files',
  );
  assert.equal(params.get('projectId'), 'project-new');
  assert.equal(params.get('stage'), 'automation');
  assert.equal(params.get('view'), 'code');
  assert.equal(params.get('tab'), 'files');
  for (const key of [
    'requirementId', 'testDesignId', 'caseId', 'testCaseId', 'bindingId', 'taskId', 'runId', 'parentRunId',
    'failureId', 'browserSessionId', 'file', 'line', 'nodeid', 'nodeId', 'node', 'step', 'target', 'panel',
  ]) {
    assert.equal(params.has(key), false, `${key} should be cleared`);
  }
});

test('sidebar Workspace home drops run context while keeping the selected project', () => {
  const context = readWorkspaceContext('?projectId=project-a&runId=run-442548e01e2d&taskId=task-a&parentRunId=parent-a', 'project-b');
  assert.equal(buildWorkspaceHomeHref(context.projectId), '/workspace/project-a');
  assert.equal(buildWorkspaceHomeHref(null), '/workspace');
});


test('opens run progress in the Workspace drawer instead of navigating to a second runtime page', () => {
  const href = buildWorkflowHref({ projectId: 'project-a', taskId: 'task-a' });
  assert.match(href, /^\/workspace\/project-a\?/);
  const params = new URLSearchParams(href.split('?')[1]);
  assert.equal(params.get('taskId'), 'task-a');
  assert.equal(params.get('view'), 'results');
  assert.equal(params.get('panel'), 'runtime');
  assert.equal(buildWorkflowHref({ projectId: 'project-a' }), '/runs/tasks?projectId=project-a');

  const parentHref = buildWorkflowHref({ projectId: 'project-a', parentRunId: 'parent-a' });
  const parentParams = new URLSearchParams(parentHref.split('?')[1]);
  assert.equal(parentParams.get('runId'), null);
  assert.equal(parentParams.get('parentRunId'), 'parent-a');
  assert.equal(parentParams.get('panel'), 'runtime');
});

test('keeps the file named by a deep link instead of the first bound case file', () => {
  // /projects/<id>/studio/file/tests/test_known_locator.py must not open tests/test_shop.py.
  const linked = readWorkspaceContext('?view=code&file=tests/test_known_locator.py', 'project-a');
  assert.equal(resolveCanonicalFile(linked, 'tests/test_shop.py'), 'tests/test_known_locator.py');
});

test('falls back to the bound case file when the link names no file', () => {
  const linked = readWorkspaceContext('?view=code&caseId=case-a', 'project-a');
  assert.equal(resolveCanonicalFile(linked, 'tests/test_shop.py'), 'tests/test_shop.py');
  assert.equal(resolveCanonicalFile(linked, undefined), undefined);
});

test('failure debug links keep their own file even when a case binding exists', () => {
  const linked = readWorkspaceContext('?view=debug&failureId=failure-a&file=tests/test_known_locator.py', 'project-a');
  assert.equal(resolveCanonicalFile(linked, 'tests/test_shop.py'), 'tests/test_known_locator.py');
});

test('top-level links keep the project and explicitly selected run they were opened from', () => {
  assert.equal(buildScopedHref('/runs', { projectId: 'project-a' }), '/runs?projectId=project-a');
  assert.equal(buildScopedHref('/runs', { projectId: 'project-a', runId: 'run-a' }), '/runs?projectId=project-a&runId=run-a');
  assert.equal(buildScopedHref('/runs', { projectId: 'project-a', parentRunId: 'parent-a' }), '/runs?projectId=project-a&parentRunId=parent-a');
  assert.equal(buildScopedHref('/quality', {}), '/quality');
  // A link from the workspace carries both, so /runs opens the same run it came from.
  assert.equal(
    readWorkspaceContext('?projectId=project-a&runId=run-a', 'project-b').projectId,
    'project-a',
  );
  assert.equal(readWorkspaceContext('?projectId=project-a&runId=run-a').runId, 'run-a');
});
