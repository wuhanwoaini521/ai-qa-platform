import type { CoverageMetric } from './types';

/**
 * The project knowledge graph is the authority on what is covered: every metric arrives from the API
 * with its own `covered` verdict per item (see `ProjectKnowledgeService.metric`), so this presentation
 * layer must not re-derive "automation" from bindings again. It only recomputes the ratio the panel
 * displays and refuses to claim a percentage for a truncated graph.
 */
export function presentCoverageMetrics(coverage: CoverageMetric[], incomplete: boolean): CoverageMetric[] {
  return coverage.map((metric) => {
    const items = metric.items;
    const covered = items.filter((item) => item.covered).length;

    return {
      ...metric,
      items,
      covered,
      total: items.length,
      percentage: incomplete || !items.length ? null : Math.round((covered * 1000) / items.length) / 10,
    };
  });
}
