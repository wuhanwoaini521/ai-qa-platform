import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TestCase, TestExecution } from '../../types';
import { buildTestExecutionRows, type ExecutionFailureReference } from './testExecutionResultsModel';
import './testExecutionResults.css';

interface TestExecutionResultsProps {
  executions: TestExecution[];
  testCases: TestCase[];
  failures: ExecutionFailureReference[];
  title?: string;
  loading?: boolean;
  loadError?: boolean;
  caseMappingUnavailable?: boolean;
  onOpenFailure?: (failureId: string) => void;
}

function durationLabel(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`;
}

function statusTone(status: string): string {
  if (status === 'FAILED' || status === 'ERROR') return 'failed';
  if (status === 'PASSED') return 'passed';
  if (status === 'RUNNING' || status === 'QUEUED') return 'running';
  return 'muted';
}

export function TestExecutionResults({
  executions,
  testCases,
  failures,
  title,
  loading = false,
  loadError = false,
  caseMappingUnavailable = false,
  onOpenFailure,
}: TestExecutionResultsProps) {
  const { t } = useTranslation('workspace');
  const rows = useMemo(
    () => buildTestExecutionRows(executions, testCases, failures),
    [executions, testCases, failures],
  );
  const failedCount = executions.filter((item) => ['FAILED', 'ERROR'].includes(item.status)).length;
  const passedCount = executions.filter((item) => item.status === 'PASSED').length;

  return (
    <section className="run-execution-results" aria-label={title ?? t('result.caseExecutionResults.title')}>
      <header className="run-execution-results-heading">
        <h3>{title ?? t('result.caseExecutionResults.title')}</h3>
        {rows.length > 0 && <span>{t('result.caseExecutionResults.summary', { count: rows.length, passed: passedCount, failed: failedCount })}</span>}
      </header>
      {caseMappingUnavailable && <p className="run-execution-results-notice" role="status">{t('result.caseExecutionResults.mappingUnavailable')}</p>}
      {!rows.length ? (
        <p className="run-execution-results-empty" role={loadError ? 'alert' : undefined}>{loadError ? t('result.caseExecutionResults.loadError') : loading ? t('result.caseExecutionResults.loading') : t('result.caseExecutionResults.empty')}</p>
      ) : (
        <ol className="run-execution-results-list">
          {rows.map(({ execution, identity, failure }) => {
            const tone = statusTone(execution.status);
            const errorMessage = execution.error_message?.trim() || failure?.message.trim() || failure?.title || '';
            const hasFailure = ['FAILED', 'ERROR'].includes(execution.status);
            const showFullEvidence = Boolean(errorMessage && (errorMessage.length > 120 || errorMessage.includes('\n'))) || Boolean(execution.stack_trace?.trim());
            return (
              <li key={execution.id} className={`run-execution-result is-${tone}`}>
                <div className="run-execution-result-main">
                  <div className="run-execution-result-identity">
                    <div>
                      {identity.displayId && <code>{identity.displayId}</code>}
                      <strong>{identity.title}</strong>
                    </div>
                    <small><code>{execution.nodeid}</code></small>
                    {identity.mapping === 'ambiguous' && <small className="run-execution-result-ambiguity">{t('result.caseExecutionResults.ambiguousMapping', { cases: identity.mappedCaseLabels.join(' / ') })}</small>}
                  </div>
                  <span className="run-execution-result-duration"><span>{t('result.duration')}</span>{durationLabel(execution.duration_ms)}</span>
                  <span className={`run-execution-result-status is-${tone}`}>{t(`result.executionStatus.${execution.status}`, { defaultValue: execution.status })}</span>
                </div>
                {hasFailure && (
                  <div className="run-execution-result-failure">
                    <p>{errorMessage || t('result.caseExecutionResults.failureMessageUnavailable')}</p>
                    {showFullEvidence && <details>
                      <summary>{t('result.caseExecutionResults.fullFailureEvidence')}</summary>
                      {errorMessage && <pre>{errorMessage}</pre>}
                      {execution.stack_trace?.trim() && <pre>{execution.stack_trace}</pre>}
                    </details>}
                    {failure && (onOpenFailure
                      ? <button type="button" className="btn btn-secondary btn-sm" onClick={() => onOpenFailure(failure.id)}>{t('result.caseExecutionResults.openFailure')}</button>
                      : <Link className="btn btn-secondary btn-sm" to={`/failures/${encodeURIComponent(failure.id)}`}>{t('result.caseExecutionResults.openFailure')}</Link>)}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
