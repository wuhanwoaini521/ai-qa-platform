import test from 'node:test';
import assert from 'node:assert/strict';

const { bindingForSelectedCase, configForRerun, defaultWorkspaceGoal, repairNoticeForRun, terminalRunStatus, workspaceGoalTarget } = await import('../src/features/workspace/workspaceRunModel.ts');

test('terminal run status includes all completed outcomes and excludes active runs', () => {
  for (const status of ['PASSED', 'FAILED', 'ERROR', 'CANCELLED']) {
    assert.equal(terminalRunStatus(status), status);
  }
  assert.equal(terminalRunStatus('QUEUED'), null);
  assert.equal(terminalRunStatus('RUNNING'), null);
});

test('repair is not needed after a pass and only blocked for failed runs missing failure data', () => {
  assert.equal(repairNoticeForRun('PASSED', false, false), 'NOT_NEEDED');
  assert.equal(repairNoticeForRun('FAILED', false, false), 'BLOCKED');
  assert.equal(repairNoticeForRun('ERROR', false, false), 'BLOCKED');
  assert.equal(repairNoticeForRun('FAILED', true, false), null);
  assert.equal(repairNoticeForRun('FAILED', false, true), null);
  assert.equal(repairNoticeForRun('RUNNING', false, false), null);
  assert.equal(repairNoticeForRun('QUEUED', false, false), null);
  assert.equal(repairNoticeForRun('CANCELLED', false, false), null);
});

test('a binding is unavailable until its case id matches the current selection', () => {
  const prior = { caseId: 'case-a', binding: { nodeid: 'tests/test_a.py::test_a' } };
  assert.equal(bindingForSelectedCase(prior, 'case-b'), null);
  assert.deepEqual(bindingForSelectedCase(prior, 'case-a'), prior.binding);
  assert.equal(bindingForSelectedCase(prior, undefined), null);
});

test('rerun config preserves the historical environment, browser, and worker count', () => {
  const fallback = { environment: 'staging', region: 'JP', browser: 'chromium', workers: 1 };
  const run = {
    environment: { QA_ENVIRONMENT: 'production', QA_REGION: 'EU' },
    browser: 'firefox',
    parallel_workers: 4,
  };
  assert.deepEqual(configForRerun(run, fallback), {
    environment: 'production', region: 'EU', browser: 'firefox', workers: 4,
  });
});

test('rerun config falls back only for fields absent from older run records', () => {
  const fallback = { environment: 'staging', region: 'JP', browser: 'chromium', workers: 2 };
  const run = { environment: {}, browser: '', parallel_workers: undefined };
  assert.deepEqual(configForRerun(run, fallback), fallback);
});

test('a requirement goal keeps requirement scope when a related case is selected', () => {
  assert.equal(workspaceGoalTarget('帮我把这个需求测试完整', {
    requirementId: 'req-1', testCaseId: 'case-1',
  }), 'requirement');
});

test('a current-case goal uses case scope and a failure keeps failure scope', () => {
  assert.equal(workspaceGoalTarget('运行当前用例并分析结果', {
    requirementId: 'req-1', testCaseId: 'case-1',
  }), 'case');
  assert.equal(workspaceGoalTarget('分析并修复这个失败', {
    failureId: 'failure-1', requirementId: 'req-1', testCaseId: 'case-1',
  }), 'failure');
  assert.equal(workspaceGoalTarget('检查这个项目目前还有什么明显测试问题', {
    requirementId: 'req-1', testCaseId: 'case-1',
  }), 'project');
});

test('workspace AI action defaults to the selected scope and generates unbound automation', () => {
  assert.match(defaultWorkspaceGoal({ requirementId: 'req-1', stage: 'requirement', hasAutomation: false }), /需求测试完整/);
  assert.match(defaultWorkspaceGoal({ testCaseId: 'case-1', stage: 'cases', hasAutomation: false }), /生成自动化并运行/);
  assert.match(defaultWorkspaceGoal({ testCaseId: 'case-1', stage: 'cases', hasAutomation: true }), /运行当前用例/);
});
