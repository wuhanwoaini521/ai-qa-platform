import test from 'node:test';
import assert from 'node:assert/strict';

const { buildTestExecutionRows, resolveExecutionCase } = await import(
  '../src/features/runs/testExecutionResultsModel.ts'
);

const testCase = (id, displayId, title, nodeid) => ({
  id,
  project_id: 'project-1',
  title,
  test_model: displayId ? { display_id: displayId } : undefined,
  external_case_id: undefined,
  binding: nodeid ? { nodeid } : null,
});

const execution = (id, nodeid, status = 'FAILED', runId = 'run-1') => ({
  id,
  run_id: runId,
  nodeid,
  status,
  duration_ms: 100,
  error_message: null,
  stack_trace: null,
});

const failure = (id, executionId, runId = 'run-1') => ({
  id,
  execution_id: executionId,
  test_run_id: runId,
  title: `Failure ${id}`,
  message: `Message ${id}`,
});

test('maps a uniquely bound execution to the case display ID and title', () => {
  const identity = resolveExecutionCase(
    'tests/test_shop.py::test_search',
    [testCase('case-1', 'TC-001', 'Search products', 'tests/test_shop.py::test_search')],
  );

  assert.deepEqual(identity, {
    caseId: 'case-1',
    displayId: 'TC-001',
    title: 'Search products',
    mapping: 'matched',
    mappedCaseLabels: [],
  });
});

test('falls back to the exact pytest node name when no case binding matches', () => {
  const identity = resolveExecutionCase(
    'tests/test_shop.py::test_legacy_name[param]',
    [testCase('case-1', 'TC-001', 'Different test', 'tests/test_shop.py::test_search')],
  );

  assert.deepEqual(identity, {
    caseId: null,
    displayId: null,
    title: 'test_legacy_name[param]',
    mapping: 'unmatched',
    mappedCaseLabels: [],
  });
});

test('reports ambiguous bindings rather than assigning an execution to the wrong case', () => {
  const nodeid = 'tests/test_shop.py::test_search';
  const identity = resolveExecutionCase(nodeid, [
    testCase('case-1', 'TC-001', 'Search products', nodeid),
    testCase('case-2', 'TC-002', 'Search variants', nodeid),
  ]);

  assert.equal(identity.mapping, 'ambiguous');
  assert.equal(identity.caseId, null);
  assert.equal(identity.title, 'test_search');
  assert.deepEqual(identity.mappedCaseLabels, [
    'TC-001 · Search products',
    'TC-002 · Search variants',
  ]);
});

test('pairs multiple failure records to their own executions and runs', () => {
  const executions = [
    execution('exec-1', 'tests/test_a.py::test_a'),
    execution('exec-2', 'tests/test_b.py::test_b'),
  ];
  const rows = buildTestExecutionRows(executions, [], [
    failure('failure-2', 'exec-2'),
    failure('failure-other-run', 'exec-1', 'run-2'),
    failure('failure-1', 'exec-1'),
  ]);

  assert.deepEqual(rows.map((row) => row.failure?.id), ['failure-1', 'failure-2']);
  assert.deepEqual(rows.map((row) => row.identity.title), ['test_a', 'test_b']);
});

test('keeps empty execution collections empty', () => {
  assert.deepEqual(buildTestExecutionRows([], [], []), []);
});
