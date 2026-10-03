import React from 'react';
import { useTranslation } from 'react-i18next';
import { History, StopCircle } from 'lucide-react';
import { AITraceEvent, FailureAnalysisRun } from '../types';

export const FailureWorkflowPanel: React.FC<{
  events: AITraceEvent[];
  running: boolean;
  history: FailureAnalysisRun[];
  selectedId: string;
  onSelect: (id: string) => void;
  onCancel: () => void;
  error?: string;
}> = ({ events, running, history, selectedId, onSelect, onCancel, error }) => {
  const { t } = useTranslation('failures');
  const plan = events.find((event) => event.type === 'workflow.plan');
  const domain = String(
    plan?.metadata?.domain ??
      history.find((item) => item.id === selectedId)?.result.domain ??
      'UNKNOWN',
  );
  const latestModel = [...events]
    .reverse()
    .find(
      (event) =>
        event.type === 'model.completed' || event.type === 'model.started',
    );
  const provider = String(latestModel?.metadata?.provider ?? '');
  const model = String(latestModel?.metadata?.model ?? '');
  const fallback = latestModel?.metadata?.fallback_used === true;
  const terminal = [...events]
    .reverse()
    .find((event) =>
      ['run.completed', 'run.failed', 'run.cancelled'].includes(event.type),
    );
  const interrupted =
    history.find((item) => item.id === selectedId)?.status === 'INTERRUPTED';
  const failed = terminal?.type === 'run.failed';
  const cancelled = terminal?.type === 'run.cancelled';
  const verification = [...events]
    .reverse()
    .find(
      (event) =>
        event.type === 'workflow.step' && event.stage === 'verification',
    );
  const verified = verification?.metadata?.verified === true;
  const verifying =
    verification?.status === 'RUNNING' &&
    verification?.metadata?.test_rerun === true;
  const verificationFailed =
    verification?.status === 'FAILED' &&
    verification?.metadata?.test_rerun === true;
  const heading = running
    ? t('workflow.analyzing')
    : failed
      ? t('workflow.failed')
      : cancelled
        ? t('workflow.cancelled')
        : interrupted
          ? t('workflow.interrupted')
          : verifying
            ? t('workflow.verifying')
            : verified
              ? t('workflow.verified')
              : verificationFailed
                ? t('workflow.verificationFailed')
                : terminal
                  ? t('workflow.finished')
                  : t('workflow.ready');
  return (
    <section
      className="failure-workflow"
      aria-label={t('workflow.title')}
      aria-live="polite"
      aria-busy={running}
    >
      <div className="failure-workflow-heading">
        <div>
          <strong>{heading}</strong>
          <span className="failure-workflow-domain">
            {t(`workflow.domain.${domain}`)}
          </span>
        </div>
        {running && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onCancel}
          >
            <StopCircle size={13} /> {t('workflow.cancel')}
          </button>
        )}
      </div>
      {provider && (
        <div
          className={`failure-workflow-provider${fallback || provider === 'fake' ? ' is-fallback' : ''}`}
        >
          {t(
            provider === 'fake'
              ? 'workflow.simulation'
              : fallback
                ? 'workflow.fallback'
                : 'workflow.provider',
          )}{' '}
          · {provider}
          {model ? ` · ${model}` : ''}
        </div>
      )}
      {(error || failed || cancelled || interrupted) && (
        <p className="failure-workflow-error" role="status">
          {error || terminal?.message || t('workflow.interruptedDetail')}
        </p>
      )}
      <p className="failure-workflow-verification">
        {t('workflow.verificationBoundary')}
      </p>
      <div className="failure-workflow-history">
        <History size={14} aria-hidden="true" />
        <label htmlFor="failure-analysis-history">
          {t('workflow.history')}
        </label>
        <select
          id="failure-analysis-history"
          value={
            history.some((item) => item.id === selectedId) ? selectedId : ''
          }
          disabled={running || !history.length}
          onChange={(event) => onSelect(event.target.value)}
        >
          <option value="">
            {running
              ? t('workflow.current')
              : history.length
                ? t('workflow.selectHistory')
                : t('workflow.noHistory')}
          </option>
          {history.map((item) => (
            <option key={item.id} value={item.id}>
              {new Date(item.created_at).toLocaleString()} ·{' '}
              {t(`workflow.runStatus.${item.status}`)}
            </option>
          ))}
        </select>
      </div>
    </section>
  );
};
