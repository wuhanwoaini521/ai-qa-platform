import test from 'node:test';
import assert from 'node:assert/strict';
import { presentCoverageMetrics } from '../src/features/lifecycle/coveragePresentation.ts';

const metric = (key, items) => ({
  key,
  label: key,
  covered: items.filter((item) => item.covered).length,
  total: items.length,
  percentage: 0,
  items,
});

test('the panel shows the verdicts the server persisted for each metric', () => {
  const coverage = [
    metric('automation', [
      { id: 'active', label: 'Active', covered: true },
      { id: 'validated', label: 'Validated', covered: true },
      { id: 'draft', label: 'Draft', covered: false },
    ]),
    metric('execution', [
      { id: 'active', label: 'Active', covered: true },
      { id: 'validated', label: 'Validated', covered: false },
    ]),
    metric('passed', [
      { id: 'active', label: 'Active', covered: false, run_id: 'run-failed' },
      { id: 'validated', label: 'Validated', covered: true, run_id: 'run-passed' },
    ]),
  ];

  const result = presentCoverageMetrics(coverage, false);
  const automation = result.find((item) => item.key === 'automation');
  const execution = result.find((item) => item.key === 'execution');
  const passed = result.find((item) => item.key === 'passed');

  assert.deepEqual([automation.covered, automation.total, automation.percentage], [2, 3, 66.7]);
  assert.deepEqual([execution.covered, execution.total, execution.percentage], [1, 2, 50]);
  assert.deepEqual([passed.covered, passed.total, passed.items[0].run_id], [1, 2, 'run-failed']);
});

test('incomplete project graphs never claim coverage percentages', () => {
  const result = presentCoverageMetrics(
    [metric('automation', [{ id: 'active', label: 'Active', covered: false }])],
    true,
  );

  assert.equal(result[0].covered, 0);
  assert.equal(result[0].total, 1);
  assert.equal(result[0].percentage, null);
});
