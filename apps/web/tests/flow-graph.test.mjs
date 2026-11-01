import test from 'node:test';
import assert from 'node:assert/strict';

const { buildScenarioFlow, edgePath } = await import('../src/features/flow-canvas/flowGraph.ts');

const criteria = [
  { id: 'AC-001', description: 'Valid code reduces the total' },
  { id: 'AC-002', description: 'Expired code leaves the total unchanged' },
];

const scenario = {
  id: 'SCN-001',
  title: 'Apply a valid discount code',
  intent: 'Apply a coupon and read the total',
  priority: 'P0',
  path_type: 'normal',
  technique: 'equivalence',
  coverage: { criterion_ids: ['AC-001'] },
  actions: ['open checkout', 'enter code', 'submit'],
  expected_outcomes: ['total is 90.00'],
};

test('flow graph lays out criteria, scenario, actions and outcomes in order', () => {
  const layout = buildScenarioFlow(scenario, criteria);
  assert.deepEqual(layout.nodes.map((node) => node.kind), [
    'criterion',
    'scenario',
    'action',
    'action',
    'action',
    'assert',
  ]);
  assert.equal(layout.nodes[0].id, 'criterion:AC-001');
  assert.ok(!layout.nodes.some((node) => node.id === 'criterion:AC-002'));

  const actions = layout.nodes.filter((node) => node.kind === 'action');
  assert.deepEqual(actions.map((node) => node.index), [1, 2, 3]);
  assert.ok(actions[0].y < actions[1].y && actions[1].y < actions[2].y);

  const sequence = layout.edges.filter((edge) => edge.kind === 'sequence');
  assert.deepEqual(sequence.map((edge) => `${edge.from}->${edge.to}`), [
    'scenario->action:1',
    'action:1->action:2',
    'action:2->action:3',
  ]);
  const assertEdge = layout.edges.find((edge) => edge.kind === 'assert');
  assert.equal(assertEdge.from, 'action:3');
  assert.equal(assertEdge.to, 'assert:1');
});

test('flow graph is deterministic and sized to its content', () => {
  const first = buildScenarioFlow(scenario, criteria);
  const second = buildScenarioFlow(scenario, criteria);
  assert.deepEqual(first, second);
  assert.ok(first.width > 940);
  assert.ok(first.height >= 64);
});

test('flow graph handles a scenario without actions or coverage', () => {
  const layout = buildScenarioFlow(
    { ...scenario, coverage: { criterion_ids: [] }, actions: [], expected_outcomes: ['nothing happens'] },
    criteria,
  );
  assert.deepEqual(layout.nodes.map((node) => node.kind), ['scenario', 'assert']);
  assert.equal(layout.edges[0].from, 'scenario');
  assert.equal(layout.edges[0].to, 'assert:1');
});

test('edge path starts at the source right edge and ends at the target left edge', () => {
  const layout = buildScenarioFlow(scenario, criteria);
  const from = layout.nodes.find((node) => node.id === 'scenario');
  const to = layout.nodes.find((node) => node.id === 'action:1');
  const path = edgePath(from, to);
  assert.ok(path.startsWith(`M ${from.x + from.width} ${from.y + from.height / 2}`));
  assert.ok(path.endsWith(`${to.x}`));
});
