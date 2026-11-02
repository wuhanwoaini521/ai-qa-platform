import type { QualityCoverageSummary } from '../types';

export function measuredPercentage(value: number, denominator: number): number | null {
  return denominator > 0 ? value : null;
}

export function hasInsufficientQualityEvidence(coverage: QualityCoverageSummary): boolean {
  return coverage.total_requirements === 0 || coverage.executed_cases_recent === 0;
}
