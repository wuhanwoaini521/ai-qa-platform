import test from 'node:test';
import assert from 'node:assert/strict';

// Minimal in-memory localStorage so readPaneSize/writePaneSize exercise their real default path.
globalThis.localStorage = {
  store: new Map(),
  getItem(key) { return this.store.has(key) ? this.store.get(key) : null; },
  setItem(key, value) { this.store.set(key, String(value)); },
};

const { PANE_RESIZE_STEP, clampPaneSize, resizeFromKey, readPaneSize, writePaneSize } =
  await import('../src/features/workspace/usePaneResize.ts');

const bounds = { min: 120, max: 480 };

test('clampPaneSize keeps a pane between its minimum and maximum', () => {
  assert.equal(clampPaneSize(80, 120, 480), 120);
  assert.equal(clampPaneSize(600, 120, 480), 480);
  assert.equal(clampPaneSize(300, 120, 480), 300);
  assert.equal(clampPaneSize(Number.NaN, 120, 480), 120);
});

test('resizeFromKey steps by 16px and jumps to the bounds', () => {
  assert.equal(resizeFromKey('ArrowUp', 300, bounds), 300 + PANE_RESIZE_STEP);
  assert.equal(resizeFromKey('ArrowDown', 300, bounds), 300 - PANE_RESIZE_STEP);
  assert.equal(resizeFromKey('ArrowUp', 475, bounds), 480);
  assert.equal(resizeFromKey('ArrowDown', 125, bounds), 120);
  assert.equal(resizeFromKey('Home', 300, bounds), 120);
  assert.equal(resizeFromKey('End', 300, bounds), 480);
  assert.equal(resizeFromKey('Enter', 300, bounds), null);
});

test('writePaneSize/readPaneSize round-trip through storage and clamp stale values', () => {
  writePaneSize('pane-size-test', 320);
  assert.equal(readPaneSize('pane-size-test', bounds, 200), 320);
  assert.equal(localStorage.getItem('pane-size-test'), '320');

  writePaneSize('pane-size-test', 900);
  assert.equal(readPaneSize('pane-size-test', bounds, 200), 480);

  writePaneSize('pane-size-test', 10);
  assert.equal(readPaneSize('pane-size-test', bounds, 200), 120);

  assert.equal(readPaneSize('pane-size-missing', bounds, 260), 260);
});
