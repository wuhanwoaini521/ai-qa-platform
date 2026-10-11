import test from 'node:test';
import assert from 'node:assert/strict';

const { isProviderUnavailableFailure } = await import('../src/components/aiExecutionTimelineModel.ts');

const failedEvent = (failureReason) => ({
  type: 'run.failed',
  metadata: failureReason ? { failure_reason: failureReason } : {},
});

test('provider connectivity failures are classified as provider unavailable', () => {
  for (const reason of [
    'provider_unavailable',
    'authentication_error',
    'authentication_failed',
    'connection_error',
    'missing_api_key',
    'network_error',
    'permission_denied',
    'rate_limited',
    'timeout',
    'upstream_error',
  ]) {
    assert.equal(isProviderUnavailableFailure(failedEvent(reason)), true, reason);
  }
});

test('generic operation and generation failures are not mislabeled as provider outages', () => {
  assert.equal(isProviderUnavailableFailure(failedEvent(undefined)), false);
  assert.equal(isProviderUnavailableFailure(failedEvent('output_limit')), false);
  assert.equal(isProviderUnavailableFailure(failedEvent('budget_exceeded')), false);
  assert.equal(isProviderUnavailableFailure(failedEvent('invalid_structured_output')), false);
  assert.equal(isProviderUnavailableFailure({ type: 'run.completed', metadata: { failure_reason: 'timeout' } }), false);
});
