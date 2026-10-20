import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CANVAS_HEADER_HEIGHT,
  CANVAS_ROW_HEIGHT,
  canvasIsLive,
  columnX,
  discoveryEvidenceLine,
  flowEdges,
  flowNodes,
  stageSummary,
  statusTone,
} from '../src/features/canvas/canvasModel.ts';

const STAGES = [
  { key: 'discovery', title: '发现', kind: 'DISCOVERY', description: '' },
  { key: 'run', title: '运行', kind: 'RUN', description: '' },
  { key: 'failure', title: '失败', kind: 'FAILURE', description: '' },
];

function node(overrides) {
  return {
    id: 'run:run_1',
    kind: 'RUN',
    stage: 'run',
    title: 'run_1',
    subtitle: 'tests/test_x.py',
    status: 'PASSED',
    entity_type: 'run',
    entity_id: 'run_1',
    task_id: null,
    parent_id: null,
    started_at: null,
    finished_at: null,
    duration_ms: null,
    inputs: {},
    outputs: {},
    evidence: [],
    links: {},
    metrics: null,
    evidence_index: [],
    ...overrides,
  };
}

function canvas(nodes, edges = []) {
  return {
    project_id: 'proj_1',
    generated_at: '2026-10-19T00:00:00Z',
    stages: STAGES,
    nodes,
    edges,
    counts: { run: nodes.filter((item) => item.stage === 'run').length },
    truncated: false,
  };
}

test('a status is only a colour decision and unknown values stay quiet', () => {
  assert.equal(statusTone('PASSED'), 'ok');
  assert.equal(statusTone('RUNNING'), 'active');
  assert.equal(statusTone('WAITING_FOR_APPROVAL'), 'attention');
  assert.equal(statusTone('BLOCKED'), 'bad');
  assert.equal(statusTone('STOPPED'), 'idle');
  assert.equal(statusTone('passed'), 'ok');
  assert.equal(statusTone('SOMETHING_NEW'), 'idle');
});

test('every stage gets a column header and every node one row below the last', () => {
  const flow = flowNodes(canvas([
    node({ id: 'run:run_1' }),
    node({ id: 'run:run_2' }),
    node({ id: 'failure:fail_1', stage: 'failure', kind: 'FAILURE', status: 'LOCATOR_CHANGED' }),
  ]));

  const stages = flow.filter((item) => item.type === 'stage');
  assert.deepEqual(stages.map((item) => item.id), ['stage:discovery', 'stage:run', 'stage:failure']);
  assert.equal(stages[1].position.x, columnX(1));
  assert.equal(flow.filter((item) => item.type === 'workflow').length, 3);

  const runs = flow.filter((item) => item.type === 'workflow' && item.data.kind === 'RUN');
  assert.deepEqual(runs.map((item) => item.position.y), [CANVAS_HEADER_HEIGHT, CANVAS_HEADER_HEIGHT + CANVAS_ROW_HEIGHT]);
  assert.equal(runs[0].position.x, columnX(1));
  assert.equal(new Set(flow.map((item) => item.id)).size, flow.length);
});

test('a node card carries the tone of its own status, not the stage tone', () => {
  const flow = flowNodes(canvas([node({ id: 'failure:fail_1', stage: 'failure', kind: 'FAILURE', status: 'BLOCKED' })]));
  const card = flow.find((item) => item.id === 'failure:fail_1');
  assert.equal(card.data.tone, 'bad');
  assert.equal(card.data.status, 'BLOCKED');
});

test('edges that point at a node the canvas does not draw are dropped', () => {
  const flow = flowEdges(canvas(
    [node({ id: 'run:run_1' }), node({ id: 'failure:fail_1', stage: 'failure', kind: 'FAILURE' })],
    [
      { id: 'e1', source: 'run:run_1', target: 'failure:fail_1', kind: 'FAILED_AS', label: '失败于' },
      { id: 'e2', source: 'run:run_1', target: 'failure:gone', kind: 'FAILED_AS', label: null },
    ],
  ));
  assert.deepEqual(flow.map((item) => item.id), ['e1']);
  assert.equal(flow[0].label, '失败于');
  assert.equal(flow[0].animated, false);
});

test('only an in-flight node makes the canvas poll', () => {
  assert.equal(canvasIsLive(canvas([node({ status: 'PASSED' })])), false);
  assert.equal(canvasIsLive(canvas([node({ status: 'RUNNING' })])), true);
  assert.equal(canvasIsLive(canvas([node({ status: 'VERIFYING' })])), true);
  assert.equal(canvasIsLive(null), false);
});

test('an empty project still gets its stage columns and no invented nodes', () => {
  const flow = flowNodes(canvas([]));
  assert.equal(flow.filter((item) => item.type === 'workflow').length, 0);
  assert.equal(flow.filter((item) => item.type === 'stage').length, STAGES.length);
  assert.equal(stageSummary(canvas([])), '');
  assert.equal(stageSummary(canvas([node({}), node({ id: 'run:run_2' })])), '运行 2');
});

function discoveryNode(id, evidence) {
  return node({
    id: `discovery:${id}`,
    kind: 'DISCOVERY',
    stage: 'discovery',
    title: id,
    entity_type: 'discovery_run',
    entity_id: id,
    status: 'COMPLETED',
    metrics: {
      states: 5,
      actions: 6,
      features: 3,
      requirements: 1,
      gaps: 2,
      covered: 1,
      partial: 0,
      not_covered: 1,
      test_cases: 2,
      evidence: evidence ? { captured: true, page_states: 0, locators: 0, locators_ambiguous: 0, scenarios: 0, candidate_gaps: 0, covered: 0, undetermined: 0, state_changes: 0, dom_elements: 0, dom_elements_deduped: 0, requests: 0, requests_associated: 0, actions: 0, ...evidence } : null,
    },
  });
}

test('collapsing a stage hides its rows and keeps the column header', () => {
  const graph = canvas([
    discoveryNode('qd_1', { dom_elements: 12, dom_elements_deduped: 9, requests: 2, requests_associated: 1 }),
  ]);
  const expanded = flowNodes(graph);
  const collapsed = flowNodes(graph, { collapsed: new Set(['discovery']) });
  assert.equal(expanded.filter((node) => node.type === 'workflow').length, 1);
  assert.equal(collapsed.filter((node) => node.type === 'workflow').length, 0);
  assert.equal(collapsed.filter((node) => node.type === 'stage').length, expanded.filter((node) => node.type === 'stage').length);
  const header = collapsed.find((node) => node.id === 'stage:discovery');
  assert.equal(header.data.collapsed, true);
});

test('a collapsed stage header reports its toggle', () => {
  const graph = canvas([discoveryNode('qd_1', {})]);
  const toggles = [];
  const nodes = flowNodes(graph, { collapsed: new Set(), onToggle: (stage) => toggles.push(stage) });
  nodes.find((node) => node.id === 'stage:run').data.onToggle();
  assert.deepEqual(toggles, ['run']);
});

test('the discovery card carries the evidence line the server counted', () => {
  const graph = canvas([
    discoveryNode('qd_1', {
      dom_elements: 12,
      dom_elements_deduped: 9,
      requests: 2,
      requests_associated: 1,
      page_states: 5,
      locators_ambiguous: 2,
      scenarios: 3,
      candidate_gaps: 2,
    }),
  ]);
  const card = flowNodes(graph).find((node) => node.id === 'discovery:qd_1');
  assert.match(card.data.evidenceLine, /DOM 12→9/);
  assert.match(card.data.evidenceLine, /关联 1/);
  assert.match(card.data.evidenceLine, /歧义定位 2/);
  assert.match(card.data.evidenceLine, /缺口 2/);
});

test('a run without captured evidence shows no evidence line', () => {
  const graph = canvas([discoveryNode('qd_1', null)]);
  const card = flowNodes(graph).find((node) => node.id === 'discovery:qd_1');
  assert.equal(card.data.evidenceLine, '');
  assert.equal(discoveryEvidenceLine(null), '');
});
