import test from 'node:test';
import assert from 'node:assert/strict';
import { presentCoverageMetrics } from '../src/features/lifecycle/coveragePresentation.ts';

const automationNode = (caseId, status, nodeid = `tests/${caseId}.py::test_case`) => ({
  id: `binding-${caseId}`,
  kind: 'automation',
  label: nodeid,
  summary: '',
  href: '',
  status,
  metadata: { case_id: caseId, nodeid },
});

const metric = (key, items) => ({
  key,
  label: key,
  covered: items.filter((item) => item.covered).length,
  total: items.length,
  percentage: 0,
  items,
});

test('only ACTIVE bindings with nodeids count in automation and run coverage', () => {
  const coverage = [
    metric('automation', [
      { id: 'active', label: 'Active', covered: true },
      { id: 'validated', label: 'Validated', covered: true },
      { id: 'draft', label: 'Draft', covered: false },
    ]),
    metric('execution', [
      { id: 'active', label: 'Active', covered: true },
      { id: 'validated', label: 'Validated', covered: true },
    ]),
    metric('passed', [
      { id: 'active', label: 'Active', covered: false, run_id: 'run-failed' },
      { id: 'validated', label: 'Validated', covered: true, run_id: 'run-passed' },
    ]),
  ];
  const nodes = [
    automationNode('active', 'ACTIVE'),
    automationNode('validated', 'VALIDATED'),
    automationNode('draft', 'ACTIVE', ''),
  ];

  const result = presentCoverageMetrics(coverage, nodes, false);
  const automation = result.find((item) => item.key === 'automation');
  const execution = result.find((item) => item.key === 'execution');
  const passed = result.find((item) => item.key === 'passed');

  assert.deepEqual([automation.covered, automation.total, automation.percentage], [1, 3, 33.3]);
  assert.deepEqual([execution.covered, execution.total, execution.percentage], [1, 1, 100]);
  assert.deepEqual([passed.covered, passed.total, passed.items[0].run_id], [0, 1, 'run-failed']);
});

test('incomplete project graphs never claim coverage percentages', () => {
  const result = presentCoverageMetrics(
    [metric('automation', [{ id: 'active', label: 'Active', covered: false }])],
    [automationNode('active', 'ACTIVE')],
    true,
  );

  assert.equal(result[0].covered, 1);
  assert.equal(result[0].total, 1);
  assert.equal(result[0].percentage, null);
});
