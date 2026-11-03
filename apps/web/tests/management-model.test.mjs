import test from 'node:test';
import assert from 'node:assert/strict';
import { canChangeCaseRequirement, countCasesForRequirement, countIndependentCases, filterRequirements, filterTestCases, getCaseDisplayId, getProjectScopedCount, getRequirementDisplayId, INDEPENDENT_CASES_FILTER } from '../src/features/management/managementModel.ts';

const requirements = [
  { id: 'r3', title: 'Cart validation', description: '', acceptance_criteria: 'reject empty', external_id: null, status: 'DRAFT', updated_at: '2026-11-01T10:00:00Z' },
  { id: 'r2', title: 'Checkout', description: 'Cart flow', acceptance_criteria: '', external_id: 'EXT-2', status: 'READY', updated_at: '2026-11-02T10:00:00Z' },
  { id: 'r1', title: 'Checkout', description: '', acceptance_criteria: '', external_id: null, status: 'READY', updated_at: '2026-11-02T10:00:00Z' },
];

const cases = [
  { id: 'c3', title: 'Search basics', requirement_id: null, preconditions: '', expected_result: 'result appears', steps: ['enter cart'], tags: ['smoke'], priority: 'P2', automation_status: 'MANUAL', updated_at: '2026-11-01T10:00:00Z' },
  { id: 'c2', title: 'Checkout submit', requirement_id: 'r2', preconditions: 'cart has items', expected_result: 'order created', steps: ['submit'], tags: ['checkout'], priority: 'P0', automation_status: 'AUTOMATED', updated_at: '2026-11-02T10:00:00Z' },
  { id: 'c1', title: 'Checkout address', requirement_id: 'r2', preconditions: '', expected_result: 'address saved', steps: ['save'], tags: ['checkout'], priority: 'P1', automation_status: 'DRAFT', updated_at: '2026-11-02T10:00:00Z' },
];

test('requirements search existing text fields, filter status, and sort with stable tie breaks', () => {
  assert.deepEqual(filterRequirements(requirements, { query: 'REJECT EMPTY', status: 'DRAFT', sort: 'updated' }).map((item) => item.id), ['r3']);
  assert.deepEqual(filterRequirements(requirements, { query: '', status: 'READY', sort: 'title' }).map((item) => item.id), ['r1', 'r2']);
  assert.deepEqual(filterRequirements(requirements, { query: '', status: '', sort: 'updated' }).map((item) => item.id), ['r1', 'r2', 'r3']);
});

test('case search covers steps and tags, filters actual automation, priority, and requirement relations', () => {
  assert.deepEqual(filterTestCases(cases, { query: 'CART', automationStatus: 'MANUAL', priority: '', sort: 'updated' }).map((item) => item.id), ['c3']);
  assert.deepEqual(filterTestCases(cases, { query: '', automationStatus: '', priority: 'P0', sort: 'updated' }).map((item) => item.id), ['c2']);
  assert.deepEqual(filterTestCases(cases, { query: '', automationStatus: '', priority: '', requirementId: 'r2', sort: 'updated' }).map((item) => item.id), ['c1', 'c2']);
  assert.deepEqual(filterTestCases(cases, { query: '', automationStatus: '', priority: '', requirementId: INDEPENDENT_CASES_FILTER, sort: 'updated' }).map((item) => item.id), ['c3']);
  assert.equal(countCasesForRequirement('r2', cases), 2);
  assert.equal(countCasesForRequirement('r3', cases), 0);
  assert.equal(countIndependentCases(cases), 1);
});

test('test-design-linked cases cannot change requirement through the management list', () => {
  assert.equal(canChangeCaseRequirement({ test_design_id: 'design-1' }), false);
  assert.equal(canChangeCaseRequirement({ test_design_id: null }), true);
  assert.equal(canChangeCaseRequirement({}), true);
});

test('requirement relationship gap filters match actual linked-case counts', () => {
  const unlinked = new Set(['r3']);
  assert.deepEqual(filterRequirements(requirements, { query: '', status: '', sort: 'updated', onlyUnlinked: true }, unlinked).map((item) => item.id), ['r3']);
  assert.deepEqual(filterRequirements(requirements, { query: '', status: '', sort: 'updated', onlyLinked: true }, unlinked).map((item) => item.id), ['r1', 'r2']);
});

test('display IDs use saved model IDs and stable record suffixes as fallback', () => {
  assert.equal(getRequirementDisplayId({ ...requirements[0], qa_model: { display_id: 'REQ-3' } }), 'REQ-3');
  assert.equal(getRequirementDisplayId(requirements[0]), 'R3');
  assert.equal(getCaseDisplayId({ ...cases[0], test_model: { display_id: 'TC-3' } }), 'TC-3');
  assert.equal(getCaseDisplayId(cases[0]), 'C3');
});

test('invalid requirement status falls back to all requirements', () => {
  assert.deepEqual(filterRequirements(requirements, { query: '', status: 'INVALID', sort: 'updated' }).map((item) => item.id), ['r1', 'r2', 'r3']);
});

test('invalid case status and priority each fall back to all cases', () => {
  const expected = ['c1', 'c2', 'c3'];
  assert.deepEqual(filterTestCases(cases, { query: '', automationStatus: 'INVALID', priority: '', sort: 'updated' }).map((item) => item.id), expected);
  assert.deepEqual(filterTestCases(cases, { query: '', automationStatus: '', priority: 'INVALID', sort: 'updated' }).map((item) => item.id), expected);
});

test('project-scoped tab counts stay hidden until the selected project data is loaded', () => {
  assert.equal(getProjectScopedCount(4, 'project-a', 'project-b'), null);
  assert.equal(getProjectScopedCount(4, null, 'project-b'), null);
  assert.equal(getProjectScopedCount(4, 'project-b', 'project-b'), 4);
});

test('case priority sorting uses P0 to P3 order and then title deterministically', () => {
  assert.deepEqual(filterTestCases(cases, { query: '', automationStatus: '', priority: '', sort: 'priority' }).map((item) => item.id), ['c2', 'c1', 'c3']);
});
