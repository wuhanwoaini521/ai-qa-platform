/**
 * Contract tests for the agent execution tree.
 *
 * The tree is a read model of stored rows, so these tests pin the mapping and the layout rules that
 * keep it honest: depth comes from the recorded parent, every edge lands on a rendered node, a
 * collapse hides only real descendants, and a duration is never invented.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  descendantsOf,
  formatDuration,
  nodeDepths,
  traceExtent,
  traceIsLive,
  treeEdges,
  treeNodes,
  treeStateLabel,
  treeTone,
} from '../src/features/canvas/executionTreeModel.ts';

function node(id, overrides = {}) {
  return {
    id,
    type: 'invocation',
    label: id,
    subtitle: null,
    status: 'COMPLETED',
    task_id: 'task_1',
    step_id: null,
    invocation_id: null,
    parent_id: null,
    started_at: '2026-10-21T06:00:00Z',
    finished_at: null,
    duration_ms: null,
    provider: null,
    model: null,
    token_usage: null,
    cost: null,
    pricing: 'unpriced',
    evidence_ids: [],
    inputs: {},
    outputs: {},
    error_code: null,
    error_message: null,
    links: {},
    unknown: [],
    ...overrides,
  };
}

function trace(nodes, edges) {
  return {
    project_id: 'proj_1',
    generated_at: '2026-10-21T06:00:00Z',
    root_task_id: 'task_1',
    root_count: 1,
    status: 'COMPLETED',
    nodes,
    edges,
    counts: {},
    unknown: [],
  };
}

const TASK = node('task:task_1', { type: 'task', status: 'COMPLETED', duration_ms: 36000 });
const STEP = node('step:step_analyze', { type: 'step', parent_id: 'task:task_1', status: 'COMPLETED' });
const INVOCATION = node('invocation:inv_1', { parent_id: 'step:step_analyze', status: 'SUCCESS', provider: 'openai-compatible' });
const NESTED = node('evidence:ev_1', { type: 'evidence', parent_id: 'invocation:inv_1' });

const TRACE = trace(
  [TASK, STEP, INVOCATION, NESTED, node('run:run_1', { type: 'run', parent_id: 'task:task_1', status: 'PASSED' })],
  [
    { id: 'e1', source: 'step:step_analyze', target: 'task:task_1', type: 'CHILD_OF' },
    { id: 'e2', source: 'invocation:inv_1', target: 'step:step_analyze', type: 'INVOKES' },
    { id: 'e3', source: 'evidence:ev_1', target: 'invocation:inv_1', type: 'PRODUCES' },
    { id: 'e4', source: 'run:run_1', target: 'task:task_1', type: 'PRODUCES' },
  ],
);

test('a node takes its depth from the recorded parent, never from the order of the rows', () => {
  const depths = nodeDepths(TRACE);
  assert.equal(depths.get('task:task_1'), 0);
  assert.equal(depths.get('step:step_analyze'), 1);
  assert.equal(depths.get('invocation:inv_1'), 2);
  assert.equal(depths.get('evidence:ev_1'), 3);
  assert.equal(depths.get('run:run_1'), 1);
});

test('a node whose parent is not in the trace stays at the root instead of failing', () => {
  const orphan = trace([node('invocation:inv_orphan', { parent_id: 'step:missing' })], []);
  assert.equal(nodeDepths(orphan).get('invocation:inv_orphan'), 0);
  assert.equal(treeNodes(orphan)[0].position.x, 0);
});

test('parallel activities of one layer sit side by side in their own rows', () => {
  const cards = treeNodes(TRACE);
  const invocation = cards.find((card) => card.id === 'invocation:inv_1');
  const run = cards.find((card) => card.id === 'run:run_1');
  assert.equal(invocation.position.x, run.position.x + 236 + 76);
  // two children of the task share a column but never a row
  const stepCard = cards.find((card) => card.id === 'step:step_analyze');
  assert.equal(stepCard.position.x, run.position.x);
  assert.notEqual(stepCard.position.y, run.position.y);
});

test('every edge lands on a rendered node, and a hidden node takes its edge with it', () => {
  const cards = treeNodes(TRACE);
  const visible = new Set(cards.map((card) => card.id));
  for (const edge of treeEdges(TRACE, visible)) {
    assert.ok(visible.has(edge.source), `missing source ${edge.source}`);
    assert.ok(visible.has(edge.target), `missing target ${edge.target}`);
  }
  const collapsed = treeNodes(TRACE, { collapsed: new Set(['step:step_analyze']) });
  const afterIds = new Set(collapsed.map((card) => card.id));
  assert.ok(!afterIds.has('invocation:inv_1'));
  assert.ok(!afterIds.has('evidence:ev_1'));
  assert.deepEqual(
    treeEdges(TRACE, afterIds).map((edge) => edge.id),
    ['e1', 'e4'],
  );
});

test('collapsing a branch hides exactly its descendants', () => {
  assert.deepEqual([...descendantsOf(TRACE, 'step:step_analyze')].sort(), ['evidence:ev_1', 'invocation:inv_1']);
  assert.deepEqual([...descendantsOf(TRACE, 'invocation:inv_1')], ['evidence:ev_1']);
});

test('focus keeps the selected branch and the path back to its root', () => {
  const focused = treeNodes(TRACE, { focusId: 'invocation:inv_1' });
  // the branch, everything below it, and the path back to its root
  assert.deepEqual(focused.map((card) => card.id).sort(), ['evidence:ev_1', 'invocation:inv_1', 'step:step_analyze', 'task:task_1']);
  assert.ok(!focused.some((card) => card.id === 'run:run_1'));
});

test('status maps to the four states the tree has to make readable', () => {
  assert.equal(treeTone('RUNNING'), 'active');
  assert.equal(treeTone('completed'), 'ok');
  assert.equal(treeTone('WAITING_FOR_APPROVAL'), 'attention');
  assert.equal(treeTone('timeout'), 'bad');
  assert.equal(treeTone(null), 'idle');
  assert.equal(treeStateLabel('COMPLETED'), 'done');
  assert.equal(treeStateLabel('SUCCESS'), 'done');
  assert.equal(treeStateLabel('RUNNING'), 'running');
  assert.equal(treeStateLabel('PENDING'), 'waiting');
  assert.equal(treeStateLabel('CANCELLED'), 'failed');
  assert.equal(treeStateLabel(''), 'unknown');
});

test('a trace is live only while a recorded node is still running or waiting', () => {
  assert.equal(traceIsLive(TRACE), false);
  assert.equal(traceIsLive(trace([node('invocation:inv_2', { status: 'RUNNING' })], [])), true);
  assert.equal(traceIsLive(trace([node('invocation:inv_3', { status: 'WAITING' })], [])), true);
  assert.equal(traceIsLive(null), false);
});

test('a duration is formatted from the recorded number and never invented', () => {
  assert.equal(formatDuration(null), null);
  assert.equal(formatDuration(undefined), null);
  assert.equal(formatDuration(24), '24ms');
  assert.equal(formatDuration(3450), '3.5s');
  assert.equal(formatDuration(72000), '1m 12s');
});

test('the extent covers every card so the viewport can be decided from it', () => {
  const extent = traceExtent(treeNodes(TRACE));
  assert.equal(extent.right, 3 * (236 + 76) + 236);
  assert.ok(extent.bottom > 0);
});

test('a card carries the fields the detail panel reads, including the unknown list', () => {
  const inv = treeNodes(trace([node('invocation:inv_1', { unknown: ['step_id'] })], []))[0];
  assert.equal(inv.data.node.unknown[0], 'step_id');
  assert.equal(inv.data.state, 'done');
  assert.equal(inv.data.hasChildren, false);
});
