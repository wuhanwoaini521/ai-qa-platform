import test from 'node:test';
import assert from 'node:assert/strict';
import {
  availableEvidenceTabs,
  displayedFailureClassification,
  extractRelevantFrames,
  failureErrorPreview,
  failureSourceLocation,
  failureFingerprint,
  normalizeFailureClassification,
  observedRoleLocatorMismatch,
  primaryActionForWorkflow,
  relatedFailures,
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
