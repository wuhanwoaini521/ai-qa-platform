import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const { clampWorkspaceDebugSplitRatio } = await import('../src/features/workspace/workspaceLayoutModel.ts');
const workspaceCss = await readFile(new URL('../src/features/workspace/workspace.css', import.meta.url), 'utf8');

test('write-mode test-case detail restores vertical scrolling inside the workspace panel', () => {
  assert.match(workspaceCss, /\.workspace-shell\.is-write \.workspace-main-scroll\s*\{[^}]*overflow:\s*hidden/);
  assert.match(workspaceCss, /\.workspace-shell \.workspace-main-panel\.is-cases-panel\s*>\s*\.workspace-main-scroll\s*\{[^}]*overflow-y:\s*auto/);
});

test('debug split ratio stays in a usable range and defaults on invalid values', () => {
  assert.equal(clampWorkspaceDebugSplitRatio(0.58), 0.58);
  assert.equal(clampWorkspaceDebugSplitRatio(-1), 0.35);
  assert.equal(clampWorkspaceDebugSplitRatio(2), 0.65);
  assert.equal(clampWorkspaceDebugSplitRatio(Number.NaN), 0.58);
});
