import test from 'node:test';
import assert from 'node:assert/strict';

const { clampWorkspaceDebugSplitRatio } = await import('../src/features/workspace/workspaceLayoutModel.ts');

test('debug split ratio stays in a usable range and defaults on invalid values', () => {
  assert.equal(clampWorkspaceDebugSplitRatio(0.58), 0.58);
  assert.equal(clampWorkspaceDebugSplitRatio(-1), 0.35);
  assert.equal(clampWorkspaceDebugSplitRatio(2), 0.65);
  assert.equal(clampWorkspaceDebugSplitRatio(Number.NaN), 0.58);
});
