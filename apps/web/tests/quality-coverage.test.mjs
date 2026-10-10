import assert from 'node:assert/strict';
import test from 'node:test';
import { summarizeAutomationCoverage } from '../src/features/quality/coverageModel.ts';

const testCase = (requirementId, status, nodeid) => ({
  requirement_id: requirementId,
  binding: status ? { status, nodeid } : null,
});

test('automation coverage counts only active bindings with a node id', () => {
  const result = summarizeAutomationCoverage([
    testCase('req-1', 'ACTIVE', 'tests/test_cart.py::test_add'),
    testCase('req-1', 'BROKEN', 'tests/test_cart.py::test_remove'),
    testCase('req-2', 'ACTIVE', '  '),
    testCase('req-2', 'VALIDATED', 'tests/test_login.py::test_login'),
    testCase(null, 'ACTIVE', 'tests/test_search.py::test_search'),
  ]);

  assert.deepEqual(
    { total: result.total, automated: result.automated, percentage: result.percentage },
    { total: 5, automated: 2, percentage: 40 },
  );
});

test('requirement coverage uses the same active-binding rule and empty data is zero', () => {
  const result = summarizeAutomationCoverage([
    testCase('req-1', 'ACTIVE', 'tests/test_cart.py::test_add'),
    testCase('req-1', 'DRAFT', 'tests/test_cart.py::test_remove'),
    testCase('req-2', 'BROKEN', 'tests/test_login.py::test_login'),
  ]);

  assert.deepEqual(result.byRequirement.get('req-1'), {
    total: 2,
    automated: 1,
    percentage: 50,
  });
  assert.deepEqual(result.byRequirement.get('req-2'), {
    total: 1,
    automated: 0,
    percentage: 0,
  });
  assert.equal(summarizeAutomationCoverage([]).percentage, 0);
});
