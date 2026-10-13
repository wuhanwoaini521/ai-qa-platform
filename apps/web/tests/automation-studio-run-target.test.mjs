import test from 'node:test';
import assert from 'node:assert/strict';

const { resolveStudioRunTarget } = await import(
  '../src/features/automation-studio/runTarget.ts'
);

test('Studio toolbar targets the active file when no individual case is requested', () => {
  assert.equal(
    resolveStudioRunTarget('tests/test_shop.py'),
    'tests/test_shop.py',
  );
});

test('an explicit Test Explorer nodeid still targets only that case', () => {
  assert.equal(
    resolveStudioRunTarget(
      'tests/test_shop.py',
      'tests/test_shop.py::test_cart_quantity_controls_and_remove',
    ),
    'tests/test_shop.py::test_cart_quantity_controls_and_remove',
  );
});

test('an explicit case can run without an active editor file', () => {
  assert.equal(
    resolveStudioRunTarget(
      null,
      'tests/test_shop.py::test_search',
    ),
    'tests/test_shop.py::test_search',
  );
});

test('no active file or explicit case produces no target', () => {
  assert.equal(resolveStudioRunTarget(null), undefined);
});
