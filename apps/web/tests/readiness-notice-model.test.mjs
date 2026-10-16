import test from 'node:test';
import assert from 'node:assert/strict';

const { limitedCapabilityComponents } = await import('../src/components/readinessNoticeModel.ts');

const component = (name, status, operational_state = null) => ({
  component: name,
  status,
  operational_state,
});

test('a healthy platform limits nothing', () => {
  assert.deepEqual(
    limitedCapabilityComponents([
      component('database', 'ok'),
      component('ai', 'ok', 'READY'),
      component('jev', 'ok'),
    ]),
    [],
  );
});

test('an AI probe timeout is unconfirmed, not a lost capability', () => {
  assert.deepEqual(
    limitedCapabilityComponents([component('ai', 'warning', 'PROBE_TIMEOUT')]),
    [],
  );
});

test('a really unavailable AI still limits capability', () => {
  assert.deepEqual(
    limitedCapabilityComponents([
      component('ai', 'warning', 'SIMULATION'),
      component('ai', 'warning', 'UNAVAILABLE'),
      component('ai', 'warning', 'PROBE_FAILED'),
      component('ai', 'error', null),
    ]),
    ['ai', 'ai', 'ai', 'ai'],
  );
});

test('a non-AI warning does not raise the notice', () => {
  assert.deepEqual(limitedCapabilityComponents([component('worker', 'warning')]), []);
});
