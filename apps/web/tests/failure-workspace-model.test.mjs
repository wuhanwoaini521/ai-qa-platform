import test from 'node:test';
import assert from 'node:assert/strict';
import {
  analysisAttemptLabelKey,
  availableEvidenceTabs,
  displayedFailureClassification,
  extractRelevantFrames,
  failureErrorPreview,
  failureCodeFrames,
  failureSourceLocation,
  failureFingerprint,
  normalizeFailureClassification,
  observedRoleLocatorMismatch,
  primaryActionForWorkflow,
  relatedFailures,
  repairTaskChain,
  summarizeFailureError,
  storedRepairProposal,
} from '../src/features/failures/failureWorkspaceModel.ts';

const failure = (overrides = {}) => ({
  id: 'f1',
  run_id: 'r1',
  execution_id: 'e1',
  test_nodeid: 'tests/test_shop.py::test_empty_search',
  test_name: 'test_empty_search',
  classification: 'UNKNOWN',
  exception_type: 'Error',
  error_message: 'BrowserType.launch: spawn EPERM',
  stack_trace: 'at launch (C:\\project\\conftest.py:38:10)',
  console_logs: [],
  created_at: '2026-10-03T00:00:00Z',
  ...overrides,
});

test('Classification aliases are normalized without changing the stored classification', () => {
  assert.equal(normalizeFailureClassification('ENVIRONMENT_ERROR'), 'ENVIRONMENT');
  assert.equal(normalizeFailureClassification('TIMING_ISSUE'), 'TIMING');
  assert.equal(normalizeFailureClassification('UNKNOWN'), 'UNKNOWN');
});

test('Classification display uses the failure record and does not apply diagnosis trust policy in the client', () => {
  assert.equal(displayedFailureClassification('UNKNOWN'), 'UNKNOWN');
  assert.equal(displayedFailureClassification('ENVIRONMENT_ERROR'), 'ENVIRONMENT');
});

test('Primary action is a presentation mapping of backend allowed actions', () => {
  assert.equal(primaryActionForWorkflow('CREATED', ['START_ANALYSIS']), 'RUN_DIAGNOSIS');
  assert.equal(primaryActionForWorkflow('PATCH_READY', ['APPLY']), 'REVIEW_REPAIR');
  assert.equal(primaryActionForWorkflow('PATCH_APPLIED', ['VERIFY', 'ROLLBACK']), 'VERIFY_FIX');
  assert.equal(primaryActionForWorkflow('NOT_APPLICABLE', ['RETRY']), 'RETRY');
  assert.equal(primaryActionForWorkflow('NOT_APPLICABLE', ['CREATE_ISSUE_DRAFT']), 'CREATE_ISSUE_DRAFT');
  assert.equal(primaryActionForWorkflow('NOT_APPLICABLE', []), 'BLOCKED');
  assert.equal(primaryActionForWorkflow('VERIFYING_FIX', []), 'VERIFYING');
  assert.equal(primaryActionForWorkflow('VERIFIED', []), 'VERIFIED');
});

test('Stored repair proposals survive failure selection and invalid patches are ignored', () => {
  const proposal = storedRepairProposal({
    old_locator: 'page.locator("#old")',
    proposed_locator: 'page.get_by_role("button", name="Save")',
    strategy: 'role-and-name',
    applied: true,
    execution_trace: [],
  });
  assert.equal(proposal?.proposed_locator, 'page.get_by_role("button", name="Save")');
  assert.equal(proposal?.applied, true);
  assert.equal(storedRepairProposal({ old_locator: 'text=Save', proposed_locator: 'text=Save', strategy: 'text' }), null);
  assert.equal(storedRepairProposal({ old_locator: 'text=Save', proposed_locator: 'text=Save' }), null);
});

test('Failure preview exposes the final cause line and safely truncates long errors', () => {
  assert.equal(
    failureErrorPreview('Traceback (most recent call last):\n  File "test.py", line 1\nAssertionError: expected checkout to succeed'),
    'AssertionError: expected checkout to succeed',
  );
  assert.equal(failureErrorPreview('x'.repeat(200)), `${'x'.repeat(179)}…`);
  assert.equal(failureErrorPreview('\n  '), '');
});

test('Raw error and stack are summarized into actionable labels and relevant frames', () => {
  assert.equal(summarizeFailureError('BrowserType.launch: spawn EPERM'), 'browserLaunchEperm');
  assert.equal(
    summarizeFailureError('TimeoutError: Locator.click timeout waiting for locator("#purchase-now")', 'LOCATOR_CHANGED'),
    'locatorTimeout',
  );
  assert.equal(summarizeFailureError('TimeoutError: waiting for navigation', 'TIMING_ISSUE'), 'timeout');
  assert.equal(summarizeFailureError('TimeoutError: assertion state did not match', 'ASSERTION_FAILURE'), 'assertion');
  assert.deepEqual(
    extractRelevantFrames('  File "site-packages/playwright/_impl.py", line 4\n  File "C:\\project\\conftest.py", line 38'),
    ['conftest.py:38'],
  );
});

test('Role locator mismatch reports only captured controls with the same role', () => {
  const mismatch = observedRoleLocatorMismatch(failure({
    failing_locator: `page.get_by_role('button', name='Add to cart1')`,
    evidence_bundle: {
      controls: [
        { role: 'button', name: 'Add to cart' },
        { role: 'link', name: 'Add to cart1' },
      ],
    },
  }));
  assert.deepEqual(mismatch, {
    role: 'button',
    expectedName: 'Add to cart1',
    observedNames: ['Add to cart'],
  });
  assert.equal(observedRoleLocatorMismatch(failure({
    failing_locator: `page.get_by_role('button', name='Add to cart')`,
    evidence_bundle: { controls: [{ role: 'button', name: 'Add to cart' }] },
  })), null);
});

test('Failure source location keeps its test file and matches the stack line', () => {
  assert.deepEqual(
    failureSourceLocation(failure({
      test_nodeid: 'tests/test_stable_locator_failure.py::test_purchase_now_locator',
      stack_trace: '  File "D:\\workspace\\tests\\test_stable_locator_failure.py", line 3, in test_purchase_now_locator',
    })),
    { filePath: 'tests/test_stable_locator_failure.py', lineNumber: 3 },
  );
  assert.deepEqual(
    failureSourceLocation(failure({ stack_trace: 'TimeoutError: locator did not resolve' })),
    { filePath: 'tests/test_shop.py', lineNumber: null },
  );
});

test('The recorded failure location wins over the stack trace', () => {
  const recorded = failure({
    stack_trace: '  File "/workspace/tests/test_shop.py", line 7, in test_shop',
    source_file: 'tests/test_shop.py',
    source_line: 12,
  });

  assert.deepEqual(failureSourceLocation(recorded), { filePath: 'tests/test_shop.py', lineNumber: 12 });
  assert.deepEqual(failureCodeFrames(recorded), ['tests/test_shop.py:12', 'test_shop.py:7']);
  assert.deepEqual(failureCodeFrames(failure()), ['conftest.py:38']);
});

test('Evidence tabs only include sections backed by captured evidence', () => {
  assert.deepEqual(availableEvidenceTabs(failure()), ['SUMMARY', 'STACK']);
  assert.deepEqual(
    availableEvidenceTabs(failure({ screenshot_path: 'artifacts/page.png', trace_path: 'artifacts/trace.zip', console_logs: ['console error'] })),
    ['SUMMARY', 'STACK', 'BROWSER', 'CONSOLE', 'ARTIFACTS'],
  );
  assert.deepEqual(
    availableEvidenceTabs(failure(), {
      url: 'http://127.0.0.1/',
      controls: [{ role: 'button', name: 'Complete order' }],
      network_logs: [{ method: 'GET', status: 200 }],
    }),
    ['SUMMARY', 'STACK', 'BROWSER', 'NETWORK'],
  );
  assert.deepEqual(
    availableEvidenceTabs(failure({ evidence_bundle: { element_evidence: { version: 'v1.0', steps: [{ step_id: 's1' }] } } })),
    ['SUMMARY', 'STACK', 'BROWSER'],
  );
});

test('Read-only grouping only joins failures with a specific shared launch signature', () => {
  const first = failure();
  const second = failure({ id: 'f2', test_nodeid: 'tests/test_shop.py::test_search' });
  const unrelated = failure({ id: 'f3', error_message: 'AssertionError: expected 2 but got 3', stack_trace: '' });
  assert.equal(failureFingerprint(first), 'browser-launch:spawn-eperm');
  assert.deepEqual(relatedFailures([first, second, unrelated], first).map((item) => item.id), ['f1', 'f2']);
  assert.deepEqual(relatedFailures([unrelated], unrelated), []);
});

const repairTask = (overrides = {}) => ({
  id: 'task-1',
  type: 'FIX_FAILURE',
  goal: 'repair',
  status: 'WAITING',
  owner_id: 'admin',
  inputs: { failure_id: 'f1' },
  context: {},
  verification: {},
  retry_count: 0,
  replan_count: 0,
  max_steps: 12,
  created_at: '2026-10-19T00:00:00Z',
  updated_at: '2026-10-19T00:00:00Z',
  plan: [
    { id: '1', key: 'diagnose', name: 'Diagnose', tool: 'ai.diagnose', status: 'COMPLETED', outputs: {} },
    { id: '2', key: 'approval', name: 'Approve', tool: 'task.request_approval', status: 'WAITING_FOR_APPROVAL', outputs: {} },
    { id: '3', key: 'apply', name: 'Apply', tool: 'source.apply_repair', status: 'PENDING', outputs: {} },
    { id: '4', key: 'target_run', name: 'Target run', tool: 'tests.run_target', status: 'PENDING', outputs: {} },
    { id: '5', key: 'verify', name: 'Verify', tool: 'tests.verify', status: 'PENDING', outputs: {} },
  ],
  ...overrides,
});

test('A repair task chain reports the approval gate and the verified run it produced', () => {
  assert.deepEqual(repairTaskChain(null), null);
  const pending = repairTaskChain(repairTask());
  assert.equal(pending.approvalPending, true);
  assert.equal(pending.applied, false);
  assert.equal(pending.verified, false);
  assert.equal(pending.targetRunId, null);

  const verifiedTask = repairTask({ status: 'COMPLETED' });
  verifiedTask.plan = verifiedTask.plan.map((step) => {
    if (step.key === 'approval') return { ...step, status: 'COMPLETED', outputs: { approved: true } };
    if (step.key === 'apply') return { ...step, status: 'COMPLETED', outputs: { written: true } };
    if (step.key === 'target_run') return { ...step, status: 'COMPLETED', outputs: { run_id: 'run_abc', status: 'PASSED' } };
    if (step.key === 'verify') return { ...step, status: 'COMPLETED', outputs: { verified: true, run_id: 'run_abc', status: 'PASSED' } };
    return step;
  });
  const verified = repairTaskChain(verifiedTask);
  assert.equal(verified.approvalPending, false);
  assert.equal(verified.applied, true);
  assert.equal(verified.targetRunId, 'run_abc');
  assert.equal(verified.targetRunStatus, 'PASSED');
  assert.equal(verified.verified, true);
  assert.equal(verified.verificationRunId, 'run_abc');
});

test('A stopped repair task is reported as stopped, not as a missing repair', () => {
  assert.equal(repairTaskChain(repairTask({ status: 'CANCELLED' })).cancelled, true);
  assert.equal(repairTaskChain(repairTask({ status: 'BLOCKED' })).blocked, true);
  assert.equal(repairTaskChain(repairTask({ status: 'FAILED' })).failed, true);
  const rejected = repairTask();
  rejected.plan = rejected.plan.map((step) =>
    step.key === 'approval' ? { ...step, status: 'SKIPPED', outputs: { approved: false } } : step,
  );
  assert.equal(repairTaskChain(rejected).approvalRejected, true);
});

test('A cancelled attempt is labelled by its own state instead of the blocked workflow', () => {
  assert.equal(analysisAttemptLabelKey('CANCELLED'), 'attemptStates.CANCELLED');
  assert.equal(analysisAttemptLabelKey('timeout'), 'attemptStates.TIMEOUT');
  assert.equal(analysisAttemptLabelKey('INTERRUPTED'), 'attemptStates.INTERRUPTED');
  assert.equal(analysisAttemptLabelKey('COMPLETED'), null);
  assert.equal(analysisAttemptLabelKey(null), null);
});
