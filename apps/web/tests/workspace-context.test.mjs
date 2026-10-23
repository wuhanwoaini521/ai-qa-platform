import test from 'node:test';
import assert from 'node:assert/strict';

const { buildStudioHref, buildWorkflowHref, buildWorkspaceHref, buildScopedHref, readWorkspaceContext, resolveCanonicalFile, writeWorkspaceContext } =
  await import('../src/app/workspaceContext.ts');
const { withProjectId } = await import('../src/app/projectPaths.ts');

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

test('round trips recorder source context and replaces stale source IDs', () => {
  const source = readWorkspaceContext('?stage=automation&view=browser&requirementId=req-1&caseId=case-1', 'project-1');
  const params = writeWorkspaceContext('', {
    ...source,
    recorderFromRequirementId: source.requirementId,
    recorderFromCaseId: source.testCaseId,
  });
  const reopened = readWorkspaceContext(params, 'project-1');
  assert.equal(reopened.recorderFromRequirementId, 'req-1');
  assert.equal(reopened.recorderFromCaseId, 'case-1');

  const changedSource = writeWorkspaceContext(params, {
    ...reopened,
    recorderFromRequirementId: 'req-2',
    recorderFromCaseId: undefined,
  });
  const next = readWorkspaceContext(changedSource, 'project-1');
  assert.equal(next.recorderFromRequirementId, 'req-2');
  assert.equal(next.recorderFromCaseId, undefined);

  const leftRecorder = writeWorkspaceContext(changedSource, {
    ...next,
    view: 'cases',
    recorderFromRequirementId: undefined,
    recorderFromCaseId: undefined,
  });
  const workspace = readWorkspaceContext(leftRecorder, 'project-1');
  assert.equal(workspace.view, 'cases');
  assert.equal(workspace.recorderFromRequirementId, undefined);
  assert.equal(workspace.recorderFromCaseId, undefined);
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
  assert.equal(withProjectId('/projects/project-old', ''), '/projects');
  assert.equal(withProjectId('/runs', 'project-new'), '/runs');
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

test('top-level links keep the project they were opened from', () => {
  assert.equal(buildScopedHref('/runs', { projectId: 'project-a' }), '/runs?projectId=project-a');
  assert.equal(buildScopedHref('/quality', {}), '/quality');
  // A link from the workspace carries both, so /runs opens the same run it came from.
  assert.equal(
    readWorkspaceContext('?projectId=project-a&runId=run-a', 'project-b').projectId,
    'project-a',
  );
  assert.equal(readWorkspaceContext('?projectId=project-a&runId=run-a').runId, 'run-a');
});
