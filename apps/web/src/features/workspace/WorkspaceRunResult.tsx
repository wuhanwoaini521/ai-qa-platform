import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Activity, AlertCircle, Bot, Check, Circle, FileCode2, Maximize2, RefreshCw, Square, Workflow } from 'lucide-react';
import { api } from '../../api/client';
import type { AITraceEvent, FailureRecord, FailureRepairWorkflow, LocatorRepairProposal, TestCase, TestRun } from '../../types';
import type { RuntimeArtifact, RuntimeEvent, RuntimeSnapshot } from '../../types/runtime';
import type { WorkspaceContext } from '../../app/workspaceContext';
import { failedLocatorFromFailure, failureSourceLocation, normalizeFailureClassification, observedRoleLocatorMismatch, summarizeFailureError } from '../failures/failureWorkspaceModel';
import { ANALYSIS_TERMINAL_EVENT_TYPES, analysisStageStatus, terminalAnalysisMessage } from './analysisLifecycleModel';
import { RuntimeArtifactActions } from '../runtime/RuntimeArtifactActions';
import { NetworkEvidenceList } from '../runtime/NetworkEvidenceList';
import { resolveExecutionCase } from '../runs/testExecutionResultsModel';

type EventFilter = 'all' | 'errors' | 'browser' | 'ai';
type EvidenceTab = 'screenshot' | 'snapshot' | 'dom' | 'trace' | 'console' | 'network' | 'source';
type CaseFilter = 'all' | 'failed' | 'passed' | 'skipped';
type ResultPanel = 'cases' | 'detail' | 'repair' | 'context';
type CorrelatedArtifact = RuntimeArtifact & { metadata_json?: Record<string, unknown> };

interface WorkspaceRunResultProps {
  context: WorkspaceContext;
  run: TestRun;
  testCases: TestCase[];
  runtime: RuntimeSnapshot | null;
  runtimeConnection: string;
  runtimeError: string;
  onRefreshRuntime: () => void;
  projectId: string;
  onOpenCode: (filePath: string, lineNumber?: number) => void;
  onOpenDetails: () => void;
  onOpenStep: (stepId: string) => void;
  onStop: () => void;
  onRerun: () => void;
  onManualAnalysis: () => void;
  onSelectExecution: (nodeId: string, caseId: string | null) => void;
}

function runArtifacts(run: TestRun, runtime: RuntimeSnapshot | null): CorrelatedArtifact[] {
  const external = (run.external_artifacts ?? []).map((item): CorrelatedArtifact => ({
    id: item.id,
    artifact_id: typeof item.metadata_json.artifact_id === 'string' ? item.metadata_json.artifact_id : null,
    name: item.name,
    type: item.type,
    source: 'run',
    step_id: null,
    test_run_id: run.id,
    case_id: null,
    created_at: item.created_at,
    size_bytes: null,
    content_type: typeof item.metadata_json.content_type === 'string' ? item.metadata_json.content_type : null,
    url: item.url,
    metadata_json: item.metadata_json,
  }));
  const externalIds = new Set(external.map((item) => item.artifact_id).filter(Boolean));
  const runtimeItems = runtime?.artifacts.filter((item) =>
    item.test_run_id === run.id && (!item.artifact_id || !externalIds.has(item.artifact_id)),
  ) ?? [];
  return [...external, ...runtimeItems];
}

function eventTone(status?: string | null): string {
  const normalized = (status ?? '').toUpperCase();
  if (['FAILED', 'ERROR', 'BLOCKED'].includes(normalized)) return 'failed';
  if (['RUNNING', 'QUEUED', 'WAITING', 'WAITING_APPROVAL', 'WAITING_FOR_APPROVAL'].includes(normalized)) return 'running';
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

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

// Events that end an analysis with a user-visible reason. The analysis runner writes exactly one of
// them, so the message it carries is the authoritative explanation of why the run stopped.
function displayEvidence(value: unknown): string {
  if (typeof value === 'string') return value;
  try { return JSON.stringify(value, null, 2); } catch { return String(value); }
}

function executionState(status: string): CaseFilter | 'other' {
  if (['FAILED', 'ERROR'].includes(status.toUpperCase())) return 'failed';
  if (status.toUpperCase() === 'PASSED') return 'passed';
  if (status.toUpperCase() === 'SKIPPED') return 'skipped';
  return 'other';
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
  onOpenCode,
  onOpenDetails,
  onOpenStep,
  onStop,
  onRerun,
  onManualAnalysis,
  onSelectExecution,
}: WorkspaceRunResultProps) {
  const { t, i18n } = useTranslation('workspace');
  const { t: tFailures } = useTranslation('failures');
  const initialNodeId = context.nodeId && run.executions.some((item) => item.nodeid === context.nodeId)
    ? context.nodeId
    : run.executions.find((item) => executionState(item.status) === 'failed')?.nodeid ?? run.executions[0]?.nodeid ?? '';
  const [selectedNodeId, setSelectedNodeId] = useState(initialNodeId);
  const [activePanel, setActivePanel] = useState<ResultPanel>('detail');
  const [caseFilter, setCaseFilter] = useState<CaseFilter>('all');
  const [evidenceTab, setEvidenceTab] = useState<EvidenceTab>('screenshot');
  const [eventFilter, setEventFilter] = useState<EventFilter>('all');
  const [failure, setFailure] = useState<FailureRecord | null>(null);
  const [failureLoadState, setFailureLoadState] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [failureRefresh, setFailureRefresh] = useState(0);
  const [repair, setRepair] = useState<FailureRepairWorkflow | null>(null);
  const [repairHistoryLoading, setRepairHistoryLoading] = useState(false);
  const [repairHistoryError, setRepairHistoryError] = useState('');
  const [verificationRun, setVerificationRun] = useState<TestRun | null>(null);
  const [diagnosis, setDiagnosis] = useState<Record<string, unknown> | null>(null);
  const [analysisEvents, setAnalysisEvents] = useState<AITraceEvent[]>([]);
  const [analysisId, setAnalysisId] = useState('');
  const [analysisRunning, setAnalysisRunning] = useState(false);
  const [analysisStatus, setAnalysisStatus] = useState('');
  const [analysisError, setAnalysisError] = useState('');
  const [actionError, setActionError] = useState('');
  const [actionRunning, setActionRunning] = useState(false);
  const [providerConfig, setProviderConfig] = useState<Awaited<ReturnType<typeof api.getAIProviderSettings>> | null>(null);
  const [jevConfig, setJevConfig] = useState<Awaited<ReturnType<typeof api.getJevSettings>> | null>(null);
  const [configurationUnavailable, setConfigurationUnavailable] = useState(false);
  const analysisController = useRef<AbortController | null>(null);
  const focusOnPanelCard = (panel: ResultPanel) => (event: MouseEvent<HTMLElement>) => {
    if (event.target instanceof Element && event.target.closest('button, a, input, select, textarea, summary')) return;
    setActivePanel(panel);
  };

  const runRuntime = runtime?.kind === 'run' && runtime.id === run.id ? runtime : null;
  const runtimeReady = Boolean(runRuntime);
  const selectedExecution = run.executions.find((item) => item.nodeid === selectedNodeId) ?? run.executions[0] ?? null;
  const selectedIdentity = selectedExecution ? resolveExecutionCase(selectedExecution.nodeid, testCases) : null;
  const runtimeFailure = selectedExecution
    ? runRuntime?.failures.find((item) => item.test_run_id === run.id && item.execution_id === selectedExecution.id) ?? null
    : null;
  const hasFailures = run.executions.some((item) => executionState(item.status) === 'failed');
  const focusedPanel = activePanel === 'repair' && !hasFailures ? 'detail' : activePanel;
  const isRunActive = ['RUNNING', 'QUEUED'].includes(run.status);
  const events = (runRuntime?.events ?? []).filter((event) => event.test_run_id === run.id);
  const artifacts = useMemo(() => runArtifacts(run, runRuntime), [run, runRuntime]);
  const browserSession = run.browser_sessions?.find((item) => item.nodeid === selectedExecution?.nodeid) ?? null;
  const pageEvidence = browserSession?.page_evidence ?? {};
  const nodeName = selectedExecution?.nodeid.split('::').at(-1) ?? '';
  const nodeFile = selectedExecution?.nodeid.split('::')[0] ?? '';
  const selectedArtifacts = useMemo(() => {
    if (!selectedExecution) return [];
    const sessionId = browserSession?.browser_session_id;
    const expectedNames = new Set((selectedExecution.artifact_paths ?? []).map((path) => path.split(/[\\/]/).at(-1)?.toLowerCase()));
    return artifacts.filter((item) => {
      const metadata = item.metadata_json ?? {};
      const artifactSession = metadata.browser_session_id;
      const name = item.name.split(/[\\/]/).at(-1)?.toLowerCase() ?? '';
      return (Boolean(sessionId) && artifactSession === sessionId)
        || name === nodeName.toLowerCase() + '.png'
        || name === nodeName.toLowerCase() + '.zip'
        || name === nodeName.toLowerCase() + '.html'
        || expectedNames.has(name)
        || Boolean(selectedIdentity?.caseId && item.case_id === selectedIdentity.caseId);
    });
  }, [artifacts, browserSession?.browser_session_id, nodeName, selectedExecution, selectedIdentity?.caseId]);
  const screenshots = selectedArtifacts.filter((item) => item.type.toUpperCase().includes('SCREENSHOT') || item.content_type?.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(item.name));
  const traces = selectedArtifacts.filter((item) => item.type.toUpperCase().includes('TRACE') || /\.zip$/i.test(item.name));
  const domArtifacts = selectedArtifacts.filter((item) => /dom|snapshot/i.test(item.type + ' ' + item.name) && !item.type.toUpperCase().includes('SCREENSHOT'));
  const locator = failure ? failure.failing_locator || failedLocatorFromFailure(failure) : '';
  const source = failure ? failureSourceLocation(failure) : null;
  const selectedSteps = Array.isArray(pageEvidence.recent_steps) ? pageEvidence.recent_steps.map(asRecord).filter(Boolean) : [];
  const failedStep = [...selectedSteps].reverse().find((item) => String(item?.status ?? '').toUpperCase() === 'FAILED');
  const sourcePath = source?.filePath ?? (typeof failedStep?.file === 'string' ? failedStep.file : nodeFile || null);
  const sourceLine = source?.lineNumber ?? (typeof failedStep?.line === 'number' ? failedStep.line : undefined);
  const selectedEvents = useMemo(() => {
    const linked = events.filter((event) => String(event.metadata.nodeid ?? event.metadata.test_nodeid ?? '') === selectedExecution?.nodeid);
    return linked.length ? linked : [...events].sort((a, b) => {
      const aError = ['FAILED', 'ERROR', 'BLOCKED'].includes((a.status ?? '').toUpperCase()) ? 1 : 0;
      const bError = ['FAILED', 'ERROR', 'BLOCKED'].includes((b.status ?? '').toUpperCase()) ? 1 : 0;
      return bError - aError;
    });
  }, [events, selectedExecution?.nodeid]);
  const filteredEvents = selectedEvents.filter((event) => {
    if (eventFilter === 'errors') return ['FAILED', 'ERROR', 'BLOCKED'].includes((event.status ?? '').toUpperCase()) || event.category === 'failure';
    if (eventFilter === 'browser') return event.category === 'browser';
    if (eventFilter === 'ai') return event.category === 'ai' || event.category === 'decision';
    return true;
  });
  const eventAssociationIsExact = selectedEvents.some((event) => String(event.metadata.nodeid ?? event.metadata.test_nodeid ?? '') === selectedExecution?.nodeid);
  const aiEvent = [...analysisEvents].reverse().find((item) => item.type.startsWith('model.') || item.stage === 'diagnosis');
  const jevEvent = [...analysisEvents].reverse().find((item) =>
    item.stage === 'decision' || String(item.metadata.provider ?? '').toLowerCase() === 'jev',
  );
  const proposal = (repair?.repair_proposal ?? failure?.repair_proposal ?? null) as LocatorRepairProposal | null;
  const codeDiff = proposal?.code_diff ?? null;
  const jevCalled = Boolean(jevEvent || proposal?.provider?.toLowerCase() === 'jev');
  const aiProviderLabel = aiEvent?.metadata.provider
    ? [String(aiEvent.metadata.provider), aiEvent.metadata.model ? String(aiEvent.metadata.model) : ''].filter(Boolean).join(' · ')
    : diagnosis?.provider
      ? [String(diagnosis.provider), typeof diagnosis.model === 'string' ? diagnosis.model : ''].filter(Boolean).join(' · ')
      : providerConfig
        ? [providerConfig.provider, providerConfig.model].filter(Boolean).join(' · ')
        : configurationUnavailable ? t('result.configUnavailable') : t('result.configLoading');
  const caseRows = useMemo(() => run.executions.map((execution) => ({
    execution,
    identity: resolveExecutionCase(execution.nodeid, testCases),
  })).sort((a, b) => {
    const order: Record<CaseFilter | 'other', number> = { failed: 0, other: 1, passed: 2, skipped: 3, all: 4 };
    const rank = (value: string) => order[executionState(value)];
    return rank(a.execution.status) - rank(b.execution.status);
  }), [run.executions, testCases]);
  const filteredCases = caseRows.filter(({ execution }) => caseFilter === 'all' || executionState(execution.status) === caseFilter);
  const counts = {
    total: run.executions.length,
    passed: run.executions.filter((item) => executionState(item.status) === 'passed').length,
    failed: run.executions.filter((item) => executionState(item.status) === 'failed').length,
    skipped: run.executions.filter((item) => executionState(item.status) === 'skipped').length,
  };
  const isSelectedError = selectedExecution ? executionState(selectedExecution.status) === 'failed' : false;
  const diagnosisRootCause = typeof diagnosis?.root_cause === 'string' ? diagnosis.root_cause : '';
  const diagnosisEvidence = Array.isArray(diagnosis?.evidence) ? diagnosis.evidence.filter((value): value is string => typeof value === 'string') : [];
  const repairState = repair?.state ?? null;
  const analysisCancelled = !analysisRunning && analysisStatus === 'CANCELLED';
  const canRestartAnalysis = repair?.allowed_actions.includes('START_ANALYSIS') === true
    || Boolean(!repair && analysisId && analysisError && !repairHistoryError);
  const canStartInitialAnalysis = !repair && !analysisId && !repairHistoryLoading && !repairHistoryError;
  const canStartAnalysis = canRestartAnalysis || canStartInitialAnalysis;
  const canApplyPatch = Boolean(failure && analysisId && proposal && repair?.allowed_actions.includes('APPLY'));
  const canVerifyPatch = Boolean(failure && analysisId && repair?.allowed_actions.includes('VERIFY'));
  const canRollbackPatch = Boolean(failure && analysisId && repair?.allowed_actions.includes('ROLLBACK'));
  const workflowStages = [
    { id: 'evidence', label: t('result.repairStages.evidence'), status: failure ? 'SUCCEEDED' : failureLoadState === 'loading' ? 'PENDING' : 'UNAVAILABLE', detail: failure ? t('result.caseEvidenceReady', { count: selectedArtifacts.length }) : t('result.caseEvidenceUnavailable') },
    { id: 'diagnosis', label: t('result.repairStages.diagnosis'), status: analysisStageStatus({ running: analysisRunning, cancelled: analysisCancelled, error: analysisError, succeeded: Boolean(diagnosisRootCause) }), detail: diagnosisRootCause || analysisError || (analysisEvents.length ? aiEvent?.message ?? '' : t('result.aiNotStarted')) },
    { id: 'decision', label: t('result.repairStages.decision'), status: jevCalled ? jevEvent?.status ?? 'SUCCEEDED' : analysisRunning ? 'RUNNING' : 'NOT_CALLED', detail: jevCalled ? jevEvent?.message ?? t('result.jevActuallyCalled') : analysisError ? t('result.jevNotReached') : jevConfig?.enabled ? t('result.jevEnabledNotCalled') : jevConfig ? t('result.jevDisabled') : t('result.configUnavailable') },
    { id: 'patch', label: t('result.repairStages.patch'), status: codeDiff ? 'SUCCEEDED' : repairState === 'BLOCKED' ? 'BLOCKED' : repairState === 'NOT_APPLICABLE' ? 'SKIPPED' : analysisError && !analysisCancelled ? 'FAILED' : 'NOT_STARTED', detail: codeDiff ? proposal?.file_path ?? t('result.diffReady') : repairState === 'BLOCKED' ? t('result.repairWorkflowBlocked') : repairState === 'NOT_APPLICABLE' ? t('result.repairNotApplicable') : t('result.diffNotGenerated') },
    { id: 'apply', label: t('result.repairStages.apply'), status: repairState === 'APPLYING' ? 'RUNNING' : repairState === 'ROLLED_BACK' ? 'ROLLED_BACK' : proposal?.applied || ['PATCH_APPLIED', 'VERIFYING_FIX', 'VERIFIED'].includes(repairState ?? '') ? 'SUCCEEDED' : canApplyPatch ? 'WAITING_APPROVAL' : repairState === 'BLOCKED' ? 'BLOCKED' : repairState === 'NOT_APPLICABLE' ? 'SKIPPED' : 'NOT_STARTED', detail: canApplyPatch ? t('result.patchApprovalPending') : repair?.repair_id ?? t('result.patchNotApplied') },
    { id: 'verify', label: t('result.repairStages.verify'), status: repairState === 'VERIFYING_FIX' ? 'RUNNING' : repair?.verified || repairState === 'VERIFIED' ? 'SUCCEEDED' : ['FAILED', 'ERROR', 'CANCELLED'].includes(repair?.verification_run_status ?? '') ? repair?.verification_run_status ?? 'FAILED' : canVerifyPatch ? 'WAITING' : repairState === 'BLOCKED' ? 'BLOCKED' : repairState === 'NOT_APPLICABLE' ? 'SKIPPED' : 'NOT_STARTED', detail: canVerifyPatch ? t('result.verificationReady') : repair?.verification_run_id ?? t('result.verificationNotStarted') },
  ];

  useEffect(() => {
    if (context.nodeId && run.executions.some((item) => item.nodeid === context.nodeId)) setSelectedNodeId(context.nodeId);
  }, [context.nodeId, run.executions]);

  useEffect(() => {
    let active = true;
    analysisController.current?.abort();
    setFailure(null);
    setRepair(null);
    setVerificationRun(null);
    setRepairHistoryError('');
    setDiagnosis(null);
    setAnalysisEvents([]);
    setAnalysisId('');
    setAnalysisError('');
    setActionError('');
    if (!isSelectedError) {
      setFailureLoadState('loaded');
      return () => { active = false; };
    }
    if (!runtimeReady) {
      setFailureLoadState(runtimeError ? 'error' : 'loading');
      return () => { active = false; };
    }
    if (!runtimeFailure) {
      setFailureLoadState('loaded');
      return () => { active = false; };
    }
    setFailureLoadState('loading');
    void api.getFailure(runtimeFailure.id).then((item) => {
      if (!active) return;
      if (item.run_id !== run.id || item.execution_id !== selectedExecution?.id) throw new Error('Failure record does not belong to the selected execution');
      setFailure(item);
      setFailureLoadState('loaded');
    }).catch(() => {
      if (active) {
        setFailure(null);
        setFailureLoadState('error');
      }
    });
    return () => { active = false; };
  }, [projectId, run.id, runtimeReady, runtimeError, runtimeFailure?.id, selectedExecution?.id, isSelectedError, failureRefresh]);

  useEffect(() => {
    if (!failure) {
      setRepairHistoryLoading(false);
      setRepairHistoryError('');
      return;
    }
    let active = true;
    setRepairHistoryLoading(true);
    setRepairHistoryError('');
    void loadLatestAnalysis(failure.id, { follow: true, isActive: () => active }).catch((error) => {
      if (active) setRepairHistoryError(error instanceof Error ? error.message : String(error));
    }).finally(() => { if (active) setRepairHistoryLoading(false); });
    return () => { active = false; };
  }, [failure?.id]);

  useEffect(() => {
    let active = true;
    void Promise.all([api.getAIProviderSettings(), api.getJevSettings()]).then(([provider, jev]) => {
      if (!active) return;
      setProviderConfig(provider);
      setJevConfig(jev);
      setConfigurationUnavailable(false);
    }).catch(() => { if (active) setConfigurationUnavailable(true); });
    return () => { active = false; };
  }, []);

  useEffect(() => () => analysisController.current?.abort(), []);

  const verificationId = verificationRun?.id ?? repair?.verification_run_id ?? null;
  const verificationPending = repair?.state === 'VERIFYING_FIX'
    || ['QUEUED', 'RUNNING'].includes(verificationRun?.status ?? repair?.verification_run_status ?? '');
  useEffect(() => {
    if (!failure || !analysisId || !verificationId) return;
    let active = true;
    const refreshVerification = async () => {
      try {
        const [nextRun, nextWorkflow] = await Promise.all([
          api.getTestRun(verificationId),
          api.getFailureRepairWorkflow(failure.id, analysisId),
        ]);
        if (!active) return;
        setVerificationRun(nextRun);
        setRepair(nextWorkflow);
      } catch (error) {
        if (active) setActionError(error instanceof Error ? error.message : String(error));
      }
    };
    void refreshVerification();
    if (!verificationPending) return () => { active = false; };
    const timer = window.setInterval(() => void refreshVerification(), 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [failure?.id, analysisId, verificationId, verificationPending]);

  const selectExecution = (nodeId: string, caseId: string | null) => {
    setSelectedNodeId(nodeId);
    setEvidenceTab('screenshot');
    setActivePanel('detail');
    onSelectExecution(nodeId, caseId);
  };

  const followAnalysis = async (controller: AbortController, failureId: string, reset: boolean) => {
    if (reset) {
      setAnalysisError('');
      setDiagnosis(null);
      setRepair(null);
      setAnalysisEvents([]);
      setAnalysisId('');
      setActionError('');
      setRepairHistoryError('');
    }
    setAnalysisRunning(true);
    let streamedAnalysisId = '';
    try {
      await api.streamFailureWorkflow(failureId, (event) => {
        if (controller.signal.aborted) return;
        // Re-attaching replays the persisted events, so a reload must not show them twice.
        setAnalysisEvents((previous) => previous.some((item) => item.event_id === event.event_id) ? previous : [...previous, event]);
        const eventDiagnosis = asRecord(event.metadata.diagnosis);
        if (eventDiagnosis) setDiagnosis(eventDiagnosis);
        if (typeof event.metadata.analysis_id === 'string') {
          streamedAnalysisId = event.metadata.analysis_id;
          setAnalysisId(event.metadata.analysis_id);
        }
        const eventProposal = asRecord(event.metadata.repair_proposal);
        if (eventProposal) setRepair((current) => current ? { ...current, repair_proposal: eventProposal as LocatorRepairProposal } : current);
        if (ANALYSIS_TERMINAL_EVENT_TYPES.includes(event.type)) {
          setAnalysisError(event.message || (event.type === 'run.failed' ? t('result.aiAnalysisFailed') : tFailures('diagnosisStreamIncomplete')));
        }
      }, controller.signal, i18n.resolvedLanguage ?? i18n.language);
      if (!controller.signal.aborted) await loadLatestAnalysis(failureId, { preferredId: streamedAnalysisId });
    } catch (error) {
      if (!controller.signal.aborted) setAnalysisError(error instanceof Error ? error.message : String(error));
    } finally {
      if (analysisController.current === controller) {
        analysisController.current = null;
        setAnalysisRunning(false);
      }
    }
  };

  const loadLatestAnalysis = async (
    failureId: string,
    options: { preferredId?: string; follow?: boolean; isActive?: () => boolean } = {},
  ) => {
    const rows = await api.getFailureAnalyses(failureId);
    if (options.isActive && !options.isActive()) return;
    const analysis = (options.preferredId ? rows.find((item) => item.id === options.preferredId) : undefined)
      ?? [...rows].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
    if (!analysis) return;
    setAnalysisId(analysis.id);
    setAnalysisStatus(analysis.status);
    setAnalysisEvents(analysis.events);
    setDiagnosis(asRecord(analysis.result.diagnosis));
    setAnalysisError(terminalAnalysisMessage(analysis, t('result.aiAnalysisFailed'), tFailures('diagnosisStreamIncomplete')));
    const workflow = await api.getFailureRepairWorkflow(failureId, analysis.id);
    if (options.isActive && !options.isActive()) return;
    setRepair(workflow);
    // A reload must never look like "not started": a persisted RUNNING analysis is followed, not restarted.
    if (options.follow && analysis.status === 'RUNNING') attachToAnalysis(failureId);
  };

  const attachToAnalysis = (failureId: string) => {
    if (analysisController.current) return;
    const controller = new AbortController();
    analysisController.current = controller;
    void followAnalysis(controller, failureId, false);
  };

  const startAnalysis = async () => {
    if (!failure || analysisRunning) return;
    analysisController.current?.abort();
    const controller = new AbortController();
    analysisController.current = controller;
    await followAnalysis(controller, failure.id, true);
  };

  const cancelAnalysis = async () => {
    if (!failure || !analysisId) return;
    setActionError('');
    try {
      // Cancel owns the run server-side; stop following only after the record is terminal.
      setRepair(await api.cancelFailureAnalysis(failure.id, analysisId));
      analysisController.current?.abort();
      analysisController.current = null;
      setAnalysisRunning(false);
      await loadLatestAnalysis(failure.id, { preferredId: analysisId });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const applyPatch = async () => {
    if (!failure || !analysisId || !proposal || !repair?.allowed_actions.includes('APPLY')) return;
    const oldCode = proposal.source_locator || proposal.old_locator || '';
    const newCode = proposal.proposed_locator || '';
    if (!oldCode || !newCode || oldCode.trim() === newCode.trim()) {
      setActionError(t('result.patchNotApplicable'));
      return;
    }
    setActionRunning(true);
    setActionError('');
    try {
      const result = await api.applyRepair(failure.id, analysisId, {
        file_path: proposal.file_path || failure.test_nodeid.split('::')[0],
        old_code: oldCode,
        new_code: newCode,
      });
      setRepair(result.repair);
      setFailure(await api.getFailure(failure.id));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setActionRunning(false);
    }
  };

  const verifyPatch = async () => {
    if (!failure || !analysisId || !repair?.allowed_actions.includes('VERIFY')) return;
    setActionRunning(true);
    setActionError('');
    try {
      const startedRun = await api.startFailureVerification(failure.id, analysisId);
      setVerificationRun(startedRun);
      const refreshedWorkflow = await api.getFailureRepairWorkflow(failure.id, analysisId);
      setRepair(refreshedWorkflow);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setActionRunning(false);
    }
  };

  const retryFailure = () => {
    setFailureLoadState('loading');
    setFailureRefresh((value) => value + 1);
    onRefreshRuntime();
  };

  const stageLabel = (status: string) => t('result.stageState.' + status, { defaultValue: status.replaceAll('_', ' ') });
  const statusMessage = selectedExecution
    ? executionState(selectedExecution.status) === 'failed'
      ? (failure?.error_message || selectedExecution.error_message || t('result.failureLoading'))
      : executionState(selectedExecution.status) === 'passed'
        ? t('result.selectedCasePassed')
        : executionState(selectedExecution.status) === 'skipped'
          ? t('result.selectedCaseSkipped')
          : t('result.selectedCaseInProgress')
    : t('result.caseExecutionResults.empty');
  const failureKind = failure
    ? observedRoleLocatorMismatch(failure) || summarizeFailureError(failure.error_message, failure.classification) === 'locatorTimeout'
      ? 'LOCATOR_CHANGED'
      : normalizeFailureClassification(failure.classification)
    : null;
  const failureTypeLabel = failureKind ? t(`result.failureTypes.${failureKind}`, { defaultValue: failureKind.replaceAll('_', ' ') }) : '';
  const errorLines = Array.isArray(pageEvidence.console_logs) ? pageEvidence.console_logs : failure?.console_logs ?? [];
  const networkLines = Array.isArray(pageEvidence.network_logs) ? pageEvidence.network_logs : [];
  const controls = Array.isArray(pageEvidence.controls) ? pageEvidence.controls : [];
  const domPathArtifact = failure?.dom_snapshot_path
    ? selectedArtifacts.find((item) => item.name.split(/[\\/]/).at(-1) === failure.dom_snapshot_path?.split(/[\\/]/).at(-1))
    : domArtifacts[0];

  return (
    <section className="workspace-result-surface workspace-result-v2" aria-label={t('result.runResult')}>
      <header className="workspace-result-overview">
        <div className="workspace-result-overview-title">
          <div><span className="workspace-eyebrow">{t('result.overviewEyebrow')}</span><h2>{t('result.runTitle')} <code>{run.id}</code></h2></div>
          <span className={'workspace-result-badge is-' + run.status.toLowerCase()}>{t('result.runStatus.' + run.status, { defaultValue: run.status })}</span>
          <div className="workspace-result-overview-actions">
            <details className="workspace-plan-disclosure"><summary>{t('result.viewExecutionPlan')}</summary><div><p>{t('result.planDisclosureDescription')}</p><button type="button" className="btn btn-secondary btn-sm" onClick={onManualAnalysis}>{t('result.openExecutionPlan')}</button></div></details>
            <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenDetails}><Workflow size={14} aria-hidden="true" />{t('result.fullRuntime')}</button>
            {isRunActive ? <button type="button" className="btn btn-danger btn-sm" onClick={onStop}><Square size={13} aria-hidden="true" />{t('dock.stop')}</button> : <button type="button" className="btn btn-primary btn-sm" onClick={onRerun} disabled={!selectedExecution}><RefreshCw size={14} aria-hidden="true" />{t('result.rerun')}</button>}
          </div>
        </div>
        <dl className="workspace-result-summary-stats">
          <div><dt>{t('result.total')}</dt><dd>{counts.total}</dd></div>
          <div className="is-passed"><dt>{t('result.passed')}</dt><dd>{counts.passed}</dd></div>
          <div className="is-failed"><dt>{t('result.failed')}</dt><dd>{counts.failed}</dd></div>
          <div><dt>{t('result.skipped')}</dt><dd>{counts.skipped}</dd></div>
          <div><dt>{t('result.duration')}</dt><dd>{formatDuration(run.duration_ms)}</dd></div>
          <div className="workspace-result-overview-meta"><dt>{t('result.environment')} · {t('result.browser')} · {t('result.started')}</dt><dd>{[run.environment.QA_ENVIRONMENT, run.environment.QA_REGION, run.browser, formatTime(run.started_at)].filter(Boolean).join(' · ')}</dd></div>
        </dl>
      </header>

      <div className={`workspace-result-workspace ${hasFailures ? 'has-repair-panel ' : ''}is-focus-${focusedPanel}`}>
        <nav onClickCapture={focusOnPanelCard('cases')} className={`workspace-result-card workspace-case-navigator ${focusedPanel === 'cases' ? 'is-focused' : 'is-compact'}`} aria-label={t('result.caseExecutionResults.title')}>
          <header><div><span className="workspace-eyebrow" title={t('result.caseExecutionResults.title')}>{t('result.caseExecutionResults.title')}</span><strong>{counts.total}</strong></div><div className="workspace-panel-header-actions"><button type="button" className="btn btn-icon btn-sm" aria-label={t('result.fullRuntime')} title={t('result.fullRuntime')} onClick={onOpenDetails}><Workflow size={14} /></button><button type="button" className="btn btn-icon btn-sm workspace-panel-focus" aria-pressed={focusedPanel === 'cases'} aria-label={t('result.focusPanel', { panel: t('result.caseExecutionResults.title') })} title={t('result.focusPanel', { panel: t('result.caseExecutionResults.title') })} onClick={() => setActivePanel('cases')}><Maximize2 size={14} aria-hidden="true" /></button></div></header>
          <div className="workspace-case-filters" role="group" aria-label={t('result.filterCases')}>
            {(['all', 'failed', 'passed', 'skipped'] as const).map((filter) => {
              const count = filter === 'all' ? counts.total : counts[filter];
              return <button key={filter} type="button" aria-pressed={caseFilter === filter} className={caseFilter === filter ? 'is-active' : ''} onClick={() => {
                setCaseFilter(filter);
                if (filter !== 'all' && executionState(selectedExecution?.status ?? '') !== filter) {
                  const firstVisible = caseRows.find(({ execution }) => executionState(execution.status) === filter);
                  if (firstVisible) selectExecution(firstVisible.execution.nodeid, firstVisible.identity.caseId);
                }
              }}>{t('result.caseFilters.' + filter)} <b>{count}</b></button>;
            })}
          </div>
          {filteredCases.length ? <ol className="workspace-case-list">
            {filteredCases.map(({ execution, identity }) => {
              const status = execution.status.toLowerCase();
              const selected = selectedExecution?.id === execution.id;
              const Icon = status === 'passed' ? Check : ['failed', 'error'].includes(status) ? AlertCircle : Circle;
              return <li key={execution.id}><button type="button" title={`${identity.displayId ? identity.displayId + ' · ' : ''}${identity.title}\n${execution.nodeid}`} aria-current={selected ? 'true' : undefined} className={`${selected ? 'is-selected ' : ''}is-${status}`} onClick={() => selectExecution(execution.nodeid, identity.caseId)}>
                <Icon size={15} aria-hidden="true" /><span><strong>{identity.displayId ? identity.displayId + ' · ' : ''}{identity.title}</strong><small>{execution.nodeid}</small></span><time>{formatDuration(execution.duration_ms)}</time>
              </button></li>;
            })}
          </ol> : <p className="workspace-muted">{t('result.noCasesForFilter')}</p>}
        </nav>

        <main onClickCapture={focusOnPanelCard('detail')} className={`workspace-result-card workspace-case-detail ${focusedPanel === 'detail' ? 'is-focused' : 'is-compact'}`}>
          {selectedExecution && selectedIdentity ? <>
            <header className="workspace-case-detail-heading">
              <div><span className="workspace-eyebrow">{selectedIdentity.displayId ?? t('result.case')}</span><h3 title={selectedIdentity.title}>{selectedIdentity.title}</h3><code>{selectedExecution.nodeid} · {selectedExecution.id}</code></div>
              <div className="workspace-panel-header-actions"><span className={'workspace-case-status is-' + selectedExecution.status.toLowerCase()}>{t('result.runStatus.' + selectedExecution.status, { defaultValue: selectedExecution.status })} · {formatDuration(selectedExecution.duration_ms)}</span><button type="button" className="btn btn-icon btn-sm workspace-panel-focus" aria-pressed={focusedPanel === 'detail'} aria-label={t('result.focusPanel', { panel: t('result.evidence') })} title={t('result.focusPanel', { panel: t('result.evidence') })} onClick={() => setActivePanel('detail')}><Maximize2 size={14} aria-hidden="true" /></button></div>
            </header>
            {isSelectedError ? <section className="workspace-case-error" role={failure ? 'alert' : 'status'}>
              <div><strong>{failure?.exception_type || failureTypeLabel || t('result.failureLoading')}</strong>{locator && <code>{locator}</code>}</div>
              <p>{statusMessage}</p>
              {failure?.stack_trace && <details><summary>{tFailures('viewFullStack')}</summary><pre>{failure.stack_trace}</pre></details>}
              {!failure && failureLoadState === 'error' && <button type="button" className="btn btn-secondary btn-sm" onClick={retryFailure}>{t('result.retryLoad')}</button>}
            </section> : <p className={'workspace-case-outcome is-' + selectedExecution.status.toLowerCase()}>{statusMessage}</p>}

            <div className="workspace-evidence-tabs" role="tablist" aria-label={t('result.evidence')}>
              {(['screenshot', 'snapshot', 'dom', 'trace', 'console', 'network', 'source'] as const).map((tab) => <button key={tab} type="button" role="tab" aria-selected={evidenceTab === tab} className={evidenceTab === tab ? 'is-active' : ''} onClick={() => setEvidenceTab(tab)}>{t('result.evidenceTabs.' + tab)}</button>)}
            </div>
            <section className="workspace-evidence-content" role="tabpanel" aria-label={t('result.evidenceTabs.' + evidenceTab)}>
              {evidenceTab === 'screenshot' && (screenshots.length ? <div className="workspace-evidence-artifacts">{screenshots.map((item, index) => <article key={item.id}><strong>{item.name}</strong><RuntimeArtifactActions artifact={item} autoPreview={index === 0} /></article>)}</div> : <p className="workspace-evidence-missing">{t('result.evidenceMissing.screenshot')}</p>)}
              {evidenceTab === 'snapshot' && (browserSession ? <div className="workspace-evidence-snapshot"><dl>{typeof pageEvidence.title === 'string' && <div><dt>{t('result.pageTitle')}</dt><dd>{pageEvidence.title}</dd></div>}{typeof pageEvidence.url === 'string' && <div><dt>URL</dt><dd>{pageEvidence.url}</dd></div>}</dl>{selectedSteps.length ? <ol>{selectedSteps.map((step, index) => <li key={index}>{displayEvidence(step)}</li>)}</ol> : <p>{t('result.evidenceMissing.snapshotSteps')}</p>}</div> : <p className="workspace-evidence-missing">{t('result.evidenceMissing.snapshot')}</p>)}
              {evidenceTab === 'dom' && (domPathArtifact ? <RuntimeArtifactActions artifact={domPathArtifact} /> : controls.length ? <><p className="workspace-evidence-missing">{t('result.evidenceMissing.fullDom')}</p><pre>{controls.map(displayEvidence).join('\n')}</pre></> : <p className="workspace-evidence-missing">{t('result.evidenceMissing.dom')}</p>)}
              {evidenceTab === 'trace' && (traces.length ? <div className="workspace-evidence-artifacts">{traces.map((item) => <article key={item.id}><strong>{item.name}</strong><RuntimeArtifactActions artifact={item} /></article>)}</div> : <p className="workspace-evidence-missing">{t('result.evidenceMissing.trace')}</p>)}
              {evidenceTab === 'console' && (errorLines.length ? <pre>{errorLines.map(displayEvidence).join('\n')}</pre> : <p className="workspace-evidence-missing">{t('result.evidenceMissing.console')}</p>)}
              {evidenceTab === 'network' && (networkLines.length ? <NetworkEvidenceList entries={networkLines} /> : <p className="workspace-evidence-missing">{t('result.evidenceMissing.network')}</p>)}
              {evidenceTab === 'source' && (sourcePath ? <div className="workspace-evidence-source"><FileCode2 size={18} aria-hidden="true" /><code>{sourcePath}{sourceLine ? ':' + sourceLine : ''}</code>{locator && <pre>{locator}</pre>}<button type="button" className="btn btn-secondary btn-sm" onClick={() => onOpenCode(sourcePath, sourceLine)}>{t('result.openSource')}</button></div> : <p className="workspace-evidence-missing">{t('result.noCodeLocation')}</p>)}
            </section>
          </> : <p className="workspace-muted">{t('result.caseExecutionResults.empty')}</p>}
        </main>

        {hasFailures && <aside onClickCapture={focusOnPanelCard('repair')} className={`workspace-result-card workspace-repair-workspace ${focusedPanel === 'repair' ? 'is-focused' : 'is-compact'}`} aria-label={t('result.repairTitle')}>
          <header><div><span className="workspace-eyebrow">{t('result.repairEyebrow')}</span><h3>{t('result.repairTitle')}</h3></div><div className="workspace-panel-header-actions"><Bot size={18} aria-hidden="true" /><button type="button" className="btn btn-icon btn-sm workspace-panel-focus" aria-pressed={focusedPanel === 'repair'} aria-label={t('result.focusPanel', { panel: t('result.repairTitle') })} title={t('result.focusPanel', { panel: t('result.repairTitle') })} onClick={() => setActivePanel('repair')}><Maximize2 size={14} aria-hidden="true" /></button></div></header>
          {isSelectedError && failure ? <>
            <div className="workspace-repair-providers"><p><small>{t('result.aiProvider')}</small><strong>{aiProviderLabel}</strong></p><p><small>Jev</small><strong>{jevCalled ? t('result.jevActuallyCalled') : jevConfig?.enabled ? t('result.jevEnabledNotCalled') : jevConfig ? t('result.jevDisabled') : t('result.configUnavailable')}</strong></p></div>
            <ol className="workspace-repair-stages">{workflowStages.map((stage, index) => {
              const tone = eventTone(stage.status);
              const Icon = tone === 'success' ? Check : tone === 'failed' ? AlertCircle : tone === 'running' ? Activity : Circle;
              return <li key={stage.id} className={'is-' + tone}><span className="workspace-repair-marker"><Icon size={13} aria-hidden="true" /></span><div>
                <div><strong>{index + 1}. {stage.label}</strong><small className={'workspace-result-state is-' + tone}>{stageLabel(stage.status)}</small></div>
                <p>{stage.detail}</p>
                {stage.id === 'diagnosis' && analysisRunning && <div className="workspace-repair-stage-actions"><button type="button" className="btn btn-secondary btn-sm" onClick={() => void cancelAnalysis()}>{tFailures('workflow.cancel')}</button></div>}
                {stage.id === 'patch' && !analysisRunning && canStartAnalysis && <div className="workspace-repair-stage-actions"><button type="button" className={`btn ${canRestartAnalysis ? 'btn-secondary' : 'btn-primary'} btn-sm`} disabled={actionRunning || repairHistoryLoading} onClick={() => void startAnalysis()}><Bot size={13} aria-hidden="true" />{analysisId || diagnosisRootCause || analysisError ? t('result.rerunAIAnalysis') : t('result.startAIAnalysis')}</button></div>}
                {stage.id === 'apply' && (canApplyPatch || canRollbackPatch) && <div className="workspace-repair-stage-actions">
                  {canApplyPatch && <button type="button" className="btn btn-primary btn-sm" disabled={actionRunning} onClick={() => void applyPatch()}>{t('result.approveAndApplyPatch')}</button>}
                  {canRollbackPatch && <button type="button" className="btn btn-secondary btn-sm" disabled={actionRunning} onClick={async () => {
                    if (!failure || !analysisId) return;
                    setActionRunning(true); setActionError('');
                    try { const result = await api.rollbackRepair(failure.id, analysisId); setRepair(result.repair); }
                    catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
                    finally { setActionRunning(false); }
                  }}>{t('result.rollbackPatch')}</button>}
                </div>}
                {stage.id === 'verify' && canVerifyPatch && <div className="workspace-repair-stage-actions"><button type="button" className="btn btn-primary btn-sm" disabled={actionRunning} onClick={() => void verifyPatch()}>{t('result.verifyRepair')}</button></div>}
              </div></li>;
            })}</ol>
            {actionError && <p className="workspace-result-error" role="alert">{actionError}</p>}
            {diagnosisRootCause && <section className="workspace-diagnosis-result"><h4>{t('result.aiRootCause')}</h4><p>{diagnosisRootCause}</p>{diagnosisEvidence.length > 0 && <ul>{diagnosisEvidence.map((item, index) => <li key={index}>{item}</li>)}</ul>}</section>}
            {codeDiff && <details className="workspace-repair-diff" open><summary>{t('result.openDiff')} · {proposal?.file_path ?? t('result.diffReady')}</summary><pre>{codeDiff}</pre></details>}
            {analysisEvents.length > 0 && <details className="workspace-repair-events"><summary>{t('result.analysisEvents', { count: analysisEvents.length })}</summary><ol>{analysisEvents.map((event, index) => <li key={`${event.type}-${index}`}><strong>{event.type}</strong><span>{event.message}</span></li>)}</ol></details>}
            {analysisError && <p className="workspace-result-error" role="alert">{analysisError}</p>}
            {repairHistoryError && <p className="workspace-result-error" role="alert">{t('result.repairLoadError')} {repairHistoryError}</p>}
            {repairHistoryLoading && <p className="workspace-repair-selection-note" role="status">{t('result.repairHistoryLoading')}</p>}
            {verificationRun && <p className="workspace-verification-relation">{t('result.verificationRelation', { original: run.id, verification: verificationRun.id, status: t('result.runStatus.' + verificationRun.status, { defaultValue: verificationRun.status }), passed: verificationRun.executions.filter((item) => item.status === 'PASSED').length, failed: verificationRun.executions.filter((item) => ['FAILED', 'ERROR'].includes(item.status)).length })}</p>}
          </> : <p className="workspace-repair-selection-note">{isSelectedError ? failureLoadState === 'loading' ? t('result.failureLoading') : t('result.failureLoadError') : t('result.selectFailureToAnalyze')}</p>}
        </aside>}

        <aside onClickCapture={focusOnPanelCard('context')} className={`workspace-result-card workspace-run-context ${focusedPanel === 'context' ? 'is-focused' : 'is-compact'}`} aria-label={t('result.runContext')}>
          <header><span><span className="workspace-eyebrow">{runtimeConnection === 'connected' ? t('result.live') : t('result.runContext')}</span><strong>{t('result.currentTask')} · {run.id}</strong></span><button type="button" className="btn btn-icon btn-sm workspace-panel-focus" aria-pressed={focusedPanel === 'context'} aria-label={t('result.focusPanel', { panel: t('result.runContext') })} title={t('result.focusPanel', { panel: t('result.runContext') })} onClick={() => setActivePanel('context')}><Maximize2 size={14} aria-hidden="true" /></button></header>
          <dl><div><dt>{t('result.case')}</dt><dd>{selectedExecution?.nodeid ?? '—'}</dd></div><div><dt>{t('result.environment')}</dt><dd>{[run.environment.QA_ENVIRONMENT, run.environment.QA_REGION].filter(Boolean).join(' · ') || '—'}</dd></div><div><dt>{t('result.browser')}</dt><dd>{run.browser || '—'}</dd></div><div><dt>{t('result.started')}</dt><dd>{formatTime(run.started_at)} · {formatDuration(run.duration_ms)}</dd></div></dl>
          <div className="workspace-result-event-heading"><h4>{t('result.eventLog')}</h4><button type="button" className="btn btn-icon btn-sm" aria-label={t('result.viewRuntimeDetails')} onClick={onOpenDetails}><Workflow size={13} /></button></div>
          {!eventAssociationIsExact && events.length > 0 && <small className="workspace-event-association-note">{t('result.runEventsNotCaseLinked')}</small>}
          <div className="workspace-result-event-filters" role="group" aria-label={t('result.filterEvents')}>{(['all', 'errors', 'browser', 'ai'] as const).map((filter) => <button type="button" key={filter} aria-pressed={eventFilter === filter} className={eventFilter === filter ? 'is-active' : ''} onClick={() => setEventFilter(filter)}>{t('result.eventFilters.' + filter)}</button>)}</div>
          {filteredEvents.length ? <div className="workspace-result-events-viewport" role="region" aria-label={t('result.eventLog')} tabIndex={0}><ol className="workspace-result-events">{filteredEvents.map((event) => <EventRow key={event.id} event={event} onOpenDetails={onOpenDetails} onOpenStep={onOpenStep} t={t} />)}</ol></div> : runtimeError ? <p className="workspace-result-empty-inline" role="alert">{t('result.runtimeLoadError')} <button type="button" className="btn btn-secondary btn-sm" onClick={onRefreshRuntime}>{t('result.retryLoad')}</button></p> : <p className="workspace-result-empty-inline">{runRuntime ? t('result.noMatchingEvents') : t('result.runtimeLoading')}</p>}
          {run.log_output && <details className="workspace-result-raw-log"><summary>{t('result.rawRunnerLog')} · {run.log_output.split(/\r?\n/).length} {t('result.logLines')}</summary><pre>{run.log_output.slice(-12000)}</pre></details>}
        </aside>
      </div>
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
    <details><summary><span className="workspace-result-event-dot" aria-hidden="true" /><time>{formatTime(event.timestamp)}</time><span className="workspace-result-event-content"><strong>{event.title || event.type}</strong><small>{event.summary || event.category}</small></span><span className={'workspace-result-state is-' + tone}>{event.status ?? event.category}</span></summary>
      <div className="workspace-result-event-detail"><code>{event.type}</code>{event.duration_ms != null && <small>{formatDuration(event.duration_ms)}</small>}{metadata.length > 0 && <dl>{metadata.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>}<button type="button" className="btn btn-secondary btn-sm" onClick={() => event.step_id ? onOpenStep(event.step_id) : onOpenDetails()}>{event.step_id ? t('result.openRelatedStep') : t('result.openRuntimeEvidence')}</button></div>
    </details>
  </li>;
}
