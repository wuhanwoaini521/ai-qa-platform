import test from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAULT_VIEWPORT,
  foldLiveEvent,
  initialLiveState,
  isTerminalRunStatus,
  normalizeEvent,
  overlayBoxes,
  toneFor,
} from '../src/features/workspace/discoveryLive.ts';

const frame = (metadata = {}) => ({
  type: 'browser.frame',
  seq: 3,
  at: '2026-01-01T00:00:03Z',
  metadata: { mime_type: 'image/jpeg', url: 'http://shop.test/', frame: 'AAAA', ...metadata },
});

const inventory = (elements, seq = 4) => ({
  type: 'element.inventory',
  seq,
  at: '2026-01-01T00:00:04Z',
  message: '已识别 2 个可交互元素。',
  metadata: { state_id: 's1', elements },
});

const button = { index: 0, tag: 'button', role: 'button', name: 'Add to cart', bounding_box: { x: 100, y: 200, width: 160, height: 40 } };
const search = { index: 1, tag: 'input', role: 'textbox', name: 'Search', bounding_box: { x: 0, y: 40, width: 320, height: 32 } };

test('frames become a data url and are counted, never treated as extra events', () => {
  const state = foldLiveEvent(initialLiveState(), frame());
  assert.equal(state.frame, 'data:image/jpeg;base64,AAAA');
  assert.equal(state.url, 'http://shop.test/');
  assert.equal(state.counts.frames, 1);
  assert.deepEqual(state.viewport, DEFAULT_VIEWPORT);
});

test('a frame without payload keeps the previous frame visible', () => {
  const withFrame = foldLiveEvent(initialLiveState(), frame());
  const degraded = foldLiveEvent(withFrame, frame({ frame: '' }));
  assert.equal(degraded.frame, 'data:image/jpeg;base64,AAAA');
  assert.equal(degraded.counts.frames, 1);
});

test('the frame metadata viewport drives overlay scaling', () => {
  const state = foldLiveEvent(initialLiveState(), frame({ viewport: { width: 800, height: 600 } }));
  assert.deepEqual(state.viewport, { width: 800, height: 600 });
  const boxes = overlayBoxes([button], state.viewport);
  assert.equal(boxes.length, 1);
  assert.equal(Math.round(boxes[0].left), Math.round((100 / 800) * 100));
  assert.equal(Math.round(boxes[0].width), Math.round((160 / 800) * 100));
});

test('element inventory keeps geometry and exposes it as clipped percentages', () => {
  const state = foldLiveEvent(initialLiveState(), inventory([button, search]));
  assert.equal(state.counts.elements, 2);
  const boxes = overlayBoxes(state.elements, state.viewport);
  assert.deepEqual(boxes.map((box) => box.tone), ['interactive', 'form']);
  const cart = boxes.find((box) => box.label === 'Add to cart');
  assert.equal(Math.round(cart.left), Math.round((100 / 1280) * 100));
  assert.equal(Math.round(cart.top), Math.round((200 / 720) * 100));
});

test('elements without geometry and off-viewport or tiny boxes are not drawn', () => {
  const boxes = overlayBoxes(
    [
      { index: 0, name: 'no box', bounding_box: null },
      { index: 1, name: 'below the fold', bounding_box: { x: 10, y: 900, width: 100, height: 40 } },
      { index: 2, name: 'hairline', bounding_box: { x: 10, y: 10, width: 100, height: 1 } },
      { index: 3, name: 'partly off screen', bounding_box: { x: -40, y: -20, width: 100, height: 60 } },
    ],
    { width: 1280, height: 720 },
  );
  assert.deepEqual(boxes.map((box) => box.label), ['partly off screen']);
  assert.equal(boxes[0].left, 0);
  assert.equal(boxes[0].top, 0);
  assert.equal(Math.round(boxes[0].width), Math.round((60 / 1280) * 100));
});

test('navigating away invalidates measured boxes until the next inventory', () => {
  let state = foldLiveEvent(initialLiveState(), inventory([button]));
  state = foldLiveEvent(state, { type: 'page.state', seq: 5, metadata: { url: 'http://shop.test/product/1' } });
  assert.equal(state.elementsStale, true);
  assert.deepEqual(overlayBoxes(state.elements, state.viewport).length, 1);
  state = foldLiveEvent(state, inventory([search], 6));
  assert.equal(state.elementsStale, false);
});

test('snapshot replays persisted history newest first and does not duplicate it', () => {
  const persisted = [
    { id: 'e1', type: 'run.started', message: 'started', created_at: '2026-01-01T00:00:01Z' },
    { id: 'e2', type: 'page.opened', message: 'opened', created_at: '2026-01-01T00:00:02Z' },
  ];
  let state = foldLiveEvent(initialLiveState(), { type: 'snapshot', seq: 0, status: 'RUNNING', events: persisted });
  assert.equal(state.status, 'RUNNING');
  assert.deepEqual(state.timeline.map((event) => event.type), ['page.opened', 'run.started']);
  state = foldLiveEvent(state, { type: 'snapshot', seq: 0, status: 'RUNNING', events: persisted });
  assert.deepEqual(state.timeline.map((event) => event.id), ['e2', 'e1']);
});

test('the timeline is bounded and drops duplicates', () => {
  let state = initialLiveState();
  state = foldLiveEvent(state, { type: 'finding', seq: 1, message: 'a' }, { timelineLimit: 3 });
  state = foldLiveEvent(state, { type: 'finding', seq: 1, message: 'a' }, { timelineLimit: 3 });
  assert.equal(state.timeline.length, 1);
  for (const seq of [2, 3, 4]) state = foldLiveEvent(state, { type: 'finding', seq, message: `f${seq}` }, { timelineLimit: 3 });
  assert.deepEqual(state.timeline.map((event) => event.seq), [4, 3, 2]);
  assert.equal(state.counts.findings, 4);
});

test('a finished run stops the stream and keeps the last frame', () => {
  let state = foldLiveEvent(initialLiveState(), frame());
  state = foldLiveEvent(state, { type: 'run.finished', seq: 9, metadata: { status: 'COMPLETED' } });
  assert.equal(state.status, 'COMPLETED');
  assert.equal(state.streamStatus, 'ended');
  assert.equal(state.frame, 'data:image/jpeg;base64,AAAA');
  assert.equal(isTerminalRunStatus('BLOCKED'), true);
  assert.equal(isTerminalRunStatus('RUNNING'), false);
});

test('an AI outage is surfaced and never fabricates a decision', () => {
  const state = foldLiveEvent(initialLiveState(), {
    type: 'ai.unavailable',
    seq: 7,
    message: 'AI 探索规划 不可用',
    metadata: { stage: '探索规划', code: 'TIMEOUT' },
  });
  assert.equal(state.aiUnavailable.stage, '探索规划');
  assert.equal(state.decision, null);
});

test('tone reflects the element, and malformed events are ignored', () => {
  assert.equal(toneFor(button), 'interactive');
  assert.equal(toneFor(search), 'form');
  assert.equal(toneFor({ tag: 'div', role: 'generic' }), 'uncertain');
  assert.equal(normalizeEvent(null), null);
  assert.equal(normalizeEvent({ type: 42 }), null);
  const state = initialLiveState();
  assert.equal(foldLiveEvent(state, { type: '' }), state);
});
