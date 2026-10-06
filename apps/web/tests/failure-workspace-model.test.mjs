import test from 'node:test';
import assert from 'node:assert/strict';
import {
  availableEvidenceTabs,
  displayedFailureClassification,
  deriveDiagnosisState,
  extractRelevantFrames,
  failureFingerprint,
  normalizeFailureClassification,
  primaryActionFor,
  relatedFailures,
  repairEligibility,
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

const diagnosis = (classification = 'LOCATOR_CHANGED', overrides = {}) => ({
  classification,
  root_cause: 'The recorded locator no longer matches the page.',
  evidence: ['The failed locator was recorded.'],
  hypotheses: [],
  recommended_actions: [],
  confidence: 0.9,
  provider: 'provider-a',
  fallback_used: false,
  ...overrides,
});

test('Classification aliases are normalized without changing the stored classification', () => {
  assert.equal(normalizeFailureClassification('ENVIRONMENT_ERROR'), 'ENVIRONMENT');
  assert.equal(normalizeFailureClassification('TIMING_ISSUE'), 'TIMING');
  assert.equal(normalizeFailureClassification('UNKNOWN'), 'UNKNOWN');
});

test('Header classification follows a trusted diagnosis and ignores simulated fallback labels', () => {
  assert.equal(displayedFailureClassification('UNKNOWN', diagnosis('PRODUCT_DEFECT')), 'PRODUCT_DEFECT');
  assert.equal(displayedFailureClassification('UNKNOWN', diagnosis('ENVIRONMENT', { provider: 'fake' })), 'UNKNOWN');
  assert.equal(displayedFailureClassification('UNKNOWN', diagnosis('ENVIRONMENT', { fallback_used: true })), 'UNKNOWN');
});

test('Failure state follows actual diagnosis, proposal, application, and verification records', () => {
  assert.equal(deriveDiagnosisState({ diagnosing: false, diagnosis: null, repairProposed: false, repairApplied: false }), 'NOT_ANALYZED');
  assert.equal(deriveDiagnosisState({ diagnosing: true, diagnosis: null, repairProposed: false, repairApplied: false }), 'ANALYZING');
  assert.equal(deriveDiagnosisState({ diagnosing: false, diagnosis: diagnosis(), repairProposed: false, repairApplied: false }), 'DIAGNOSED');
  assert.equal(deriveDiagnosisState({ diagnosing: false, diagnosis: diagnosis(), repairProposed: true, repairApplied: false }), 'REPAIR_PROPOSED');
  assert.equal(deriveDiagnosisState({ diagnosing: false, diagnosis: diagnosis(), repairProposed: true, repairApplied: true }), 'REPAIR_APPLIED');
  assert.equal(deriveDiagnosisState({ diagnosing: false, diagnosis: diagnosis(), repairProposed: false, repairApplied: false, verificationStatus: 'RUNNING' }), 'VERIFYING');
  assert.equal(deriveDiagnosisState({ diagnosing: false, diagnosis: diagnosis(), repairProposed: false, repairApplied: false, verificationStatus: 'PASSED' }), 'VERIFIED');
});

test('Primary action is classification and workflow aware', () => {
  assert.equal(primaryActionFor({ state: 'NOT_ANALYZED', classification: 'UNKNOWN', hasFailedLocator: false }), 'RUN_DIAGNOSIS');
  assert.equal(primaryActionFor({ state: 'DIAGNOSED', classification: 'UNKNOWN', diagnosedClassification: 'LOCATOR_CHANGED', hasFailedLocator: true }), 'GENERATE_LOCATOR_REPAIR');
  assert.equal(primaryActionFor({ state: 'DIAGNOSED', classification: 'AUTOMATION_DEFECT', hasFailedLocator: false }), 'BLOCKED');
  assert.equal(primaryActionFor({ state: 'DIAGNOSED', classification: 'ENVIRONMENT', hasFailedLocator: false }), 'RETRY');
  assert.equal(primaryActionFor({ state: 'DIAGNOSED', classification: 'PRODUCT_DEFECT', hasFailedLocator: false }), 'CREATE_ISSUE_DRAFT');
  assert.equal(primaryActionFor({ state: 'REPAIR_APPLIED', classification: 'LOCATOR_CHANGED', hasFailedLocator: true }), 'VERIFY_FIX');
});

test('Locator repair requires a confirmed non-fallback locator diagnosis and evidence', () => {
  const record = failure({ classification: 'LOCATOR_CHANGED', failing_locator: 'text=Save' });
  assert.equal(repairEligibility({ failure: record, diagnosis: null }).reason, 'not-diagnosed');
  assert.equal(repairEligibility({ failure: record, diagnosis: diagnosis('LOCATOR_CHANGED', { provider: 'fake' }) }).eligible, false);
  assert.equal(repairEligibility({ failure: record, diagnosis: diagnosis('LOCATOR_CHANGED') }).eligible, true);
  assert.equal(repairEligibility({ failure: failure({ classification: 'UNKNOWN', failing_locator: 'text=Save' }), diagnosis: diagnosis('UNKNOWN') }).eligible, false);
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

test('Raw error and stack are summarized into actionable labels and relevant frames', () => {
  assert.equal(summarizeFailureError('BrowserType.launch: spawn EPERM'), 'browserLaunchEperm');
  assert.deepEqual(
    extractRelevantFrames('  File "site-packages/playwright/_impl.py", line 4\n  File "C:\\project\\conftest.py", line 38'),
    ['conftest.py:38'],
  );
});

test('Evidence tabs only include sections backed by captured evidence', () => {
  assert.deepEqual(availableEvidenceTabs(failure()), ['SUMMARY', 'STACK']);
  assert.deepEqual(
    availableEvidenceTabs(failure({ screenshot_path: 'artifacts/page.png', trace_path: 'artifacts/trace.zip', console_logs: ['console error'] })),
    ['SUMMARY', 'STACK', 'BROWSER', 'CONSOLE', 'ARTIFACTS'],
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
