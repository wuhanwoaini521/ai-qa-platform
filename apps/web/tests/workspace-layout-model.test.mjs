import test from 'node:test';
import assert from 'node:assert/strict';

const { workspacePanelMode } = await import('../src/features/workspace/workspaceLayoutModel.ts');

const mode = (overrides = {}) => workspacePanelMode({
  viewportWidth: 1524,
  workspaceWidth: 1170,
  contextOpen: true,
  contextWidth: 230,
  inspectorWidth: 380,
  isStudioView: false,
  isResultView: false,
  ...overrides,
});

test('stacks context above the primary panel before it falls below its minimum width', () => {
  assert.deepEqual(mode({ viewportWidth: 1024, workspaceWidth: 888 }), { contextCompact: true, stackContext: true, inspectorModal: true });
  assert.deepEqual(mode({ viewportWidth: 1280, workspaceWidth: 926 }), { contextCompact: true, stackContext: true, inspectorModal: true });
  assert.deepEqual(mode({ viewportWidth: 1366, workspaceWidth: 1012 }), { contextCompact: true, stackContext: true, inspectorModal: true });
  assert.equal(mode({ viewportWidth: 390, workspaceWidth: 354 }).contextCompact, true);
});

test('uses a modal inspector when side-by-side panels would crowd the main content', () => {
  assert.equal(mode().inspectorModal, true);
  assert.equal(mode({ contextOpen: false }).inspectorModal, true);
  assert.equal(mode({ contextOpen: false, isStudioView: true }).inspectorModal, true);
  assert.equal(mode({ workspaceWidth: 1566, viewportWidth: 1920, contextOpen: false, isStudioView: true }).inspectorModal, false);
  assert.equal(mode({ workspaceWidth: 1566, viewportWidth: 1920, contextOpen: false, isStudioView: true }).stackContext, false);
});

test('keeps the inspector beside the main panel when both can retain useful width', () => {
  assert.deepEqual(
    mode({ workspaceWidth: 1566, viewportWidth: 1920 }),
    { contextCompact: false, stackContext: false, inspectorModal: false },
  );
  assert.equal(mode({ workspaceWidth: 1212, viewportWidth: 1600, contextOpen: false }).inspectorModal, false);
  assert.equal(mode({ workspaceWidth: 1352, viewportWidth: 1600, contextOpen: false, isStudioView: true }).inspectorModal, false);
});

test('results do not reserve width for the hidden context rail', () => {
  assert.equal(mode({ contextOpen: true, isResultView: true, workspaceWidth: 1300, viewportWidth: 1600 }).stackContext, false);
  assert.equal(mode({ contextOpen: true, isResultView: true, workspaceWidth: 1300, viewportWidth: 1600 }).inspectorModal, false);
});
