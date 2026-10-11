import type { AITraceEvent } from '../types';

const PROVIDER_UNAVAILABLE_FAILURE_REASONS = new Set([
  'authentication_error',
  'authentication_failed',
  'connection_error',
  'missing_api_key',
  'network_error',
  'permission_denied',
  'provider_unavailable',
  'rate_limited',
  'timeout',
  'upstream_error',
]);

export function isProviderUnavailableFailure(event: AITraceEvent | undefined): boolean {
  if (event?.type !== 'run.failed') return false;
  const reason = event.metadata.failure_reason;
  return typeof reason === 'string' && PROVIDER_UNAVAILABLE_FAILURE_REASONS.has(reason.trim().toLowerCase());
}
