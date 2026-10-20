import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CANVAS_HEADER_HEIGHT,
  CANVAS_ROW_HEIGHT,
  canvasIsLive,
  columnX,
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
