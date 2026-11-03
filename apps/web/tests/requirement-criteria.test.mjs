import assert from 'node:assert/strict';
import test from 'node:test';
import { criteriaTextFor, requirementDocumentWithCriteria } from '../src/features/lifecycle/requirementCriteria.ts';

const requirement = (criteria, acceptanceCriteria = '') => ({
  id: 'req-1',
  project_id: 'project-1',
  title: 'Checkout',
  description: '',
  acceptance_criteria: acceptanceCriteria,
  status: 'DRAFT',
  qa_model: {
    display_id: 'REQ-1',
    criteria,
    rules: [],
    constraints: [],
    dependencies: [],
    history: [],
  },
});

test('criteriaTextFor prefers structured criteria and trims blank lines', () => {
  assert.equal(criteriaTextFor(requirement([
    { id: 'AC-001', description: '  first  ', negative_required: false },
    { id: 'AC-002', description: 'second', negative_required: false },
  ], 'outdated text')), 'first\nsecond');
});

test('criteriaTextFor falls back to legacy acceptance text', () => {
  assert.equal(criteriaTextFor({ ...requirement([]), acceptance_criteria: ' one \n\n two ' }), 'one\ntwo');
});

test('requirementDocumentWithCriteria preserves identities when text changes and order moves', () => {
  const source = requirement([
    { id: 'AC-001', description: 'Alpha', negative_required: true },
    { id: 'AC-002', description: 'Beta', negative_required: false },
  ]);
  const updated = requirementDocumentWithCriteria(source, ['Beta', 'Alpha revised']);
  assert.deepEqual(updated.criteria, [
    { id: 'AC-002', description: 'Beta', negative_required: false },
    { id: 'AC-001', description: 'Alpha revised', negative_required: true },
  ]);
});

test('new criteria receive IDs that do not collide with existing criteria', () => {
  const source = requirement([
    { id: 'AC-001', description: 'Existing', negative_required: false },
  ]);
  const updated = requirementDocumentWithCriteria(source, ['Existing', 'New']);
  assert.deepEqual(updated.criteria.map(({ id }) => id), ['AC-001', 'AC-002']);
  assert.equal(updated.display_id, 'REQ-1');
});
