import type { CoverageMetric, KnowledgeNode } from './types';

export function presentCoverageMetrics(
  coverage: CoverageMetric[],
  nodes: KnowledgeNode[],
  incomplete: boolean,
): CoverageMetric[] {
  const activeBoundCaseIds = new Set(
    nodes
      .filter((node) => node.kind === 'automation' && node.status === 'ACTIVE')
      .filter((node) => typeof node.metadata.case_id === 'string' && typeof node.metadata.nodeid === 'string' && node.metadata.nodeid.trim())
      .map((node) => node.metadata.case_id as string),
  );

  return coverage.map((metric) => {
    const items = metric.key === 'automation'
      ? metric.items.map((item) => ({ ...item, covered: activeBoundCaseIds.has(item.id) }))
      : metric.key === 'execution' || metric.key === 'passed'
        ? metric.items.filter((item) => activeBoundCaseIds.has(item.id))
        : metric.items;
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
