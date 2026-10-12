import test from 'node:test';
import assert from 'node:assert/strict';

const { buildRequirementSelectionModel } = await import(
  '../src/features/requirements/requirementSelectionModel.ts'
);

const requirement = (id, title, displayId) => ({
  id,
  project_id: 'project-1',
  title,
  description: '',
  acceptance_criteria: '',
  status: 'READY',
  created_at: '',
  updated_at: '',
  qa_model: displayId ? { display_id: displayId } : undefined,
});

test('shows the identity of the only current requirement without a switcher', () => {
  const current = requirement('req-1', 'Product search', 'REQ-001');
  const model = buildRequirementSelectionModel([current], current);

  assert.equal(model.kind, 'single');
  assert.equal(model.displayId, 'REQ-001');
  assert.equal(model.title, 'Product search');
  assert.deepEqual(model.options, [{ id: 'req-1', label: 'REQ-001 · Product search' }]);
});

test('lists every requirement by display ID and title and preserves the selected ID', () => {
  const first = requirement('req-1', 'Product search', 'REQ-001');
  const selected = requirement('req-2', 'Checkout confirmation', 'REQ-002');
  const model = buildRequirementSelectionModel([first, selected], selected);

  assert.equal(model.kind, 'multiple');
  assert.equal(model.selectedId, 'req-2');
  assert.equal(model.displayId, 'REQ-002');
  assert.deepEqual(model.options, [
    { id: 'req-1', label: 'REQ-001 · Product search' },
    { id: 'req-2', label: 'REQ-002 · Checkout confirmation' },
  ]);
});

test('uses a visible ID suffix when analysis has not assigned a display ID', () => {
  const draft = requirement('requirement-abc123', 'Draft requirement');
  const model = buildRequirementSelectionModel([draft], draft);

  assert.equal(model.displayId, 'ABC123');
  assert.equal(model.options[0].label, 'ABC123 · Draft requirement');
});

test('does not build a selection model before a requirement is selected', () => {
  assert.equal(buildRequirementSelectionModel([], null), null);
});
