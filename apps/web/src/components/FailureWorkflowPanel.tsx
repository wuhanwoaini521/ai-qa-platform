import React from 'react';
import { useTranslation } from 'react-i18next';
import { Bug, Code2, History, StopCircle } from 'lucide-react';
import { AITraceEvent, FailureAnalysisRun, FailureRecord } from '../types';
import { AIExecutionTimeline } from './AIExecutionTimeline';
import {
  failedLocatorFromFailure,
  type PrimaryAction,
} from '../features/failures/failureWorkspaceModel';

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;

export const FailureWorkflowPanel: React.FC<{
  events: AITraceEvent[];
  running: boolean;
  history: FailureAnalysisRun[];
  selectedId: string;
  onSelect: (id: string) => void;
  workflowLoading?: boolean;
  workflowError?: string;
  onCancel: () => void;
  failure: FailureRecord;
  failureCreatedAt?: string;
  changesAppliedOverride?: boolean;
  classification?: string;
  error?: string;
  primaryAction?: PrimaryAction;
  primaryActionDisabled?: boolean;
  primaryActionReason?: string;
  primaryActionPending?: boolean;
  showPrimaryAction?: boolean;
  onPrimaryAction?: () => void;
  onOpenStudio?: () => void;
  onDebug?: () => void;
}> = ({
  events,
  running,
  history,
  selectedId,
  onSelect,
  workflowLoading = false,
  workflowError = '',
  onCancel,
  failure,
  failureCreatedAt,
  changesAppliedOverride,
  classification,
  error,
  primaryAction,
  primaryActionDisabled = false,
  primaryActionReason,
  primaryActionPending = false,
  showPrimaryAction = false,
  onPrimaryAction,
  onOpenStudio,
  onDebug,
}) => {
  const { t, i18n } = useTranslation('failures');
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
      ['run.completed', 'run.failed', 'run.cancelled', 'run.timeout'].includes(event.type),
    );
  const selectedRun = history.find((item) => item.id === selectedId);
  const selectedResult = selectedRun?.result;
  const completedMetadata = asRecord(terminal?.metadata);
  const diagnosis = asRecord(selectedRun?.result.diagnosis) ?? asRecord(completedMetadata?.diagnosis);
  const diagnosisEvent = [...events]
    .reverse()
    .find((event) => event.type === 'workflow.step' && event.stage === 'diagnosis' && event.status === 'COMPLETED');
  const rootCause = typeof diagnosis?.root_cause === 'string'
    ? diagnosis.root_cause
    : diagnosisEvent?.message ?? '';
  const suggestionEvent = [...events]
    .reverse()
    .find((event) => event.type === 'workflow.step' && event.stage === 'suggestion');
  const verification = [...events]
    .reverse()
    .find(
      (event) =>
        (event.type === 'workflow.step' && event.stage === 'verification') ||
        event.type === 'verification.completed',
    );
  const rawRecommendations = diagnosis?.recommended_actions ?? suggestionEvent?.metadata.recommended_actions;
  const recommendations = Array.isArray(rawRecommendations)
    ? rawRecommendations.filter((item): item is string => typeof item === 'string')
    : [];
  const inspectionEvent = [...events]
    .reverse()
    .find((event) => event.type === 'workflow.step' && event.stage === 'inspection');
  const rawCandidates = inspectionEvent?.metadata.candidates;
  const candidates = Array.isArray(rawCandidates)
    ? rawCandidates.map(asRecord).filter((item): item is Record<string, unknown> => item !== null)
    : [];
  const observedCartControl = candidates.find((candidate) =>
    candidate.kind === 'test_id' && /add[\s_-]*to[\s_-]*cart/i.test(String(candidate.value ?? '')),
  ) ?? candidates.find((candidate) =>
    /add[\s_-]*to[\s_-]*cart|加入购物车/i.test(
      `${String(candidate.name ?? '')} ${String(candidate.value ?? '')} ${String(candidate.locator ?? '')}`,
    ),
  );
  const observedCartLocator = observedCartControl && typeof observedCartControl.locator === 'string'
    ? observedCartControl.locator
    : observedCartControl && observedCartControl.kind === 'test_id'
      ? `get_by_test_id(${JSON.stringify(observedCartControl.value)})`
      : '';
  const locatorTimeout = /LOCATOR_ERROR|LOCATOR_CHANGED/i.test(
    String(diagnosis?.classification ?? failure.failure_kind ?? failure.classification),
  ) && /TimeoutError|Locator\.\w+: Timeout/i.test(failure.error_message);
  const failedLocator = failedLocatorFromFailure(failure);
  const timeoutMs = failure.error_message.match(/Timeout\s+(\d+)\s*ms/i)?.[1] ?? '';
  const isChinese = (i18n.resolvedLanguage ?? i18n.language).toLowerCase().startsWith('zh');
  const rootCauseSummary = locatorTimeout && isChinese
    ? t('workflow.locatorTimeoutConclusion', {
        locator: failedLocator || '未知定位器',
        duration: timeoutMs || '?',
      })
    : rootCause;
  const selection = asRecord(selectedRun?.result.selection ?? completedMetadata?.selection);
  const decisionEvent = [...events]
    .reverse()
    .find((event) => event.type === 'workflow.step' && event.stage === 'decision');
  const decisionEngine = String(selection?.engine ?? selection?.provider ?? decisionEvent?.metadata.engine ?? '');
  const decisionFallbackReason = String(
    selection?.fallback_reason ?? decisionEvent?.metadata.fallback_reason ?? 'unknown',
  );
  const decisionFallbackReasonLabel =
    decisionFallbackReason === 'below_minimum_confidence' && typeof selection?.confidence === 'number'
      ? t('workflow.localDecisionLowConfidence', { confidence: selection.confidence.toFixed(2) })
      : decisionFallbackReason;
  const localDecisionFallback = /local[- ]strategy|local strategy/i.test(decisionEngine);
  const trustedDecisionBlocked = decisionEngine.toLowerCase() === 'blocked' && decisionFallbackReason !== 'unknown';
  const changesApplied = changesAppliedOverride ?? (
    typeof selectedResult?.changes_applied === 'boolean'
      ? selectedResult.changes_applied
      : suggestionEvent?.metadata.changes_applied === true
  );
  const rolledBack = selectedResult?.repair_state === 'ROLLED_BACK';
  const autoRolledBack = selectedResult?.auto_rolled_back === true;
  const testRerun = verification?.metadata.test_rerun === true || Boolean(selectedResult?.verification_run_id);
  const capturedEvidenceVerified =
    verification?.metadata.verification_source === 'captured_browser_evidence' ||
    selection?.verification_source === 'captured_browser_evidence';
  const completed = selectedRun?.status === 'COMPLETED' || terminal?.type === 'run.completed';
  const interrupted =
    history.find((item) => item.id === selectedId)?.status === 'INTERRUPTED';
  const timedOut = terminal?.type === 'run.timeout' || selectedRun?.status === 'TIMEOUT';
  const failed = terminal?.type === 'run.failed';
  const cancelled = terminal?.type === 'run.cancelled';
  const verified = verification?.metadata?.verified === true || selectedResult?.verified === true;
  const verifying =
    (verification?.status === 'RUNNING' && verification?.metadata?.test_rerun === true) ||
    (selectedResult?.repair_state === 'VERIFYING_FIX' && testRerun);
  const verificationFailed =
    (verification?.status === 'FAILED' && testRerun) ||
    (testRerun && ['FAILED', 'ERROR', 'CANCELLED'].includes(selectedResult?.verification_run_status ?? ''));
  const heading = running
    ? t('workflow.analyzing')
    : failed
      ? t('workflow.failed')
      : timedOut
        ? t('workflow.timedOut')
        : cancelled
          ? t('workflow.cancelled')
          : interrupted
            ? t('workflow.interrupted')
            : verifying
              ? t('workflow.verifying')
              : verified
              ? t('workflow.verified')
              : rolledBack
                ? t('workflow.rolledBackHeading')
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
      aria-busy={running || workflowLoading}
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
      {selectedRun && (
        <div className="failure-workflow-attempt" aria-live="polite">
          <strong>{t('workflow.selectedAttempt', { id: selectedRun.id.slice(0, 8), status: selectedRun.status })}</strong>
          <time dateTime={selectedRun.created_at}>{new Date(selectedRun.created_at).toLocaleString(i18n.resolvedLanguage ?? i18n.language)}</time>
          {workflowLoading && <span role="status">{t('workflow.loadingAttempt')}</span>}
        </div>
      )}
      {workflowError && <p className="failure-workflow-error" role="status">{t('workflow.attemptLoadFailed', { error: workflowError })}</p>}
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
      {(running || rootCause || completed) && (
        <section className="failure-workflow-result" aria-label={t('workflow.resultTitle')}>
          <div className="failure-workflow-result-heading">
            <strong>{t('workflow.resultTitle')}</strong>
            <span className={completed ? 'is-complete' : running ? 'is-running' : ''}>
              {completed ? t('workflow.finished') : running ? t('workflow.analyzing') : t('workflow.ready')}
            </span>
          </div>
          {rootCauseSummary && (
            <div className="failure-workflow-result-block">
              <span>{t('workflow.rootCause')}</span>
              <p>{rootCauseSummary}</p>
              {locatorTimeout && observedCartLocator && (
                <p className="failure-workflow-observed-locator">
                  {t('workflow.observedControl', { locator: observedCartLocator })}
                </p>
              )}
            </div>
          )}
          {running && !rootCause && (
            <p className="failure-workflow-current-stage">
              {t('workflow.currentStageLabel')}: {t(`workflow.stage.${[...events].reverse().find((event) => event.type === 'workflow.step' && event.status === 'RUNNING')?.stage ?? 'context'}`)}
            </p>
          )}
          <div className="failure-workflow-result-status">
            <span>{t('workflow.codeChangeStatus', { status: rolledBack ? t('workflow.rolledBack') : changesApplied ? t('workflow.applied') : t('workflow.notApplied') })}</span>
            <span>{t('workflow.retestStatus', { status: verified ? t('workflow.verified') : verifying ? t('workflow.verifying') : testRerun ? t('workflow.verificationFailed') : t('workflow.notRun') })}</span>
          </div>
          {rolledBack && (
            <p className="failure-workflow-fallback-note" role="status">
              {t(autoRolledBack ? 'workflow.autoRolledBack' : 'workflow.rolledBackDetail')}
            </p>
          )}
          {localDecisionFallback && (
            <p className="failure-workflow-fallback-note">
              {t(
                capturedEvidenceVerified ? 'workflow.localEvidenceDecision' : 'workflow.localDecisionFallback',
                { reason: decisionFallbackReasonLabel },
              )}
            </p>
          )}
          {trustedDecisionBlocked && (
            <p className="failure-workflow-fallback-note" role="status">
              {t('workflow.decisionBlocked', { reason: decisionFallbackReasonLabel })}
            </p>
          )}
          {!verified && (recommendations.length > 0 || (locatorTimeout && Boolean(observedCartLocator))) && (
            <div className="failure-workflow-result-block">
              <span>{t('workflow.nextSteps')}</span>
              {locatorTimeout && isChinese ? (
                <ol>
                  <li>
                    {t('workflow.locatorRepairAdvice', {
                      locator: observedCartLocator || recommendations.join(' '),
                    })}
                  </li>
                  <li>{t('workflow.locatorRetestAdvice')}</li>
                </ol>
              ) : recommendations.length > 0 ? (
                <ol>{recommendations.map((action, index) => <li key={`${index}-${action}`}>{action}</li>)}</ol>
              ) : null}
            </div>
          )}
          {showPrimaryAction && completed && primaryAction && onPrimaryAction && (
            <div className="failure-diagnosis-next-step" role="group" aria-label={t('primaryAction')}>
              <div>
                <strong>{t('nextAction')}</strong>
                <p>{primaryAction === 'BLOCKED' ? t('manualNextStep') : t(`nextActionDescriptions.${primaryAction}`, { defaultValue: primaryActionReason || t(`primaryActions.${primaryAction}`) })}</p>
                {primaryActionReason && <small role="status">{primaryActionReason}</small>}
              </div>
              {primaryAction === 'BLOCKED' ? (
                <div className="failure-manual-next-step-actions">
                  {onOpenStudio && <button type="button" className="btn btn-primary btn-sm" onClick={onOpenStudio}><Code2 size={14} />{t('openFailureCode')}</button>}
                  {onDebug && <button type="button" className="btn btn-secondary btn-sm" onClick={onDebug}><Bug size={14} />{t('debugFromFailure')}</button>}
                </div>
              ) : (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={primaryActionDisabled}
                  onClick={onPrimaryAction}
                >
                  {primaryActionPending ? t('generatingProposal') : t(`primaryActions.${primaryAction}`)}
                </button>
              )}
            </div>
          )}
          {rootCause && (
            <details className="failure-workflow-original-diagnosis">
              <summary>{t('workflow.originalDiagnosis')}</summary>
              <p>{rootCause}</p>
              {recommendations.length > 0 && <ol>{recommendations.map((action, index) => <li key={`${index}-${action}`}>{action}</li>)}</ol>}
            </details>
          )}
        </section>
      )}
      {events.length > 0 && (
        <details className="failure-workflow-live-events">
          <summary>{t('workflow.liveEvents')}</summary>
          <AIExecutionTimeline events={events} running={running} workflowMode />
        </details>
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
        <div className="failure-workflow-history-title">
          <History size={14} aria-hidden="true" />
          <strong>{t('analysisTimeline')}</strong>
        </div>
        {!failureCreatedAt && !history.length ? (
          <p className="failure-workflow-empty">{t('noDiagnosisHistory')}</p>
        ) : (
          <ol className="failure-analysis-timeline">
            {failureCreatedAt && (
              <li>
                <time dateTime={failureCreatedAt}>
                  {new Date(failureCreatedAt).toLocaleString()}
                </time>
                <span>
                  {t('failureRecorded')}
                  {classification
                    ? ` · ${t('ruleClassified', { classification })}`
                    : ''}
                </span>
              </li>
            )}
            {history.map((item) => {
              const selected = item.id === selectedId;
              const labelKey =
                item.status === 'COMPLETED'
                  ? 'analysisCompleted'
                  : item.status === 'FAILED'
                    ? 'analysisFailed'
                    : 'analysisStarted';
              return (
                <li key={item.id} className={selected ? 'is-selected' : ''}>
                  <button
                    type="button"
                    aria-pressed={selected}
                    disabled={running}
                    onClick={() => onSelect(item.id)}
                  >
                    <time dateTime={item.created_at}>
                      {new Date(item.created_at).toLocaleString()}
                    </time>
                    <span>
                      {t(labelKey)} · {t(`workflow.runStatus.${item.status}`)}
                    </span>
                    {item.events.length > 0 && (
                      <small>{item.events.length} {t('recordedEvents')}</small>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </section>
  );
};
