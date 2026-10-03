import test from 'node:test';
import assert from 'node:assert/strict';
import {
  eventWindow,
  nearEventTail,
} from '../src/features/runtime/eventWindow.ts';

test('Large event stream renders a bounded viewport while retaining all 500 event positions', () => {
  for (const scroll of [0, 500, 9000, 15808]) {
    const window = eventWindow(500, scroll, 192);
    assert.ok(window.end - window.start <= 14);
    assert.equal(window.height, 16000);
    assert.ok(window.start >= 0 && window.end <= 500);
  }
});
test('Manual scrolling pauses follow until near the real tail; empty streams remain valid', () => {
  assert.equal(nearEventTail(0, 192, 16000), false);
  assert.equal(nearEventTail(15808, 192, 16000), true);
  assert.deepEqual(eventWindow(0, 0, 192), { start: 0, end: 0, height: 0 });
});
