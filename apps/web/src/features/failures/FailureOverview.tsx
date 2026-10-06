import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Bug,
  Code2,
  ExternalLink,
  Play,
  Sparkles,
} from 'lucide-react';
import type {
  AIFailureDiagnosisResponse,
  FailureRecord,
  TestRun,
} from '../../types';
import {
  displayedFailureClassification,
  failedLocatorFromFailure,
  summarizeFailureError,
  type DiagnosisState,
  type PrimaryAction,
} from './failureWorkspaceModel';

function relativeTime(value: string, locale: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return value;
  const seconds = Math.round((timestamp - Date.now()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31536000],
    ['month', 2592000],
    ['week', 604800],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
    ['second', 1],
  ];
  const [unit, size] = units.find(([, secondsPerUnit]) => Math.abs(seconds) >= secondsPerUnit) ?? units.at(-1)!;
  return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(Math.round(seconds / size), unit);
}

function statusText(run?: TestRun | null, linkedStatus?: string): string {
  return run?.status ?? linkedStatus ?? '';
}

export const FailureOverview: React.FC<{
  failure: FailureRecord;
  sourceRun: TestRun | null;
  verificationRun: TestRun | null;
  verificationRunId?: string;
  linkedVerificationStatus?: string;
  diagnosis: AIFailureDiagnosisResponse | null;
  state: DiagnosisState;
  primaryAction: PrimaryAction;
  primaryDisabled: boolean;
  showPrimaryAction?: boolean;
  primaryReason?: string;
  onPrimaryAction: () => void;
  canRetry: boolean;
  rerunning: boolean;
  onRetry: () => void;
  onOpenStudio?: () => void;
  onDebug?: () => void;
  canCreateJiraDraft: boolean;
  onCreateJiraDraft: () => void;
  relatedTests: string[];
  repairProposed: boolean;
  repairApplied: boolean;
  rerunMessage?: string | null;
}> = ({
  failure,
  sourceRun,
  verificationRun,
  verificationRunId,
  linkedVerificationStatus,
  diagnosis,
  state,
  primaryAction,
  primaryDisabled,
  showPrimaryAction = true,
  primaryReason,
  onPrimaryAction,
  canRetry,
  rerunning,
  onRetry,
  onOpenStudio,
  onDebug,
  canCreateJiraDraft,
  onCreateJiraDraft,
  relatedTests,
  repairProposed,
  repairApplied,
  rerunMessage,
}) => {
  const { t, i18n } = useTranslation('failures');
  const environment = sourceRun?.environment ?? {};
  const platform = Object.entries(environment).find(([key]) =>
    /(^|_)(os|platform|operating_system)(_|$)/i.test(key),
  )?.[1];
  const summaryKind = summarizeFailureError(failure.error_message);
  const isChinese = (i18n.resolvedLanguage ?? i18n.language).toLowerCase().startsWith('zh');
  const locatorTimeout = /TimeoutError|Locator\.\w+: Timeout/i.test(failure.error_message);
  const failedLocator = failedLocatorFromFailure(failure) || '未知定位器';
  const timeoutMs = failure.error_message.match(/Timeout\s+(\d+)\s*ms/i)?.[1] ?? '?';
  const rootCause = diagnosis?.root_cause && locatorTimeout && isChinese
    ? t('workflow.locatorTimeoutConclusion', { locator: failedLocator, duration: timeoutMs })
    : diagnosis?.root_cause;
  const classification = displayedFailureClassification(
    failure.failure_kind ?? failure.classification,
    diagnosis,
  );
  const heuristicHint = summaryKind === 'browserLaunchEperm' && classification === 'UNKNOWN';
  const primaryIcon =
    primaryAction === 'RETRY' || primaryAction === 'VERIFY_FIX'
      ? <Play size={16} />
      : primaryAction === 'CREATE_ISSUE_DRAFT'
        ? <Bug size={16} />
        : <Sparkles size={16} />;
  const verifiedStatus = statusText(verificationRun, linkedVerificationStatus);
  const verificationLabel = verifiedStatus
    ? t(`verificationStatuses.${verifiedStatus}`, { defaultValue: verifiedStatus })
    : t('notStarted');
  const repairLabel = repairApplied
    ? t('repairAppliedStatus')
    : repairProposed
      ? t('repairProposalAvailable')
      : t('repairPending');
  const currentStage =
    primaryAction === 'CREATE_ISSUE_DRAFT'
      ? null
      : state === 'VERIFYING' || state === 'VERIFIED'
        ? 'verification'
        : state === 'REPAIR_APPLIED' || primaryAction === 'RETRY'
          ? 'retry'
          : state === 'REPAIR_PROPOSED' || primaryAction === 'REVIEW_REPAIR' || primaryAction === 'GENERATE_LOCATOR_REPAIR' || (state === 'DIAGNOSED' && primaryAction === 'BLOCKED')
            ? 'repair'
            : 'diagnosis';
  const retryRunLabel = verificationRun
    ? `#${verificationRun.id.slice(0, 8)} · ${t(`verificationStatuses.${verificationRun.status}`, { defaultValue: verificationRun.status })}`
    : verificationRunId
      ? `#${verificationRunId.slice(0, 8)} · ${verificationLabel}`
      : t('notStarted');
  const verificationResult = verificationRun
    ? t(`verificationStatuses.${verificationRun.status}`, { defaultValue: verificationRun.status })
    : linkedVerificationStatus
      ? t(`verificationStatuses.${linkedVerificationStatus}`, { defaultValue: linkedVerificationStatus })
      : t('notStarted');

  return (
    <section className="card failure-overview" aria-labelledby="failure-overview-heading">
      <div className="card-header failure-overview-heading">
        <div className="failure-overview-title">
          <AlertTriangle size={17} aria-hidden="true" />
          <div>
            <span className="failure-overview-kicker">{t('failureHeader')}</span>
            <h2 id="failure-overview-heading">{failure.test_name || failure.test_nodeid.split('::').at(-1)}</h2>
            <code>{failure.test_nodeid}</code>
          </div>
        </div>
        <div className="failure-overview-badges">
          <span className="failure-status-badge">{t('failureStatus')}</span>
          <span className="failure-classification-badge">{classification}</span>
        </div>
      </div>
      <div className="card-body">
        <dl className="failure-metadata-grid">
          <div><dt>{t('run')}</dt><dd title={failure.run_id}>#{failure.run_id.slice(0, 8)}</dd></div>
          <div><dt>{t('environment')}</dt><dd>{platform || t('unknownValue')}</dd></div>
          <div><dt>{t('browser')}</dt><dd>{sourceRun?.browser || t('unknownValue')}</dd></div>
          <div><dt>{t('time')}</dt><dd title={new Date(failure.created_at).toLocaleString()}>{relativeTime(failure.created_at, i18n.language)}</dd></div>
        </dl>

        <div className="failure-decision-panel">
          <div className="failure-decision-copy">
            <span className="failure-section-label">{t('whatFailed')}</span>
            <p className="failure-summary-text">
              {summaryKind === 'browserLaunchEperm'
                ? platform
                  ? t('summary.browserLaunchWithPlatform', { platform })
                  : t('summary.browserLaunch')
                : summaryKind === 'timeout'
                  ? t('summary.timeout')
                  : summaryKind === 'assertion'
                    ? t('summary.assertion')
                    : t('summary.generic', { detail: summarizeFailureError(failure.error_message) })}
            </p>
            {rootCause && (
              <p id="failure-root-cause" className="failure-root-cause"><b>{t('rootCause')}</b> {rootCause}</p>
            )}
            {heuristicHint && <span className="failure-heuristic-badge">{t('heuristicUnconfirmed')}</span>}
          </div>
          <div className="failure-decision-action">
            <div className="failure-state-line">
              <span className={`failure-state-dot is-${state.toLowerCase().replaceAll('_', '-')}`} aria-hidden="true" />
              <span>{t('diagnosisState')}: <strong>{t(`diagnosisStateLabels.${state}`)}</strong></span>
            </div>
            {showPrimaryAction && (
              <>
                <span className="failure-section-label">{t('primaryAction')}</span>
                {primaryAction === 'BLOCKED' ? (
                  <div className="failure-manual-next-step">
                    {primaryReason && <p className="failure-action-reason" role="status">{primaryReason}</p>}
                    <p className="failure-manual-next-step-copy">{t('manualNextStepOverview')}</p>
                  </div>
                ) : (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary failure-primary-action"
                      onClick={onPrimaryAction}
                      disabled={primaryDisabled}
                    >
                      {primaryIcon}
                      {t(`primaryActions.${primaryAction}`)}
                    </button>
                    {primaryReason && <p className="failure-action-reason" role="status">{primaryReason}</p>}
                  </>
                )}
                {state === 'NOT_ANALYZED' && <p className="failure-analysis-hint">{t('analysisNotRun')}</p>}
              </>
            )}
          </div>
        </div>

        <div className="failure-verification" aria-label={t('verificationChain')}>
          <h3>{t('verificationChain')}</h3>
          <ol>
            <li><span>{t('originalRun')}</span><strong>#{failure.run_id.slice(0, 8)} · {sourceRun?.status ?? 'FAILED'}</strong></li>
            <li><span>{t('failureStep')}</span><strong>{failure.test_name || failure.test_nodeid.split('::').at(-1)}</strong></li>
            <li className={currentStage === 'diagnosis' ? 'is-current' : undefined} aria-current={currentStage === 'diagnosis' ? 'step' : undefined}>
              <span>{t('diagnosisStep')}</span>
              <strong>{t(`diagnosisStateLabels.${state}`)}</strong>
              {currentStage === 'diagnosis' && <small>{t('currentStage')}</small>}
            </li>
            <li className={currentStage === 'repair' ? 'is-current' : undefined} aria-current={currentStage === 'repair' ? 'step' : undefined}>
              <span>{t('repairStep')}</span>
              <strong>{repairLabel}</strong>
              {currentStage === 'repair' && <small>{t('currentStage')}</small>}
            </li>
            <li className={currentStage === 'retry' ? 'is-current' : undefined} aria-current={currentStage === 'retry' ? 'step' : undefined}>
              <span>{t('retryStep')}</span>
              <strong>{retryRunLabel}</strong>
              {currentStage === 'retry' && <small>{t('currentStage')}</small>}
            </li>
            <li className={currentStage === 'verification' ? 'is-current' : undefined} aria-current={currentStage === 'verification' ? 'step' : undefined}>
              <span>{t('verificationStep')}</span>
              <strong>{verificationResult}</strong>
              {currentStage === 'verification' && <small>{t('currentStage')}</small>}
            </li>
          </ol>
          {primaryAction === 'CREATE_ISSUE_DRAFT' && <p className="failure-verification-handoff">{t('issueHandoff')}</p>}
          {verificationRun?.parent_run_id === failure.run_id && <span className="failure-verification-attempt">{t('verificationAttempt', { count: 2 })}</span>}
          {rerunMessage && <p role="status" className="failure-rerun-status">{rerunMessage}</p>}
        </div>

        {relatedTests.length > 1 && (
          <aside className="failure-shared-group" role="note">
            <div>
              <strong>{t('sharedFailureTitle')}</strong>
              <p>{t('sharedFailureSummary', { count: relatedTests.length })}</p>
              <small>{t('sharedFailureHeuristic')}</small>
            </div>
            <details>
              <summary>{t('sharedFailureTests')}</summary>
              <ul>{relatedTests.map((test) => <li key={test}><code>{test}</code></li>)}</ul>
              <p>{t('groupAnalysisUnavailable')}</p>
            </details>
          </aside>
        )}

        <div className="failure-secondary-actions">
          {primaryAction !== 'BLOCKED' && (onOpenStudio || onDebug) && (
            <details>
              <summary>{t('developerActions')}</summary>
              <div className="failure-secondary-buttons">
                {onOpenStudio && <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenStudio}><Code2 size={14} />{t('openInStudio')}</button>}
                {onDebug && <button type="button" className="btn btn-secondary btn-sm" onClick={onDebug}><Bug size={14} />{t('debugFromFailure')}</button>}
              </div>
            </details>
          )}
          {(canRetry || canCreateJiraDraft) && (
            <details>
              <summary>{t('externalActions')}</summary>
              <div className="failure-secondary-buttons">
                {canRetry && primaryAction !== 'RETRY' && primaryAction !== 'VERIFY_FIX' && (
                  <button type="button" className="btn btn-secondary btn-sm" disabled={rerunning} onClick={onRetry}><Play size={14} />{rerunning ? t('rerunning') : t('rerun')}</button>
                )}
                {canCreateJiraDraft && (
                  primaryAction !== 'CREATE_ISSUE_DRAFT' &&
                  <button type="button" className="btn btn-secondary btn-sm" onClick={onCreateJiraDraft}><ExternalLink size={14} />{t('createJiraDraft')}</button>
                )}
              </div>
            </details>
          )}
        </div>
      </div>
    </section>
  );
};
