import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Activity, AlertCircle, Bot, Check, Circle, Clock3, FileCode2, Image as ImageIcon, RefreshCw, Square, Workflow } from 'lucide-react';
import { api } from '../../api/client';
import type { FailureRecord, FailureRepairWorkflow, TestCase, TestRun } from '../../types';
import type { RuntimeArtifact, RuntimeEvent, RuntimeSnapshot } from '../../types/runtime';
import type { WorkspaceContext } from '../../app/workspaceContext';
import { buildWorkspaceHref } from '../../app/workspaceContext';
import { failedLocatorFromFailure, failureSourceLocation, normalizeFailureClassification, observedRoleLocatorMismatch, summarizeFailureError } from '../failures/failureWorkspaceModel';
import { RuntimeArtifactActions } from '../runtime/RuntimeArtifactActions';

type EventFilter = 'all' | 'errors' | 'browser' | 'ai';

interface BrowserStepEvidence {
  action?: string;
  locator?: string;
  status?: string;
  file?: string;
  line?: number;
  duration_ms?: number;
}

interface WorkspaceRunResultProps {
  context: WorkspaceContext;
  run: TestRun;
  testCases: TestCase[];
  runtime: RuntimeSnapshot | null;
  runtimeConnection: string;
  runtimeError: string;
  onRefreshRuntime: () => void;
  projectId: string;
  onOpenFailure: (failureId: string) => void;
  onOpenCode: (filePath: string, lineNumber?: number) => void;
  onOpenDetails: () => void;
  onOpenStep: (stepId: string) => void;
  onStop: () => void;
  onRerun: () => void;
  onManualAnalysis: () => void;
}

function browserSteps(run: TestRun): BrowserStepEvidence[] {
  return (run.browser_sessions ?? []).flatMap((session) => {
    const values = session.page_evidence?.recent_steps;
    if (!Array.isArray(values)) return [];
    return values.filter((value): value is BrowserStepEvidence => Boolean(value) && typeof value === 'object');
  });
}

function runArtifacts(run: TestRun, runtime: RuntimeSnapshot | null): RuntimeArtifact[] {
  const correlatedArtifacts = runtime?.artifacts.filter((artifact) => artifact.test_run_id === run.id) ?? [];
  if (correlatedArtifacts.length) return correlatedArtifacts;
  return (run.external_artifacts ?? []).map((artifact) => ({
    id: artifact.id,
    artifact_id: typeof artifact.metadata_json.artifact_id === 'string' ? artifact.metadata_json.artifact_id : null,
    name: artifact.name,
    type: artifact.type,
    source: 'run',
    step_id: null,
    test_run_id: run.id,
    case_id: null,
    created_at: artifact.created_at,
    size_bytes: null,
    content_type: typeof artifact.metadata_json.content_type === 'string' ? artifact.metadata_json.content_type : null,
    url: artifact.url,
  }));
}

function eventTone(status?: string | null): string {
  const normalized = (status ?? '').toUpperCase();
  if (['FAILED', 'ERROR', 'BLOCKED'].includes(normalized)) return 'failed';
  if (['RUNNING', 'QUEUED', 'WAITING', 'WAITING_FOR_APPROVAL'].includes(normalized)) return 'running';
  if (['PASSED', 'COMPLETED', 'SUCCESS', 'SUCCEEDED'].includes(normalized)) return 'success';
  return 'muted';
}

function formatDuration(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return value >= 1000 ? (value / 1000).toFixed(1) + ' s' : Math.round(value) + ' ms';
}

function formatTime(value?: string | null): string {
  return value ? new Date(value).toLocaleTimeString() : '—';
}

export function WorkspaceRunResult({
  context,
  run,
  testCases,
  runtime,
  runtimeConnection,
  runtimeError,
  onRefreshRuntime,
  projectId,
  onOpenFailure,
  onOpenCode,
  onOpenDetails,
  onOpenStep,
  onStop,
  onRerun,
  onManualAnalysis,
}: WorkspaceRunResultProps) {
  const { t } = useTranslation('workspace');
  const { t: tFailures } = useTranslation('failures');
  const [failure, setFailure] = useState<FailureRecord | null>(null);
  const [failureLoadState, setFailureLoadState] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [failureRefresh, setFailureRefresh] = useState(0);
  const [repair, setRepair] = useState<FailureRepairWorkflow | null>(null);
  const [repairLoadState, setRepairLoadState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle');
  const [repairRefresh, setRepairRefresh] = useState(0);
  const [providerConfig, setProviderConfig] = useState<Awaited<ReturnType<typeof api.getAIProviderSettings>> | null>(null);
  const [jevConfig, setJevConfig] = useState<Awaited<ReturnType<typeof api.getJevSettings>> | null>(null);
  const [configurationUnavailable, setConfigurationUnavailable] = useState(false);
  const [eventFilter, setEventFilter] = useState<EventFilter>('all');
  const [logExpanded, setLogExpanded] = useState(false);
  const runRuntime = runtime?.kind === 'run' && runtime.id === run.id ? runtime : null;
  const runtimeFailureId = runRuntime?.failures.find((item) => item.test_run_id === run.id)?.id ?? null;
  const runtimeFailureIndexReady = Boolean(runRuntime);

  useEffect(() => {
    let active = true;
    setFailure(null);
    setRepair(null);
    if (!runtimeFailureIndexReady) {
      setFailureLoadState(runtimeError ? 'error' : 'loading');
      return () => { active = false; };
    }
    if (!runtimeFailureId) {
      setFailure(null);
      setFailureLoadState('loaded');
      return () => { active = false; };
    }
    setFailureLoadState('loading');
    void api.getFailure(runtimeFailureId).then((item) => {
      if (!active) return;
      if (item.run_id !== run.id) throw new Error('Failure record does not belong to the selected Run');
      setFailure(item);
      setFailureLoadState('loaded');
    }).catch(() => {
      if (!active) return;
      setFailure(null);
      setFailureLoadState('error');
    });
    return () => { active = false; };
  }, [projectId, run.id, run.status, failureRefresh, runtimeFailureId, runtimeFailureIndexReady, runtimeError]);

  useEffect(() => {
    let active = true;
    setRepair(null);
    if (!failure) {
      setRepairLoadState('idle');
      return () => { active = false; };
    }
    setRepairLoadState('loading');
    void api.getFailureRepairWorkflow(failure.id).then((value) => {
      if (!active) return;
      setRepair(value);
      setRepairLoadState('loaded');
    }).catch(() => {
      if (!active) return;
      setRepair(null);
      setRepairLoadState('error');
    });
    return () => { active = false; };
  }, [failure?.id, repairRefresh]);

  useEffect(() => {
    let active = true;
    void Promise.all([api.getAIProviderSettings(), api.getJevSettings()]).then(([provider, jev]) => {
      if (!active) return;
      setProviderConfig(provider);
      setJevConfig(jev);
      setConfigurationUnavailable(false);
    }).catch(() => {
      if (active) setConfigurationUnavailable(true);
    });
    return () => { active = false; };
  }, []);

  const events = (runRuntime?.events ?? []).filter((event) => event.test_run_id === run.id);
  const allRunRuntimeInvocations = runRuntime?.ai_invocations ?? [];
  const runInvocations = allRunRuntimeInvocations.filter((item) => item.test_run_id === run.id);
  const unlinkedAiInvocation = [...allRunRuntimeInvocations].reverse().find((item) => item.test_run_id !== run.id) ?? null;
  const unlinkedJevDecision = [...(runRuntime?.decisions ?? [])].reverse().find((item) => item.provider.trim().toLowerCase() === 'jev') ?? null;
  const unlinkedEvidenceExists = Boolean(runRuntime?.evidence.length);
  const browserEvidence = useMemo(() => browserSteps(run), [run]);
  const failedBrowserStep = [...browserEvidence].reverse().find((step) => step.status?.toUpperCase() === 'FAILED');
  const failedBrowserEvent = [...events].reverse().find((event) =>
    event.category === 'browser' && ['FAILED', 'ERROR'].includes((event.status ?? '').toUpperCase()),
  );
  const artifacts = useMemo(() => runArtifacts(run, runRuntime), [run, runRuntime]);
  const screenshots = artifacts.filter((item) => item.type.toUpperCase().includes('SCREENSHOT') || item.content_type?.startsWith('image/'));
  const traces = artifacts.filter((item) => item.type.toUpperCase().includes('TRACE'));
  const reports = artifacts.filter((item) => item.type.toUpperCase().includes('REPORT') || item.type.toUpperCase().includes('HTML'));
  const aiInvocation = runInvocations.at(-1) ?? null;
  const aiEvent = [...events].reverse().find((event) => event.category === 'ai') ?? null;
  const aiStep = aiInvocation?.step_id ? runRuntime?.steps.find((item) => item.id === aiInvocation.step_id) ?? null : null;
  const decisionEvent = [...events].reverse().find((event) =>
    event.category === 'decision'
    && (String(event.metadata.provider ?? '').trim().toLowerCase() === 'jev' || event.type.toLowerCase().includes('jev')),
  ) ?? null;
  const aiProvider = aiInvocation?.provider ?? (typeof aiEvent?.metadata.provider === 'string' ? aiEvent.metadata.provider : null);
  const aiModel = aiInvocation?.model ?? (typeof aiEvent?.metadata.model === 'string' ? aiEvent.metadata.model : null);
  const aiOutputSummary = aiStep?.outputs_summary?.trim()
    || (typeof aiEvent?.metadata.output_summary === 'string' ? aiEvent.metadata.output_summary : '');
  const repairState = repair?.state ?? null;
  const verificationRunStatus = repair?.verification_run_status?.toUpperCase() ?? null;
  const proposal = repair?.repair_proposal ?? failure?.repair_proposal ?? null;
  const repairHasJevDecision = proposal?.provider?.trim().toLowerCase() === 'jev';
  const diff = proposal?.code_diff ?? null;
  const source = failure ? failureSourceLocation(failure) : null;
  const sourcePath = failedBrowserStep?.file ?? source?.filePath ?? run.nodeids[0]?.split('::')[0] ?? null;
  const sourceLine = failedBrowserStep?.line ?? source?.lineNumber ?? undefined;
  const isTimeout = run.status === 'ERROR' && /execution timed out|timed out|timeout/i.test(run.log_output ?? '');
  const isRunActive = ['RUNNING', 'QUEUED'].includes(run.status);
  const resultCount = run.executions.length;
  const passedCount = run.executions.filter((item) => item.status === 'PASSED').length;
  const failedCount = run.executions.filter((item) => item.status === 'FAILED').length;
  const filteredEvents = useMemo(() => events.filter((event) => {
    if (eventFilter === 'errors') return ['FAILED', 'ERROR', 'BLOCKED'].includes((event.status ?? '').toUpperCase()) || event.category === 'failure';
    if (eventFilter === 'browser') return event.category === 'browser';
    if (eventFilter === 'ai') return event.category === 'ai' || event.category === 'decision';
    return true;
  }), [events, eventFilter]);

  const stageStatus = (status: string) => t('result.stageState.' + status, { defaultValue: status.replaceAll('_', ' ') });
  const rawInvocationStatus = (aiInvocation?.status ?? aiEvent?.status ?? (unlinkedAiInvocation ? 'UNAVAILABLE' : runRuntime ? 'NOT_STARTED' : 'UNAVAILABLE')).toUpperCase();
  const aiHasRecordedOutput = Boolean(aiOutputSummary);
  const invocationCompleted = ['SUCCESS', 'SUCCEEDED', 'COMPLETED', 'PASSED'].includes(rawInvocationStatus);
  const invocationStatus = invocationCompleted
    ? aiHasRecordedOutput ? 'SUCCEEDED' : 'UNAVAILABLE'
    : rawInvocationStatus;
  const jevStatus = decisionEvent?.status?.toUpperCase()
    ?? (repairHasJevDecision ? 'SUCCEEDED' : unlinkedJevDecision ? 'UNAVAILABLE' : runRuntime ? 'NOT_CALLED' : 'UNAVAILABLE');
  const jevCallObserved = Boolean(decisionEvent || repairHasJevDecision);
  const patchStatus = diff
    ? 'SUCCEEDED'
    : failureLoadState === 'loading' || repairLoadState === 'loading'
      ? 'PENDING'
      : failureLoadState === 'error' || repairLoadState === 'error'
        ? 'UNAVAILABLE'
        : repairState === 'PATCH_READY'
          ? proposal ? 'WAITING_APPROVAL' : 'UNAVAILABLE'
          : repairState === 'BLOCKED' ? 'BLOCKED' : 'NOT_STARTED';
  const applyStatus = repairState === 'APPLYING'
    ? 'RUNNING'
    : repairState === 'ROLLED_BACK'
      ? 'ROLLED_BACK'
      : proposal?.applied === true || ['PATCH_APPLIED', 'VERIFYING_FIX', 'VERIFIED'].includes(repairState ?? '')
      ? 'SUCCEEDED'
      : failureLoadState === 'loading' || repairLoadState === 'loading'
        ? 'PENDING'
        : failureLoadState === 'error' || repairLoadState === 'error'
          ? 'UNAVAILABLE'
          : repairState === 'BLOCKED' ? 'SKIPPED' : 'NOT_STARTED';
  const verificationFailureStatus = repairState === 'FAILED'
    ? 'FAILED'
    : ['FAILED', 'ERROR', 'CANCELLED'].includes(verificationRunStatus ?? '')
      ? verificationRunStatus
      : null;
  const verifyStatus = verificationFailureStatus
    ?? (repairState === 'VERIFYING_FIX'
      ? 'RUNNING'
      : repair?.verified === true || repairState === 'VERIFIED'
      ? 'SUCCEEDED'
      : failureLoadState === 'loading' || repairLoadState === 'loading'
        ? 'PENDING'
        : failureLoadState === 'error' || repairLoadState === 'error'
          ? 'UNAVAILABLE'
          : repairState === 'BLOCKED'
            ? 'SKIPPED'
            : verificationRunStatus === 'PASSED'
              ? 'UNAVAILABLE'
              : 'NOT_STARTED');
  const evidenceStatus = artifacts.length || failedBrowserEvent || failure
    ? 'SUCCEEDED'
    : unlinkedEvidenceExists || runRuntime ? 'UNAVAILABLE' : 'PENDING';
  const timeoutMessage = (run.log_output ?? '').split(/\r?\n/).reverse().find((line) => /timed out|timeout/i.test(line));
  const resultMessage = isTimeout
    ? timeoutMessage || t('result.runTimedOutDescription')
    : run.status === 'ERROR'
      ? t('result.runErrorDescription')
      : t('result.runStatusDescription.' + run.status, { defaultValue: run.status });
  const resultUnavailableDescription = isRunActive
    ? t('result.resultUnavailableActive', { status: t('result.runStatus.' + run.status, { defaultValue: run.status }) })
    : run.status === 'ERROR'
      ? t('result.resultUnavailableError')
      : t('result.resultUnavailableTerminal', { status: t('result.runStatus.' + run.status, { defaultValue: run.status }) });
  const verificationDetail = verificationRunStatus === 'PASSED' && repair?.verified !== true
    ? t('result.verificationNotConfirmed')
    : null;
  const aiProviderLabel = aiProvider
    ? [aiProvider, aiModel].filter(Boolean).join(' · ')
    : unlinkedAiInvocation
      ? [unlinkedAiInvocation.provider, unlinkedAiInvocation.model, t('result.unlinked')].filter(Boolean).join(' · ')
    : providerConfig
      ? [providerConfig.provider, providerConfig.model].filter(Boolean).join(' · ')
      : configurationUnavailable ? t('result.configUnavailable') : t('result.configLoading');
  const primaryFailureText = failure?.error_message
    ?? (failedBrowserStep
      ? [failedBrowserStep.action, failedBrowserStep.locator].filter(Boolean).join(' · ')
      : failedBrowserEvent?.summary)
    ?? (failureLoadState === 'loading'
      ? t('result.failureLoading')
      : failureLoadState === 'error' ? t('result.failureLoadError') : t('result.noFailureEvidence'));
  const failedNodeId = failure?.test_nodeid
    ?? run.executions.find((item) => ['FAILED', 'ERROR'].includes(item.status))?.nodeid;
  const expectedResult = testCases.find((item) => item.binding?.nodeid === failedNodeId)?.expected_result.trim();
  const locatorMismatch = failure ? observedRoleLocatorMismatch(failure) : null;
  const failureKind = failure
    ? locatorMismatch || summarizeFailureError(failure.error_message, failure.classification) === 'locatorTimeout'
      ? 'LOCATOR_CHANGED'
      : normalizeFailureClassification(failure.classification)
    : null;
  const failureTypeLabel = failureKind
    ? t(`result.failureTypes.${failureKind}`, { defaultValue: failureKind.replaceAll('_', ' ') })
    : t('result.failureClassificationUnavailable');
  const observedFailureSummary = locatorMismatch
    ? t('result.locatorMismatch', {
        role: t(`result.controlRoles.${locatorMismatch.role}`, { defaultValue: locatorMismatch.role }),
        expectedName: locatorMismatch.expectedName,
        observedNames: locatorMismatch.observedNames.map((name) => `“${name}”`).join('、'),
      })
    : failure?.error_message
    ? (() => {
        const summary = summarizeFailureError(failure.error_message, failure.classification);
        if (summary === 'browserLaunchEperm') return tFailures('summary.browserLaunch');
        if (summary === 'locatorTimeout') {
          return tFailures('summary.locatorTimeout', { locator: failure.failing_locator || failedLocatorFromFailure(failure) || '—' });
        }
        if (summary === 'timeout') return tFailures('summary.timeout');
        if (summary === 'assertion') return tFailures('summary.assertion');
        return tFailures('summary.generic', { detail: summary });
      })()
    : failedBrowserStep
      ? [failedBrowserStep.action, failedBrowserStep.locator].filter(Boolean).join(' · ')
      : failedBrowserEvent?.summary ?? primaryFailureText;

  const workflowStages = [
    { id: 'evidence', label: t('result.repairStages.evidence'), status: evidenceStatus, meta: artifacts.length ? t('result.artifactCount', { count: artifacts.length }) : unlinkedEvidenceExists ? t('result.evidenceUnlinked') : t('result.noEvidenceYet'), duration: null },
    { id: 'diagnosis', label: t('result.repairStages.diagnosis'), status: invocationStatus, meta: aiProvider ? [aiProvider, aiModel].filter(Boolean).join(' · ') : unlinkedAiInvocation ? t('result.aiInvocationUnlinked') : t('result.aiNotStarted'), detail: aiStep?.error ?? aiOutputSummary ?? (invocationCompleted && !aiHasRecordedOutput ? t('result.aiOutputNotRecorded') : unlinkedAiInvocation ? t('result.aiInvocationUnlinkedDetail') : aiEvent?.summary ?? null), duration: aiInvocation?.duration_ms ?? aiEvent?.duration_ms ?? null },
    { id: 'decision', label: t('result.repairStages.decision'), status: jevStatus, meta: decisionEvent ? (typeof decisionEvent.metadata.selected === 'string' ? `Jev · ${decisionEvent.metadata.selected}` : 'Jev') : repairHasJevDecision ? `Jev · ${proposal?.proposed_locator ?? proposal?.candidate_id ?? ''}` : unlinkedJevDecision ? t('result.jevDecisionUnlinked') : jevConfig?.enabled ? t('result.jevEnabledNotCalled') : t('result.jevDisabled'), detail: decisionEvent?.summary ?? null, duration: decisionEvent?.duration_ms ?? null },
    { id: 'patch', label: t('result.repairStages.patch'), status: patchStatus, meta: diff ? (proposal?.file_path ?? t('result.diffReady')) : t('result.diffNotGenerated'), duration: null },
    { id: 'apply', label: t('result.repairStages.apply'), status: applyStatus, meta: repair?.repair_id ?? t('result.patchNotApplied'), duration: null },
    { id: 'verify', label: t('result.repairStages.verify'), status: verifyStatus, meta: repair?.verification_run_id ?? t('result.verificationNotStarted'), detail: verificationDetail, duration: null },
  ];
  const retryFailureLoad = () => {
    setFailureRefresh((value) => value + 1);
    if (!runtimeFailureIndexReady) onRefreshRuntime();
  };

  return (
    <section className="workspace-result-surface" aria-label={t('result.runResult')}>
      <header className="workspace-result-topbar">
        <div className="workspace-result-identity">
          <span className={'workspace-result-badge is-' + run.status.toLowerCase()}>{t('result.runStatus.' + run.status, { defaultValue: run.status })}</span>
          <div>
            <h3>{run.requested_by || t('result.runTitle')}</h3>
            <p><code>{run.id}</code><span>{run.nodeids[0] ?? t('result.noCaseId')}</span></p>
          </div>
        </div>
        <div className="workspace-result-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onManualAnalysis} disabled={isRunActive} title={isRunActive ? t('result.waitForRunToFinish') : undefined}><Bot size={14} aria-hidden="true" />{t('result.manualAnalysis')}</button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenDetails}><Workflow size={14} aria-hidden="true" />{t('result.fullRuntime')}</button>
          {isRunActive
            ? <button type="button" className="btn btn-danger btn-sm" onClick={onStop}><Square size={13} aria-hidden="true" />{t('dock.stop')}</button>
            : <button type="button" className="btn btn-primary btn-sm" onClick={onRerun} disabled={!context.testCaseId && !run.nodeids.length}><RefreshCw size={14} aria-hidden="true" />{t('result.rerun')}</button>}
        </div>
      </header>

      <div className="workspace-result-columns">
        <section className="workspace-result-panel workspace-result-diagnosis" aria-labelledby="workspace-result-summary-title">
          <header className="workspace-result-panel-heading"><div><span>{t('result.overviewEyebrow')}</span><h4 id="workspace-result-summary-title">{t('result.summary')}</h4></div><Clock3 size={16} aria-hidden="true" /></header>
          <dl className="workspace-result-stats">
            <div><dt>{t('result.plannedTests')}</dt><dd>{run.total || run.nodeids.length || '—'}</dd></div>
            <div><dt>{t('result.savedTestResults')}</dt><dd>{resultCount}/{run.total || run.nodeids.length || '—'}</dd></div>
            <div><dt>{t('result.confirmedPassed')}</dt><dd>{resultCount ? passedCount : '—'}</dd></div>
            <div><dt>{t('result.confirmedFailed')}</dt><dd>{resultCount ? failedCount : '—'}</dd></div>
            <div><dt>{t('result.runTerminalStatus')}</dt><dd>{['ERROR', 'FAILED'].includes(run.status) ? run.status : '—'}</dd></div>
            <div><dt>{t('result.duration')}</dt><dd>{formatDuration(run.duration_ms)}</dd></div>
          </dl>

          <div className={'workspace-result-incident is-' + (run.status === 'ERROR' ? 'error' : run.status === 'FAILED' ? 'failed' : 'info')} role={run.status === 'ERROR' || run.status === 'FAILED' ? 'alert' : 'status'}>
            <AlertCircle size={17} aria-hidden="true" />
            <div>
              <strong>{isTimeout ? t('result.runTimedOut') : t('result.runOutcome.' + run.status, { defaultValue: run.status })}</strong>
              <p>{resultMessage}</p>
            </div>
          </div>

          {!resultCount && <p className="workspace-result-not-recorded"><strong>{t('result.resultUnavailable')}</strong>{resultUnavailableDescription}</p>}

          <section className="workspace-result-observation">
            <h5>{t('result.observedFailure')}</h5>
            <dl className="workspace-result-failure-facts">
              <div><dt>{t('result.expectedResult')}</dt><dd>{expectedResult || t('result.expectedResultUnavailable')}</dd></div>
              <div><dt>{t('result.observedResult')}</dt><dd>{observedFailureSummary}</dd></div>
              <div><dt>{t('result.failureClassification')}</dt><dd>{failureTypeLabel}</dd></div>
            </dl>
            {failedBrowserStep && <small>{t('result.browserStepObserved')} · {failedBrowserStep.file ?? run.nodeids[0]?.split('::')[0] ?? '—'}{failedBrowserStep.line ? ':' + failedBrowserStep.line : ''}</small>}
            {failure?.error_message && <details><summary>{tFailures('viewRawError')}</summary><pre>{failure.error_message}</pre></details>}
            {failure?.stack_trace && <details><summary>{tFailures('viewFullStack')}</summary><pre>{failure.stack_trace}</pre></details>}
          </section>

          <section className="workspace-result-next">
            <h5>{t('result.nextAction')}</h5>
            <p>{failureLoadState === 'loading'
              ? t('result.failureLoading')
              : failureLoadState === 'error'
                ? t('result.failureLoadError')
              : failureKind === 'LOCATOR_CHANGED'
                  ? t('result.checkLocatorAgainstControls')
                  : failure?.suggested_action ?? (failure ? t('result.repairAvailable') : t('result.failureRecordMissing'))}</p>
            <div>
              {failure && <button type="button" className="btn btn-secondary btn-sm" onClick={() => onOpenFailure(failure.id)}>{t('result.openFailureWorkflow')}</button>}
              {sourcePath && <button type="button" className="btn btn-secondary btn-sm" onClick={() => onOpenCode(sourcePath, sourceLine)}><FileCode2 size={13} aria-hidden="true" />{t('result.openSource')}</button>}
            </div>
          </section>
        </section>

        <section className="workspace-result-panel workspace-result-repair" aria-labelledby="workspace-repair-title">
          <header className="workspace-result-panel-heading"><div><span>{t('result.repairEyebrow')}</span><h4 id="workspace-repair-title">{t('result.repairTitle')}</h4></div><Bot size={17} aria-hidden="true" /></header>
          <div className="workspace-result-provider-row">
            <div><small>{t('result.aiProvider')}</small><strong>{aiProviderLabel}</strong><span>{aiInvocation || aiEvent ? t('result.providerUsed') : unlinkedAiInvocation ? t('result.aiInvocationUnlinked') : t('result.providerConfiguredOnly')}</span></div>
            <div><small>Jev</small><strong>{jevConfig ? jevConfig.model || t('result.modelNotSet') : configurationUnavailable ? t('result.configUnavailable') : t('result.configLoading')}</strong><span>{jevCallObserved ? t('result.jevActuallyCalled') : unlinkedJevDecision ? t('result.jevDecisionUnlinked') : jevConfig?.enabled ? t('result.jevEnabledNotCalled') : t('result.jevDisabled')}</span></div>
          </div>
          {failureLoadState === 'error' && <p className="workspace-result-blocker" role="alert"><AlertCircle size={14} aria-hidden="true" />{t('result.failureLoadError')} <button type="button" className="btn btn-secondary btn-sm" onClick={retryFailureLoad}>{t('result.retryLoad')}</button></p>}
          {failureLoadState === 'loaded' && failure && repairLoadState === 'error' && <p className="workspace-result-blocker" role="alert"><AlertCircle size={14} aria-hidden="true" />{t('result.repairLoadError')} <button type="button" className="btn btn-secondary btn-sm" onClick={() => setRepairRefresh((value) => value + 1)}>{t('result.retryLoad')}</button></p>}
          {failureLoadState === 'loaded' && !failure && !runRuntime?.ai_invocations.length && <p className="workspace-result-blocker"><AlertCircle size={14} aria-hidden="true" />{t('result.repairBlockedWithoutFailure')}</p>}
          <ol className="workspace-repair-timeline">
            {workflowStages.map((item) => {
              const tone = eventTone(item.status);
              const Icon = tone === 'success' ? Check : tone === 'failed' ? AlertCircle : tone === 'running' ? Activity : Circle;
              return <li key={item.id} className={'is-' + tone}>
                <span className="workspace-repair-marker"><Icon size={14} aria-hidden="true" /></span>
                <div><div className="workspace-repair-stage-heading"><strong>{item.label}</strong><span className={'workspace-result-state is-' + tone}>{stageStatus(item.status)}</span></div><p>{item.meta}</p>
                  {item.detail && <small className="workspace-repair-detail">{item.detail}</small>}
                  {item.id === 'diagnosis' && aiStep?.inputs_summary && <details className="workspace-repair-input"><summary>{t('result.viewAIInput')}</summary><p>{aiStep.inputs_summary}</p></details>}
                  {item.id === 'decision' && typeof decisionEvent?.metadata.confidence === 'number' && <small>{t('result.confidence', { value: Math.round(decisionEvent.metadata.confidence * 100) })}</small>}
                  {(item.duration != null || (item.id === 'diagnosis' && aiInvocation?.started_at)) && <small>{item.id === 'diagnosis' && aiInvocation?.started_at ? formatTime(aiInvocation.started_at) + ' · ' : ''}{formatDuration(item.duration)}</small>}
                </div>
              </li>;
            })}
          </ol>
          {repair?.state === 'FAILED' && <p className="workspace-result-blocker"><AlertCircle size={14} aria-hidden="true" />{t('result.repairWorkflowFailed')}</p>}
          {repair?.state === 'BLOCKED' && <p className="workspace-result-blocker"><AlertCircle size={14} aria-hidden="true" />{t('result.repairWorkflowBlocked')}</p>}
        </section>

        <aside className="workspace-result-panel workspace-result-activity" aria-label={t('result.currentRunAndLogs')}>
          <header className="workspace-result-panel-heading"><div><span>{runtimeConnection === 'connected' ? t('result.live') : t('result.runContext')}</span><h4>{t('result.currentTask')}</h4></div><span className={'workspace-result-state is-' + eventTone(run.status)}>{run.status}</span></header>
          <dl className="workspace-result-context">
            <div><dt>{t('result.case')}</dt><dd>{run.nodeids[0] ?? '—'}</dd></div>
            <div><dt>{t('result.environment')}</dt><dd>{run.environment.QA_ENVIRONMENT ?? '—'} · {run.environment.QA_REGION ?? '—'}</dd></div>
            <div><dt>{t('result.browser')}</dt><dd>{run.browser}</dd></div>
            <div><dt>{t('result.started')}</dt><dd>{formatTime(run.started_at)}</dd></div>
          </dl>
          <div className="workspace-result-event-heading"><h5>{t('result.eventLog')}</h5><button type="button" className="btn btn-icon btn-sm" aria-label={t('result.viewRuntimeDetails')} title={t('result.viewRuntimeDetails')} onClick={onOpenDetails}><Workflow size={13} aria-hidden="true" /></button></div>
          <div className="workspace-result-event-filters" role="group" aria-label={t('result.filterEvents')}>
            {(['all', 'errors', 'browser', 'ai'] as const).map((filter) => <button type="button" key={filter} className={eventFilter === filter ? 'is-active' : ''} aria-pressed={eventFilter === filter} onClick={() => setEventFilter(filter)}>{t('result.eventFilters.' + filter)}</button>)}
          </div>
          {filteredEvents.length ? <ol className="workspace-result-events">
            {filteredEvents.map((event) => <EventRow key={event.id} event={event} onOpenDetails={onOpenDetails} onOpenStep={onOpenStep} t={t} />)}
          </ol> : runtimeError
            ? <p className="workspace-result-empty-inline" role="alert">{t('result.runtimeLoadError')} <button type="button" className="btn btn-secondary btn-sm" onClick={onRefreshRuntime}>{t('result.retryLoad')}</button></p>
            : <p className="workspace-result-empty-inline">{runRuntime ? t('result.noMatchingEvents') : t('result.runtimeLoading')}</p>}
          {run.log_output && <details className="workspace-result-raw-log" open={logExpanded} onToggle={(event) => setLogExpanded(event.currentTarget.open)}>
            <summary>{t('result.rawRunnerLog')} · {run.log_output.split(/\r?\n/).length} {t('result.logLines')}</summary>
            <pre>{run.log_output.slice(-12000)}</pre>
          </details>}
        </aside>
      </div>

      <details className="workspace-result-evidence">
        <summary className="workspace-result-evidence-heading"><div><span>{t('result.evidenceEyebrow')} · {run.id}</span><span className="workspace-result-evidence-title" id="workspace-evidence-title">{t('result.evidence')}</span></div><small>{t('result.evidenceCounts', { screenshots: screenshots.length, traces: traces.length, reports: reports.length })}</small></summary>
        <div className="workspace-result-evidence-grid">
          <section className="workspace-result-evidence-panel">
            <h5><ImageIcon size={14} aria-hidden="true" />{t('result.screenshots')}</h5>
            {screenshots.length ? screenshots.map((artifact) => <article className="workspace-result-artifact" key={artifact.id}><div><strong>{artifact.name}</strong><small>{formatTime(artifact.created_at)}</small></div><RuntimeArtifactActions artifact={artifact} /></article>) : <p>{t('result.noScreenshot')}</p>}
          </section>
          <section className="workspace-result-evidence-panel">
            <h5><FileCode2 size={14} aria-hidden="true" />{t('result.codeLocation')}</h5>
            {sourcePath ? <><code className="workspace-result-source-path">{sourcePath}{sourceLine ? ':' + sourceLine : ''}</code>{failedBrowserStep?.locator && <pre>{failedBrowserStep.locator}</pre>}<button type="button" className="btn btn-secondary btn-sm" onClick={() => onOpenCode(sourcePath, sourceLine)}>{t('result.openSource')}</button></> : <p>{t('result.noCodeLocation')}</p>}
          </section>
          <section className="workspace-result-evidence-panel">
            <h5><Workflow size={14} aria-hidden="true" />{t('result.repairDiff')}</h5>
            {diff ? <details className="workspace-result-diff"><summary>{t('result.openDiff')} · {proposal?.file_path ?? t('result.diffReady')}</summary><pre>{diff}</pre></details> : <p>{t('result.diffNotGenerated')}</p>}
          </section>
          <section className="workspace-result-evidence-panel">
            <h5><Activity size={14} aria-hidden="true" />{t('result.artifactsAndTrace')}</h5>
            {[...traces, ...reports, ...artifacts.filter((item) => !screenshots.includes(item) && !traces.includes(item) && !reports.includes(item))].length
              ? [...traces, ...reports, ...artifacts.filter((item) => !screenshots.includes(item) && !traces.includes(item) && !reports.includes(item))].map((artifact) => <article className="workspace-result-artifact" key={artifact.id}><div><strong>{artifact.name}</strong><small>{artifact.type} · {formatTime(artifact.created_at)}</small></div><RuntimeArtifactActions artifact={artifact} /></article>)
              : <p>{t('result.noArtifacts')}</p>}
          </section>
        </div>
        <footer className="workspace-result-evidence-footer">
            <span>{t('result.runtimeEventCount', { count: events.length })}</span>
          <span>{t('result.browserFailureCount', { count: Math.max(
            browserEvidence.filter((step) => step.status?.toUpperCase() === 'FAILED').length,
            events.filter((event) => event.category === 'browser' && event.status?.toUpperCase() === 'FAILED').length,
          ) })}</span>
          <span>{t('result.savedExecutionCount', { count: resultCount })}</span>
          {context.testCaseId && <Link to={buildWorkspaceHref({ ...context, projectId, stage: 'cases', view: 'cases' })}>{t('result.openCase')}</Link>}
        </footer>
      </details>
    </section>
  );
}

function EventRow({ event, onOpenDetails, onOpenStep, t }: {
  event: RuntimeEvent;
  onOpenDetails: () => void;
  onOpenStep: (stepId: string) => void;
  t: ReturnType<typeof useTranslation<'workspace'>>['t'];
}) {
  const tone = eventTone(event.status);
  const metadata = Object.entries(event.metadata ?? {}).filter(([, value]) => value !== null && value !== undefined && ['string', 'number', 'boolean'].includes(typeof value));
  return <li className={'workspace-result-event is-' + tone}>
    <details>
      <summary>
        <span className="workspace-result-event-dot" aria-hidden="true" />
        <time>{formatTime(event.timestamp)}</time>
        <span className="workspace-result-event-content"><strong>{event.title || event.type}</strong><small>{event.summary || event.category}</small></span>
        <span className={'workspace-result-state is-' + tone}>{event.status ?? event.category}</span>
      </summary>
      <div className="workspace-result-event-detail"><code>{event.type}</code>{event.duration_ms != null && <small>{formatDuration(event.duration_ms)}</small>}
        {metadata.length > 0 && <dl>{metadata.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>}
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => event.step_id ? onOpenStep(event.step_id) : onOpenDetails()}>{event.step_id ? t('result.openRelatedStep') : t('result.openRuntimeEvidence')}</button>
      </div>
    </details>
  </li>;
}
