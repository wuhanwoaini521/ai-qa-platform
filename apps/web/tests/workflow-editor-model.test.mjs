import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  addNode,
  applyEdit,
  autoLayout,
  connect,
  depths,
  describeInput,
  disconnect,
  emptyEditor,
  localIssues,
  nextNodeKey,
  parseInput,
  redo,
  removeNode,
  sameGraph,
  setInput,
  undo,
} from '../src/features/canvas/workflowEditorModel.ts';

const CATALOGUE = [
  { kind: 'discovery.collect_gaps', title: 'Collect', risk: 'READ', summary: '', writes: false, inputs: [{ name: 'discovery_run_id', kind: 'string', required: true, description: '' }] },
  { kind: 'discovery.analyze_gaps', title: 'Analyse', risk: 'READ', summary: '', writes: false, inputs: [] },
  { kind: 'task.request_approval', title: 'Approval', risk: 'APPROVAL', summary: '', writes: false, inputs: [] },
  { kind: 'source.write_generated', title: 'Write', risk: 'WRITE', summary: '', writes: true, inputs: [] },
];

const graph = (nodes, edges) => ({ nodes, edges });

test('a new node gets a readable key that never collides', () => {
  const first = addNode({ nodes: [], edges: [] }, CATALOGUE, 'discovery.analyze_gaps');
  assert.equal(first.key, 'analyze_gaps');
  const second = addNode(first.state, CATALOGUE, 'discovery.analyze_gaps');
  assert.equal(second.key, 'analyze_gaps_2');
  assert.equal(nextNodeKey('a.b', ['b']), 'b_2');
});

test('an unknown kind is refused instead of being added', () => {
  const result = addNode({ nodes: [], edges: [] }, CATALOGUE, 'shell.execute');
  assert.deepEqual(result, { error: 'unknown_kind' });
});

test('connecting refuses self links, duplicates and anything that closes a loop', () => {
  const base = graph(
    [
      { key: 'a', kind: 'discovery.collect_gaps' },
      { key: 'b', kind: 'discovery.analyze_gaps' },
      { key: 'c', kind: 'task.request_approval' },
    ],
    [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }],
  );
  assert.deepEqual(connect(base, 'a', 'a'), { error: 'self_link' });
  assert.deepEqual(connect(base, 'a', 'b'), { error: 'duplicate_link' });
  assert.deepEqual(connect(base, 'c', 'a'), { error: 'cycle' });
  assert.deepEqual(connect(base, 'a', 'ghost'), { error: 'missing_node' });
  const ok = connect(base, 'a', 'c');
  assert.ok('state' in ok);
  assert.equal(ok.state.edges.length, 3);
});

test('removing a node takes its links with it and disconnecting keeps both nodes', () => {
  const base = graph(
    [
      { key: 'a', kind: 'discovery.collect_gaps' },
      { key: 'b', kind: 'discovery.analyze_gaps' },
    ],
    [{ source: 'a', target: 'b' }],
  );
  const removed = removeNode(base, 'b');
  assert.equal(removed.nodes.length, 1);
  assert.equal(removed.edges.length, 0);
  const unlinked = disconnect(base, 'a', 'b');
  assert.equal(unlinked.nodes.length, 2);
  assert.equal(unlinked.edges.length, 0);
});

test('undo and redo walk a linear history and a no-op edit adds no step', () => {
  let history = emptyEditor(graph([{ key: 'a', kind: 'discovery.analyze_gaps' }], []));
  history = applyEdit(history, removeNode(history.present, 'a'));
  assert.equal(history.present.nodes.length, 0);
  assert.equal(history.past.length, 1);
  history = applyEdit(history, history.present);
  assert.equal(history.past.length, 1);
  history = undo(history);
  assert.equal(history.present.nodes.length, 1);
  history = redo(history);
  assert.equal(history.present.nodes.length, 0);
  assert.equal(redo(history).present.nodes.length, 0);
});

test('same graph compares by content, not by array identity', () => {
  const left = graph([{ key: 'a', kind: 'x', inputs: { b: 1, a: 2 } }], []);
  const right = graph([{ key: 'a', kind: 'x', inputs: { a: 2, b: 1 } }], []);
  assert.equal(sameGraph(left, right), true);
});

test('automatic layout layers by dependency and never stacks two nodes on one spot', () => {
  const state = graph(
    [
      { key: 'root', kind: 'discovery.collect_gaps' },
      { key: 'one', kind: 'discovery.analyze_gaps' },
      { key: 'two', kind: 'discovery.analyze_gaps' },
      { key: 'join', kind: 'task.request_approval' },
    ],
    [
      { source: 'root', target: 'one' },
      { source: 'root', target: 'two' },
      { source: 'one', target: 'join' },
      { source: 'two', target: 'join' },
    ],
  );
  assert.equal(depths(state).get('join'), 2);
  const laid = autoLayout(state);
  const spots = new Set(laid.nodes.map((node) => `${node.position.x}:${node.position.y}`));
  assert.equal(spots.size, 4);
  const byKey = Object.fromEntries(laid.nodes.map((node) => [node.key, node.position]));
  assert.ok(byKey.join.x > byKey.one.x && byKey.one.x > byKey.root.x);
  assert.notEqual(byKey.one.y, byKey.two.y);
});

test('local validation mirrors the server rules the editor must show instantly', () => {
  const write = graph(
    [
      { key: 'gen', kind: 'discovery.analyze_gaps' },
      { key: 'write', kind: 'source.write_generated' },
    ],
    [{ source: 'gen', target: 'write' }],
  );
  assert.deepEqual(localIssues(write, CATALOGUE).map((issue) => issue.code), ['WRITE_WITHOUT_APPROVAL']);

  const guarded = graph(
    [
      { key: 'gen', kind: 'discovery.analyze_gaps' },
      { key: 'approve', kind: 'task.request_approval' },
      { key: 'write', kind: 'source.write_generated' },
    ],
    [{ source: 'gen', target: 'approve' }, { source: 'approve', target: 'write' }],
  );
  assert.deepEqual(localIssues(guarded, CATALOGUE), []);

  const missingInput = graph([{ key: 'collect', kind: 'discovery.collect_gaps' }], []);
  assert.deepEqual(localIssues(missingInput, CATALOGUE).map((issue) => issue.code), ['MISSING_INPUT']);

  assert.deepEqual(localIssues(graph([], []), CATALOGUE).map((issue) => issue.code), ['EMPTY_GRAPH']);

  const loop = graph(
    [
      { key: 'a', kind: 'task.request_approval' },
      { key: 'b', kind: 'task.request_approval' },
    ],
    [{ source: 'a', target: 'b' }, { source: 'b', target: 'a' }],
  );
  assert.ok(localIssues(loop, CATALOGUE).some((issue) => issue.code === 'CYCLE'));
});

test('an input can be a literal or a binding to the run inputs', () => {
  assert.deepEqual(parseInput('$input.discovery_run_id', 'string'), { $input: 'discovery_run_id' });
  assert.equal(parseInput('  ', 'string'), '');
  assert.equal(parseInput('12', 'integer'), 12);
  assert.equal(parseInput('abc', 'integer'), 'abc');
  assert.equal(parseInput('true', 'boolean'), true);
  assert.deepEqual(parseInput('a, b c', 'list'), ['a', 'b c']);
  assert.equal(describeInput({ $input: 'discovery_run_id' }), '$input.discovery_run_id');
  assert.equal(describeInput(undefined), '');
});

test('setting an empty input removes it instead of storing an empty string', () => {
  const state = graph([{ key: 'a', kind: 'discovery.collect_gaps' }], []);
  const withValue = setInput(state, 'a', 'discovery_run_id', { $input: 'discovery_run_id' });
  assert.deepEqual(withValue.nodes[0].inputs, { discovery_run_id: { $input: 'discovery_run_id' } });
  const cleared = setInput(withValue, 'a', 'discovery_run_id', '');
  assert.deepEqual(cleared.nodes[0].inputs, {});
});
