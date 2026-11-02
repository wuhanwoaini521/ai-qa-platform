import test from 'node:test';
import assert from 'node:assert/strict';

const { measuredPercentage, hasInsufficientQualityEvidence } = await import('../src/pages/qualityMetricsModel.ts');

const coverage = (overrides = {}) => ({
  total_requirements: 1,
  covered_requirements: 0,
  requirement_coverage_pct: 0,
  total_test_cases: 1,
  manual_cases: 1,
  draft_cases: 0,
  automated_cases: 0,
  automation_coverage_pct: 0,
  executed_cases_recent: 1,
  execution_coverage_pct: 0,
  requirement_details: [],
  ...overrides,
});

test('zero denominators are unavailable, while measured zero remains zero', () => {
  assert.equal(measuredPercentage(0, 0), null);
  assert.equal(measuredPercentage(0, 1), 0);
  assert.equal(measuredPercentage(42, 2), 42);
});

test('quality evidence is incomplete without requirements or recent executions', () => {
  assert.equal(hasInsufficientQualityEvidence(coverage({ total_requirements: 0 })), true);
  assert.equal(hasInsufficientQualityEvidence(coverage({ executed_cases_recent: 0 })), true);
  assert.equal(hasInsufficientQualityEvidence(coverage()), false);
});
