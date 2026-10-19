import test from 'node:test';
import assert from 'node:assert/strict';
import { locatorLabel } from '../src/features/automation-studio/recorderSteps.ts';

test('a recorded locator keeps the shape the generated script uses', () => {
  assert.equal(locatorLabel({ kind: 'test_id', value: 'add-to-cart', nth: 0 }), 'test_id: add-to-cart [0]');
  assert.equal(locatorLabel({ kind: 'role', value: 'button', name: 'Add to cart' }), 'role: button (Add to cart)');
});

test('a step without a locator renders as an explicit blank instead of undefined', () => {
  assert.equal(locatorLabel(null), '—');
  assert.equal(locatorLabel({}), '—');
  assert.equal(locatorLabel({ kind: 'css', value: '' }), '—');
});
