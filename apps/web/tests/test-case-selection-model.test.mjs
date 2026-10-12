import test from 'node:test';
import assert from 'node:assert/strict';

const { buildTestCaseSelectionModel } = await import(
  '../src/features/test-cases/testCaseSelectionModel.ts'
);

const testCase = (id, title, displayId, externalCaseId) => ({
  id,
  project_id: 'project-1',
  title,
  preconditions: '',
  steps: [],
  expected_result: '',
  priority: 'P1',
  automation_status: 'MANUAL',
  tags: [],
  created_at: '',
  updated_at: '',
  test_model: displayId ? { display_id: displayId } : undefined,
  external_case_id: externalCaseId,
});

test('shows one selected test case as an identity instead of an inert selector', () => {
  const current = testCase('case-1', 'Product details', 'TC-001');
  const model = buildTestCaseSelectionModel([current], current);

  assert.equal(model.kind, 'static');
  assert.equal(model.selectedId, 'case-1');
  assert.equal(model.displayId, 'TC-001');
  assert.equal(model.title, 'Product details');
  assert.deepEqual(model.options, [{ id: 'case-1', label: 'TC-001 · Product details' }]);
});

test('lists all project cases by ID and title and preserves the selected case', () => {
  const first = testCase('case-1', 'Search products', 'TC-001');
  const selected = testCase('case-2', 'Checkout order', 'TC-002');
  const model = buildTestCaseSelectionModel([first, selected], selected);

  assert.equal(model.kind, 'select');
  assert.equal(model.selectedId, 'case-2');
  assert.deepEqual(model.options, [
    { id: 'case-1', label: 'TC-001 · Search products' },
    { id: 'case-2', label: 'TC-002 · Checkout order' },
  ]);
});

test('keeps a selector when one project case exists but none is selected', () => {
  const only = testCase('case-1', 'Only case', 'TC-001');
  const model = buildTestCaseSelectionModel([only], null);

  assert.equal(model.kind, 'select');
  assert.equal(model.selectedId, '');
  assert.deepEqual(model.options, [{ id: 'case-1', label: 'TC-001 · Only case' }]);
});

test('keeps a selector when no case is selected and supports external/fallback identifiers', () => {
  const first = testCase('case-1', 'Imported case', undefined, 'EXT-17');
  const second = testCase('case-abc123', 'Draft case');
  const model = buildTestCaseSelectionModel([first, second], null);

  assert.equal(model.kind, 'select');
  assert.equal(model.selectedId, '');
  assert.deepEqual(model.options, [
    { id: 'case-1', label: 'EXT-17 · Imported case' },
    { id: 'case-abc123', label: 'ABC123 · Draft case' },
  ]);
});

test('does not build a case selector when the project has no cases', () => {
  assert.equal(buildTestCaseSelectionModel([], null), null);
});
