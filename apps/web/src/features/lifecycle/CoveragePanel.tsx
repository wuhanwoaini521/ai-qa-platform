import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { CoverageMetric, ProjectKnowledge } from './types';
import { presentCoverageMetrics } from './coveragePresentation';
import './coverage-panel.css';

type CoverageItem = CoverageMetric['items'][number];

const caseMetrics = new Set(['automation', 'execution', 'passed']);

function metricCaption(metric: CoverageMetric, incomplete: boolean, t: TFunction): string {
  if (!metric.total) return t('noDenominatorShort');
  if (incomplete || metric.percentage === null) return t('metricCountIncomplete');
  const counts = { covered: metric.covered, total: metric.total };
  if (metric.key === 'automation') return t('metricCounts.automation', counts);
  if (metric.key === 'execution') return t('metricCounts.execution', counts);
  if (metric.key === 'passed') return t('metricCounts.passed', counts);
  return t('metricCounts.design', counts);
}

function itemCaseIds(item: CoverageItem, selectedMetric: string): string[] {
  if (item.case_ids) return item.case_ids;
  return caseMetrics.has(selectedMetric) ? [item.id] : [];
}

export function CoveragePanel({ graph, onOpenKnowledge }: { graph: ProjectKnowledge; onOpenKnowledge: () => void }) {
  const { t } = useTranslation('lifecycle');
  const [selected, setSelected] = useState('criteria');
  const incomplete = graph.truncated;
  const qualityMetrics = useMemo(
    () => presentCoverageMetrics(graph.coverage, incomplete),
    [graph.coverage, incomplete],
  );
  const metrics = useMemo(() => new Map(qualityMetrics.map((item) => [item.key, item])), [qualityMetrics]);
  const metric = metrics.get(selected);
  const automationByCase = useMemo(() => new Set(
    (metrics.get('automation')?.items ?? []).filter((item) => item.covered).map((item) => item.id),
  ), [metrics]);
  const executionByCase = useMemo(() => new Set(
    (metrics.get('execution')?.items ?? []).filter((item) => item.covered).map((item) => item.id),
  ), [metrics]);
  const passedByCase = useMemo(() => new Set(
    (metrics.get('passed')?.items ?? []).filter((item) => item.covered).map((item) => item.id),
  ), [metrics]);
  const latestRunByCase = useMemo(() => new Map(
    (metrics.get('passed')?.items ?? [])
      .filter((item) => item.run_id)
      .map((item) => [item.id, item.run_id as string]),
  ), [metrics]);

  const count = (value: number, denominator: number) =>
    incomplete || denominator === 0 ? '—' : `${value} / ${denominator}`;

  return (
    <div className="lc-coverage">
      <p className="lc-caption">{t('coverageBasis')}</p>
      <p className="lc-caption">{t('latestRunLinkMeaning')}</p>
      <div className="lc-metric-grid">
        {graph.coverage.map((item) => (
          <button
            key={item.key}
            className={`lc-metric ${selected === item.key ? 'selected' : ''}`}
            onClick={() => setSelected(item.key)}
            aria-pressed={selected === item.key}
          >
            <span>{t(`metric.${item.key}`)}</span>
            <strong>{incomplete || item.percentage === null ? '—' : `${item.percentage}%`}</strong>
            <small>{metricCaption(item, incomplete, t)}</small>
            <span className="lc-meter"><i style={{ width: `${incomplete ? 0 : item.percentage ?? 0}%` }} /></span>
          </button>
        ))}
      </div>

      {incomplete && <div className="lc-notice">
        <p>{t('truncated')}</p>
        <p>{t('coverageIncompleteNextStep')}</p>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenKnowledge}>{t('openKnowledgeView')}</button>
      </div>}

      <div className="lc-table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('coverageObject')}</th>
              <th>{t('selectedMetricState', { metric: metric ? t(`metric.${metric.key}`) : '' })}</th>
              <th>{t('mappedCases')}</th>
              <th>{t('automation')}</th>
              <th>{t('execution')}</th>
              <th>{t('latestPassAndSourceRun')}</th>
            </tr>
          </thead>
          <tbody>
            {metric?.items.map((item) => {
              const caseIds = itemCaseIds(item, selected);
              const automatedIds = caseIds.filter((id) => automationByCase.has(id));
              const executedIds = caseIds.filter((id) => executionByCase.has(id));
              const passedIds = caseIds.filter((id) => passedByCase.has(id));
              const runIds = [...new Set(caseIds.map((id) => latestRunByCase.get(id)).filter((id): id is string => Boolean(id)))];
              const caseCount = count(automatedIds.length, caseIds.length);
              const executionCount = count(executedIds.length, automatedIds.length);
              const passCount = count(passedIds.length, executedIds.length);

              return (
                <tr key={item.id}>
                  <td>
                    <strong>{item.label}</strong>
                    {item.summary && <p className="lc-muted">{item.summary}</p>}
                  </td>
              <td>{incomplete ? t('incompleteStatus') : item.covered ? t('covered') : t('gap')}</td>
                  <td>
                    {caseIds.length ? (
                      <details>
                        <summary>{t('mappedCasesCount', { count: caseIds.length })}</summary>
                        <div className="lc-chip-list">
                          {caseIds.map((id) => (
                            <Link className="lc-chip" key={id} to={`/projects/${graph.project_id}/test-cases/${id}`}>
                              {graph.nodes.find((node) => node.id === id)?.label ?? id}
                            </Link>
                          ))}
                        </div>
                      </details>
                    ) : '—'}
                  </td>
                  <td>{caseCount}</td>
                  <td>{executionCount}</td>
                  <td>
                    <span>{passCount}</span>
                    {runIds.length > 0 && (
                      <div className="lc-run-links">
                        {runIds.slice(0, 3).map((runId) => <Link key={runId} to={`/runs/${runId}`} aria-label={t('latestRunLinkAriaLabel', { id: runId })}>{t('latestRunLink', { id: runId.slice(-6) })}</Link>)}
                        {runIds.length > 3 && <small>{t('moreRuns', { count: runIds.length - 3 })}</small>}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {!metric?.items.length && <p className="lc-empty">{t('noDenominator')}</p>}
      <details>
        <summary>{t('gaps')} · {graph.gaps.length}</summary>
        <div className="lc-stack">
          {graph.gaps.map((item) => (
            <Link key={`${item.kind}:${item.id}`} to={`/projects/${graph.project_id}/requirements/${item.requirement_id}?tab=coverage&node=${item.label}`} className="lc-gap">
              <strong>{item.label}</strong><span>{item.summary}</span><small>{t(`gapReason.${item.reason}`)}</small>
            </Link>
          ))}
        </div>
      </details>
    </div>
  );
}
