import test from 'node:test';
import assert from 'node:assert/strict';
import {
  layoutDAG,
  graphStructure,
  FLOW_NODE_WIDTH,
  FLOW_NODE_HEIGHT,
} from '../src/features/runtime/dagLayout.ts';
const steps = [
  { id: 'a', key: 'inspect', dependencies: [] },
  { id: 'b', key: 'source', dependencies: ['inspect'] },
  { id: 'c', key: 'browser', dependencies: ['inspect'] },
  { id: 'd', key: 'decide', dependencies: ['source', 'browser'] },
];
test('Flow uses actual dependencies, lays out sibling branches at the same level and joins later', () => {
  const graph = layoutDAG(steps);
  assert.equal(graph.edges.length, 4);
  assert.equal(graph.positions.get('b').x, graph.positions.get('c').x);
  assert.notEqual(graph.positions.get('b').y, graph.positions.get('c').y);
  assert.ok(graph.positions.get('d').x > graph.positions.get('c').x);
});
test('Status updates and reordered API rows never move DAG nodes or invalidate its structure', () => {
  const next = [...steps]
    .reverse()
    .map((step) => ({ ...step, status: 'RUNNING' }));
  assert.deepEqual(layoutDAG(steps).positions, layoutDAG(next).positions);
  assert.equal(graphStructure(steps), graphStructure(next));
});
test('Dynamic real steps change structure; historical cycles and unknown dependencies are diagnosed', () => {
  assert.notEqual(
    graphStructure(steps),
    graphStructure([
      ...steps,
      { id: 'e', key: 'run', dependencies: ['decide'] },
    ]),
  );
  const graph = layoutDAG([
    { id: 'a', key: 'a', dependencies: ['b'] },
    { id: 'b', key: 'b', dependencies: ['a'] },
    { id: 'c', key: 'c', dependencies: ['missing'] },
  ]);
  assert.deepEqual(graph.cycle, ['a', 'b']);
  assert.equal(graph.unknown.length, 1);
  assert.equal(graph.edges.length, 2);
});

test('Vertical Flow preserves branches, joins and deterministic navigation order', () => {
  const graph = layoutDAG(steps, 'vertical');
  assert.equal(graph.positions.get('b').y, graph.positions.get('c').y);
  assert.notEqual(graph.positions.get('b').x, graph.positions.get('c').x);
  assert.ok(graph.positions.get('d').y > graph.positions.get('c').y);
  assert.deepEqual(graph.edges, layoutDAG(steps).edges);
  assert.deepEqual(graph.order, ['a', 'c', 'b', 'd']);
  assert.deepEqual(graph, layoutDAG([...steps].reverse(), 'vertical'));
});

test('A long vertical chain keeps a single readable column and bounds every node', () => {
  const chain = Array.from({ length: 20 }, (_, index) => ({
    id: String(index),
    key: `step-${index}`,
    dependencies: index ? [`step-${index - 1}`] : [],
  }));
  const graph = layoutDAG(chain, 'vertical');
  assert.equal(graph.width, FLOW_NODE_WIDTH + 48);
  assert.equal(new Set([...graph.positions.values()].map((p) => p.x)).size, 1);
  assert.deepEqual(
    graph.order,
    chain.map((step) => step.id),
  );
  for (const position of graph.positions.values()) {
    assert.ok(position.x + FLOW_NODE_WIDTH <= graph.width);
    assert.ok(position.y + FLOW_NODE_HEIGHT <= graph.height);
  }
});
