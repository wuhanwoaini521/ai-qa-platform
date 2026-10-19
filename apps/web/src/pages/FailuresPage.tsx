import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AgentTask,
  AIFailureDiagnosisResponse,
  FailureAnalysisRun,
  FailureRepairWorkflow,
  AITraceEvent,
  FailureRecurrenceItem,
  FailureRecord,
  JiraBugDraft,
  JiraCreateBugResponse,
  LocatorRepairProposal,
  LocatorSemanticReviewResponse,
  Project,
  TestRun,
} from '../types';
import { api } from '../api/client';
import { AIExecutionTimeline } from '../components/AIExecutionTimeline';
import { ErrorState } from '../components/AsyncState';
import { FailureWorkflowPanel } from '../components/FailureWorkflowPanel';
import { FailureEvidence } from '../features/failures/FailureEvidence';
import { FailureOverview } from '../features/failures/FailureOverview';
import {
  displayedFailureClassification,
  failedLocatorFromFailure,
  failureSourceLocation,
  normalizeFailureClassification,
  primaryActionForWorkflow,
  relatedFailures,
  storedRepairProposal,
} from '../features/failures/failureWorkspaceModel';
import {
  Sparkles,
  Check,
  ShieldCheck,
  History,
  Bug,
  ExternalLink,
  XCircle,
} from 'lucide-react';

interface FailuresPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  /** Deep-link target: when set, this failure is selected once the list resolves. */
  initialFailureId?: string | null;
  /** Opens the failing test file in the Automation Studio. */
  onOpenInStudio?: (
    filePath: string,
    lineNumber?: number,
    debugNodeId?: string,
    failureContext?: { failureId: string; runId: string },
  ) => void;
  onNavigateToRuns?: (runId?: string) => void;
  /** Opens the task runtime while preserving the selected failure context. */
  onTaskStarted: (taskId: string, preserveFailureContext: boolean) => void;
}

export const FailuresPage: React.FC<FailuresPageProps> = ({
  projects,
  selectedProjectId,
  initialFailureId,
  onOpenInStudio,
  onNavigateToRuns,
  onTaskStarted,
}) => {
  const { t, i18n } = useTranslation('failures');
  const currentProjectId = selectedProjectId || projects[0]?.id || null;

  const [failures, setFailures] = useState<FailureRecord[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedFailure, setSelectedFailure] = useState<FailureRecord | null>(
    null,
  );
  const [sourceRun, setSourceRun] = useState<TestRun | null>(null);
  const [verificationRun, setVerificationRun] = useState<TestRun | null>(null);

  // Diagnosis State
  const [diagnosing, setDiagnosing] = useState<boolean>(false);
  const [aiDiagnosis, setAiDiagnosis] =
    useState<AIFailureDiagnosisResponse | null>(null);
  const [diagnosisEvents, setDiagnosisEvents] = useState<AITraceEvent[]>([]);
  const [diagnosisError, setDiagnosisError] = useState('');
  const [analysisHistory, setAnalysisHistory] = useState<FailureAnalysisRun[]>(
    [],
  );
  const [repairWorkflow, setRepairWorkflow] = useState<FailureRepairWorkflow | null>(null);
  const [repairWorkflowLoading, setRepairWorkflowLoading] = useState(false);
  const [repairWorkflowError, setRepairWorkflowError] = useState('');
  const [repairWorkflowLoadAttempt, setRepairWorkflowLoadAttempt] = useState(0);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState('');
  const selectedAnalysisIdRef = useRef('');
  selectedAnalysisIdRef.current = selectedAnalysisId;
  const selectedFailureIdRef = useRef<string | null>(null);
  selectedFailureIdRef.current = selectedFailure?.id ?? null;
  const analysisSelectionRequestRef = useRef(0);
  const diagnosisController = useRef<AbortController | null>(null);

  const restoreAnalysis = (analysis: FailureAnalysisRun) => {
    setSelectedAnalysisId(analysis.id);
    setDiagnosisEvents(analysis.events);
    setAiDiagnosis(analysis.result.diagnosis ?? null);
    setDiagnosisError('');
    // A persisted terminal state must explain itself, also after a reload.
    if (analysis.status === 'CANCELLED') {
      setDiagnosisError(t('diagnosisCancelled'));
    } else if (
      analysis.status === 'FAILED' ||
      analysis.status === 'TIMEOUT' ||
      analysis.status === 'INTERRUPTED'
    ) {
      const lastRunEvent = [...analysis.events]
        .reverse()
        .find((event) => event.type.startsWith('run.'));
      setDiagnosisError(
        lastRunEvent?.message || t('alertDiagnoseFailed', { error: analysis.status }),
      );
    }
  };

  useEffect(() => {
    const requestId = ++analysisSelectionRequestRef.current;
    const preferredAnalysisId = selectedAnalysisIdRef.current;
    setAnalysisHistory([]);
    setRepairWorkflow(null);
    setRepairProposal(null);
    setSelectedCandidate('');
    setSemanticReview(null);
    setRepairWorkflowError('');
    setRepairWorkflowLoading(Boolean(selectedFailure?.id));
    if (!selectedFailure?.id) return;
    let active = true;
    void api
      .getFailureAnalyses(selectedFailure.id)
      .then(async (rows) => {
        if (!active || analysisSelectionRequestRef.current !== requestId) return;
        setAnalysisHistory(rows);
        const preferredAnalysis = rows.find((item) => item.id === preferredAnalysisId) ?? rows[0];
        if (preferredAnalysis && !diagnosisController.current) {
          restoreAnalysis(preferredAnalysis);
          // Reloading during a live analysis must resume the stream instead of showing a frozen page.
          if (preferredAnalysis.status === 'RUNNING') void followFailureAnalysis(selectedFailure.id);
        }
        try {
          const workflow = await api.getFailureRepairWorkflow(selectedFailure.id, preferredAnalysis?.id);
          if (!active || analysisSelectionRequestRef.current !== requestId) return;
          setRepairWorkflow(workflow);
          const proposal = workflow.repair_proposal ?? preferredAnalysis?.result.repair_proposal;
          setRepairProposal(proposal ? proposal as LocatorRepairProposal : null);
        } catch (error) {
          if (active && analysisSelectionRequestRef.current === requestId) {
            setRepairWorkflowError(String(error));
          }
        } finally {
          if (active && analysisSelectionRequestRef.current === requestId) {
            setRepairWorkflowLoading(false);
          }
        }
      })
      .catch((error) => {
        if (active && analysisSelectionRequestRef.current === requestId) {
          setDiagnosisError(String(error));
          setRepairWorkflowError(String(error));
          setRepairWorkflowLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [selectedFailure?.id, repairWorkflowLoadAttempt]);

  const selectedAnalysis = analysisHistory.find(
    (item) => item.id === selectedAnalysisId,
  );
  const verificationRunStatus = verificationRun?.status ??
    repairWorkflow?.verification_run_status ??
    selectedAnalysis?.result.verification_run_status;
  useEffect(() => {
    if (
      !selectedFailure?.id ||
      (repairWorkflow?.state !== 'VERIFYING_FIX' &&
        !['QUEUED', 'RUNNING'].includes(verificationRunStatus ?? '') &&
        !['QUEUED', 'RUNNING'].includes(repairWorkflow?.retry_run_status ?? ''))
    )
      return;
    let active = true;
    const timer = window.setInterval(() => {
      void api
        .getFailureAnalyses(selectedFailure.id)
        .then(async (rows) => {
          if (!active || diagnosisController.current) return;
          setAnalysisHistory(rows);
          const selected = rows.find((item) => item.id === selectedAnalysisId);
          if (selected) restoreAnalysis(selected);
          const workflow = await api.getFailureRepairWorkflow(selectedFailure.id, selectedAnalysisId || undefined);
          if (!active) return;
          setRepairWorkflow(workflow);
          if (workflow.repair_proposal) {
            setRepairProposal(workflow.repair_proposal as LocatorRepairProposal);
          }
        })
        .catch(() => undefined);
    }, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [selectedFailure?.id, selectedAnalysisId, verificationRunStatus, repairWorkflow?.retry_run_status]);

  useEffect(() => () => diagnosisController.current?.abort(), []);

  // Locator Repair Proposal State
  const [repairProposal, setRepairProposal] =
    useState<LocatorRepairProposal | null>(null);
  const [repairError, setRepairError] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState<string>('');

  // Semantic Review State
  const [reviewingSemantic, setReviewingSemantic] = useState<boolean>(false);
  const [semanticReview, setSemanticReview] =
    useState<LocatorSemanticReviewResponse | null>(null);

  const handleSelectAnalysis = async (analysisId: string) => {
    const analysis = analysisHistory.find((item) => item.id === analysisId);
    if (!analysis || analysis.id === selectedAnalysisId) return;
    const requestId = ++analysisSelectionRequestRef.current;
    restoreAnalysis(analysis);
    setRepairWorkflow(null);
    setRepairProposal(null);
    setSelectedCandidate('');
    setSemanticReview(null);
    setRepairWorkflowError('');
    setRepairWorkflowLoading(true);
    try {
      const workflow = await api.getFailureRepairWorkflow(analysis.failure_id, analysis.id);
      if (
        analysisSelectionRequestRef.current !== requestId ||
        selectedFailureIdRef.current !== analysis.failure_id
      ) return;
      setRepairWorkflow(workflow);
      const proposal = workflow.repair_proposal ?? analysis.result.repair_proposal;
      setRepairProposal(proposal ? proposal as LocatorRepairProposal : null);
    } catch (error) {
      if (analysisSelectionRequestRef.current === requestId) {
        setRepairWorkflowError(String(error));
      }
    } finally {
      if (analysisSelectionRequestRef.current === requestId) {
        setRepairWorkflowLoading(false);
      }
    }
  };

  // Recurrence State
  const [recurrenceList, setRecurrenceList] = useState<FailureRecurrenceItem[]>(
    [],
  );
  const [loadingRecurrence, setLoadingRecurrence] = useState<boolean>(false);
  const [recurrenceError, setRecurrenceError] = useState(false);
  const recurrenceRequestRef = useRef(0);

  // Jira Bug Ticket State (Phase 9)
  const [isJiraBugModalOpen, setIsJiraBugModalOpen] = useState<boolean>(false);
  const [jiraBugDraft, setJiraBugDraft] = useState<JiraBugDraft | null>(null);
  const [generatingJiraDraft, setGeneratingJiraDraft] =
    useState<boolean>(false);
  const [creatingJiraBug, setCreatingJiraBug] = useState<boolean>(false);
  const [jiraBugResult, setJiraBugResult] =
    useState<JiraCreateBugResponse | null>(null);

  const [applyingRepair, setApplyingRepair] = useState<boolean>(false);
  const [rejectingRepair, setRejectingRepair] = useState<boolean>(false);
  const [startingRepairTask, setStartingRepairTask] = useState<boolean>(false);
  const [repairTaskId, setRepairTaskId] = useState<string | null>(null);
  const [rollingBackRepair, setRollingBackRepair] = useState<boolean>(false);
  const repairApplied = repairWorkflow?.repair_proposal?.applied === true;
  const repairRejected = repairWorkflow?.block_reason === 'HUMAN_REJECTED';
  const repairVerified = repairWorkflow?.verified === true;
  const repairReady = repairWorkflow?.allowed_actions.includes('APPLY') === true;
  const diagnosisState = repairWorkflow?.state ?? 'CREATED';
  const workflowActions = repairWorkflow?.allowed_actions ?? [];
  const locatorRepairReason = repairProposal?.verification_reason
    ? t('locatorRepairNotApplicable', { classification: repairProposal.verification_reason })
    : null;
  const repairEligibilityMessage = repairWorkflowError
    ? t('workflow.statusUnavailableDetail')
    : repairReady
    ? t('repairProposalNotCreated')
    : workflowActions.includes('START_ANALYSIS')
      ? t('repairUnavailableUntilDiagnosis')
      : t('repairNotRecommended');
  const canStartRepairTask = Boolean(
    selectedFailure &&
      currentProjectId &&
      !repairWorkflowLoading &&
      !repairWorkflowError &&
      !repairApplied &&
      !repairReady &&
      !['ANALYZING', 'DECIDING', 'VERIFYING_CANDIDATE', 'APPLYING', 'VERIFYING_FIX'].includes(diagnosisState),
  );
  const useLocatorDiagnosis = Boolean(
    selectedFailure &&
      analysisHistory.length === 0 &&
      (normalizeFailureClassification(selectedFailure.failure_kind ?? selectedFailure.classification) === 'LOCATOR_CHANGED' ||
        failedLocatorFromFailure(selectedFailure)),
  );
  const selectedDecision = selectedAnalysis?.result.selection ?? {};
  const decisionBlockReason = String(selectedDecision.fallback_reason ?? '');
  const resolvedClassification = normalizeFailureClassification(
    selectedAnalysis?.result.resolved_classification ?? selectedAnalysis?.result.diagnosis?.classification,
  );
  const primaryActions = analysisHistory.length > 0
    ? workflowActions.filter((action) => action !== 'START_ANALYSIS')
    : workflowActions;
  const workflowPrimaryAction = diagnosing
    ? 'ANALYZING'
    : primaryActionForWorkflow(diagnosisState, primaryActions);
  const canStartRepairTaskAsPrimary = canStartRepairTask &&
    ['RUN_DIAGNOSIS', 'BLOCKED'].includes(workflowPrimaryAction);
  const primaryAction = canStartRepairTaskAsPrimary ? 'RUN_DIAGNOSIS' : workflowPrimaryAction;
  const showReanalysis = !canStartRepairTaskAsPrimary && analysisHistory.length > 0 && (
    workflowActions.includes('START_ANALYSIS') || diagnosing
  );
  const reanalysisBlockedReason = diagnosisState === 'FAILED' && repairApplied
    ? t('rollbackBeforeReanalysis')
    : undefined;
  const sharedFailures = selectedFailure
    ? relatedFailures(failures, selectedFailure)
    : [];
  const canRetry = workflowActions.includes('RETRY');
  const canCreateJiraDraft = workflowActions.includes('CREATE_ISSUE_DRAFT');

  const [rerunning, setRerunning] = useState<boolean>(false);
  const [rerunMessage, setRerunMessage] = useState<string | null>(null);
  const primaryActionDisabled =
    ['ANALYZING', 'VERIFYING', 'VERIFIED', 'BLOCKED'].includes(primaryAction) ||
    rerunning || generatingJiraDraft || startingRepairTask ||
    (primaryAction === 'RUN_DIAGNOSIS' && !useLocatorDiagnosis && !repairTaskId && !currentProjectId);
  const showFailurePrimaryAction = !['ANALYZING', 'VERIFYING', 'VERIFIED'].includes(primaryAction);
  const primaryActionReason =
    primaryAction === 'RUN_DIAGNOSIS' && !useLocatorDiagnosis && !repairTaskId && !currentProjectId
      ? t('repairRequiresProject')
      : primaryAction === 'BLOCKED'
        ? decisionBlockReason === 'below_minimum_confidence'
          ? t('primaryReasons.jevConfidenceTooLow')
          : decisionBlockReason === 'selected_candidate_failed_verification' || selectedDecision.verified === false
            ? t('primaryReasons.candidateNotVerified')
            : resolvedClassification === 'LOCATOR_CHANGED'
              ? t('primaryReasons.locatorRepairBlocked')
              : t('primaryReasons.repairUnavailable')
        : undefined;
  const handleOpenFailureInStudio = async (startDebug = false) => {
    if (!selectedFailure || !onOpenInStudio) return;
    const sourceLocation = failureSourceLocation(selectedFailure);
    const filePath = sourceLocation.filePath ?? selectedFailure.test_nodeid.split('::')[0];
    const breakpoints = currentProjectId
      ? await api.getBreakpoints(currentProjectId).catch(() => [])
      : [];
    const failureBreakpoint = breakpoints.find(
      (item) =>
        item.source === 'auto_failure' &&
        item.run_id === selectedFailure.run_id &&
        item.file_path === filePath,
    );
    onOpenInStudio(
      filePath,
      failureBreakpoint?.line_number ?? sourceLocation.lineNumber ?? undefined,
      startDebug ? selectedFailure.test_nodeid : undefined,
      { failureId: selectedFailure.id, runId: selectedFailure.run_id },
    );
  };

  const fetchFailures = async () => {
    try {
      const data = await api.getFailures(currentProjectId || undefined);
      setFailures(data);
      setLoadError(null);
      const deepLinked = initialFailureId
        ? data.find((f) => f.id === initialFailureId)
        : undefined;
      if (deepLinked) {
        handleSelectFailure(deepLinked);
      } else if (data.length > 0) {
        handleSelectFailure(data[0]);
      } else {
        setSelectedFailure(null);
      }
    } catch (err) {
      console.error('Failed to load failures', err);
      // An empty queue and a broken request must not look the same.
      setFailures([]);
      setSelectedFailure(null);
      setLoadError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    fetchFailures();
  }, [currentProjectId]);

  useEffect(() => {
    setSourceRun(null);
    setVerificationRun(null);
    if (!selectedFailure?.run_id) return;
    let active = true;
    void api.getTestRun(selectedFailure.run_id).then((run) => {
      if (active) setSourceRun(run);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [selectedFailure?.run_id]);

  useEffect(() => {
    const failureId = selectedFailure?.id;
    if (!currentProjectId || !failureId) {
      setRepairTaskId(null);
      return;
    }
    let active = true;
    void api.getTasks(currentProjectId).then((tasks) => {
      if (!active) return;
      const belongsToFailure = (task: AgentTask) =>
        task.type === 'FIX_FAILURE' &&
        task.inputs.failure_id === failureId;
      const existing = tasks.find((task) =>
        belongsToFailure(task) &&
        !['COMPLETED', 'FAILED', 'BLOCKED', 'CANCELLED'].includes(task.status),
      ) ?? tasks.find(belongsToFailure);
      setRepairTaskId(existing?.id ?? null);
    }).catch(() => {
      if (active) setRepairTaskId(null);
    });
    return () => { active = false; };
  }, [currentProjectId, selectedFailure?.id]);

  useEffect(() => {
    const verificationRunId = selectedAnalysis?.result.verification_run_id;
    if (!verificationRunId) return;
    let active = true;
    void api.getTestRun(verificationRunId).then((run) => {
      if (active) setVerificationRun(run);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [selectedAnalysis?.result.verification_run_id]);

  useEffect(() => {
    if (!verificationRun || !['QUEUED', 'RUNNING'].includes(verificationRun.status)) return;
    let active = true;
    const timer = window.setInterval(() => {
      void api.getTestRun(verificationRun.id).then((run) => {
        if (active) setVerificationRun(run);
      }).catch(() => undefined);
    }, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [verificationRun?.id, verificationRun?.status]);

  const handleSelectFailure = (f: FailureRecord) => {
    const savedRepair = storedRepairProposal(f.repair_proposal);
    diagnosisController.current?.abort();
    diagnosisController.current = null;
    setDiagnosing(false);
    setDiagnosisEvents([]);
    setDiagnosisError('');
    setRepairWorkflowError('');
    setRepairWorkflowLoading(Boolean(f.id));
    setSelectedAnalysisId('');
    setRepairWorkflowLoadAttempt((attempt) => attempt + 1);
    setSelectedFailure(f);
    setRepairTaskId(null);
    setSourceRun(null);
    setVerificationRun(null);
    setAiDiagnosis(null);
    setRepairProposal(savedRepair);
    setRepairError('');
    setSelectedCandidate(savedRepair?.proposed_locator ?? '');
    setSemanticReview(null);
    setRepairWorkflow(null);
    setRerunMessage(null);
    fetchRecurrence(f.id);
  };

  useEffect(() => {
    const linkedFailure = failures.find((failure) => failure.id === initialFailureId);
    if (!linkedFailure || selectedFailure?.id === linkedFailure.id) return;
    handleSelectFailure(linkedFailure);
  }, [initialFailureId, failures, selectedFailure?.id, handleSelectFailure]);

  const fetchRecurrence = async (failureId: string) => {
    const requestId = ++recurrenceRequestRef.current;
    setLoadingRecurrence(true);
    setRecurrenceError(false);
    setRecurrenceList([]);
    try {
      const list = await api.getFailureRecurrence(failureId);
      if (requestId === recurrenceRequestRef.current) setRecurrenceList(list);
    } catch (err) {
      if (requestId === recurrenceRequestRef.current) {
        console.error('Failed to fetch recurrence', err);
        setRecurrenceError(true);
      }
    } finally {
      if (requestId === recurrenceRequestRef.current) setLoadingRecurrence(false);
    }
  };

  // One server-side analysis can be followed twice: when it is started here, and after a reload.
  const followFailureAnalysis = async (failureId: string, reset = false) => {
    if (reset) {
      diagnosisController.current?.abort();
      setSelectedAnalysisId('');
      setAiDiagnosis(null);
      setDiagnosisEvents([]);
      setDiagnosisError('');
      setRepairWorkflow(null);
      setRepairProposal(null);
      setRepairError('');
      setSemanticReview(null);
      setSelectedCandidate('');
      setVerificationRun(null);
      setRerunMessage(null);
    }
    const controller = new AbortController();
    diagnosisController.current = controller;
    setDiagnosing(true);
    let terminal = false;
    let analysisId = '';
    try {
      await api.streamFailureWorkflow(
        failureId,
        (event) => {
          if (
            diagnosisController.current !== controller ||
            controller.signal.aborted
          )
            return;
          setDiagnosisEvents((previous) => [...previous, event]);
          if (typeof event.metadata?.analysis_id === 'string') {
            analysisId = event.metadata.analysis_id;
            setSelectedAnalysisId(analysisId);
          }
          if (event.type === 'run.completed') {
            // SAFETY: the backend run.completed event serializes diagnosis using the shared response DTO.
            const result = event.metadata?.diagnosis as unknown as
              AIFailureDiagnosisResponse | undefined;
            if (!result) throw new Error(t('diagnosisStreamIncomplete'));
            terminal = true;
            setAiDiagnosis(result);
            const proposal = event.metadata?.repair_proposal as LocatorRepairProposal | null | undefined;
            if (proposal?.proposed_locator) {
              setRepairProposal(proposal);
              setSelectedCandidate(proposal.proposed_locator);
              setSelectedFailure((current) => current
                ? { ...current, repair_proposal: proposal }
                : current);
            }
          } else if (
            event.type === 'run.failed' ||
            event.type === 'run.timeout' ||
            event.type === 'run.interrupted' ||
            event.type === 'run.cancelled'
          ) {
            terminal = true;
            setDiagnosisError(
              event.message ||
                (event.type === 'run.cancelled'
                  ? t('diagnosisCancelled')
                  : t('diagnosisStreamIncomplete')),
            );
          }
        },
        controller.signal,
        i18n.resolvedLanguage ?? i18n.language,
      );
      if (!terminal && !controller.signal.aborted)
        throw new Error(t('diagnosisStreamIncomplete'));
    } catch (err: unknown) {
      if (
        diagnosisController.current === controller &&
        !controller.signal.aborted
      ) {
        setDiagnosisError(
          t('alertDiagnoseFailed', {
            error: err instanceof Error ? err.message : String(err),
          }),
        );
      }
    } finally {
      if (diagnosisController.current === controller) {
        diagnosisController.current = null;
        setDiagnosing(false);
      }
      void api.getFailure(failureId).then((refreshed) => {
        if (selectedFailureIdRef.current === failureId) {
          setSelectedFailure((current) => current?.id === failureId
            ? { ...current, evidence_bundle: refreshed.evidence_bundle }
            : current);
        }
      }).catch(() => undefined);
      void api
        .getFailureAnalyses(failureId)
        .then(async (rows) => {
          if (selectedFailureIdRef.current !== failureId || diagnosisController.current) return;
          setAnalysisHistory(rows);
          const saved = rows.find((item) => item.id === analysisId);
          if (saved) restoreAnalysis(saved);
          const workflow = await api.getFailureRepairWorkflow(failureId, analysisId || undefined);
          if (selectedFailureIdRef.current === failureId) {
            setRepairWorkflow(workflow);
            if (workflow.repair_proposal) {
              setRepairProposal(workflow.repair_proposal as LocatorRepairProposal);
            }
          }
        })
        .catch(() => undefined);
    }
  };

  const handleDiagnoseAI = async () => {
    if (!selectedFailure) return;
    await followFailureAnalysis(selectedFailure.id, true);
  };

  const handleCancelDiagnosis = async () => {
    const failureId = selectedFailure?.id;
    const analysisId = selectedAnalysisIdRef.current || repairWorkflow?.analysis_id || '';
    // Cancelling must stop the server-side task, not only the browser stream.
    if (failureId && analysisId) {
      try {
        setRepairWorkflow(await api.cancelFailureAnalysis(failureId, analysisId));
        const rows = await api.getFailureAnalyses(failureId);
        if (selectedFailureIdRef.current === failureId) {
          setAnalysisHistory(rows);
          const saved = rows.find((item) => item.id === analysisId);
          if (saved) restoreAnalysis(saved);
        }
      } catch (err: unknown) {
        setDiagnosisError(
          t('alertDiagnoseFailed', { error: err instanceof Error ? err.message : String(err) }),
        );
      }
    }
    diagnosisController.current?.abort();
    diagnosisController.current = null;
    setDiagnosing(false);
  };

  const handleSemanticReview = async () => {
    if (!selectedFailure || !repairProposal) return;
    const chosenLocator = selectedCandidate || repairProposal.proposed_locator;
    const sourceLocator = repairProposal.source_locator || repairProposal.old_locator;
    try {
      setReviewingSemantic(true);
      const review = await api.getSemanticLocatorReview(
        selectedFailure.id,
        sourceLocator,
        chosenLocator,
      );
      setSemanticReview(review);
    } catch (err: any) {
      alert(t('alertSemanticReviewFailed', { error: err.message || err }));
    } finally {
      setReviewingSemantic(false);
    }
  };

  const handleApplyRepair = async () => {
    if (
      !selectedFailure ||
      !repairProposal ||
      !selectedAnalysisId ||
      !repairWorkflow?.allowed_actions.includes('APPLY')
    )
      return;
    const chosenLocator = selectedCandidate || repairProposal.proposed_locator;
    const sourceLocator = repairProposal.source_locator || repairProposal.old_locator;
    if (
      !chosenLocator.trim() ||
      chosenLocator.trim() === sourceLocator.trim()
    ) {
      setRepairError(t('noAlternativeLocator'));
      return;
    }
    const filePath =
      repairProposal.file_path || selectedFailure.test_nodeid.split('::')[0];
    try {
      setApplyingRepair(true);
      const result = await api.applyRepair(
        selectedFailure.id,
        selectedAnalysisId,
        {
          file_path: filePath,
          old_code: sourceLocator,
          new_code: chosenLocator,
        },
      );
      setRepairWorkflow(result.repair);
      setRerunMessage(t('patchAppliedStatus'));
      const rows = await api.getFailureAnalyses(selectedFailure.id);
      setAnalysisHistory(rows);
      const appliedAnalysis = rows.find((item) => item.id === selectedAnalysisId);
      if (appliedAnalysis) restoreAnalysis(appliedAnalysis);
    } catch (err: any) {
      alert(t('alertApplyRepairFailed', { error: err.message || err }));
    } finally {
      setApplyingRepair(false);
    }
  };

  const handleRejectRepair = async () => {
    if (
      !selectedFailure ||
      !selectedAnalysisId ||
      !repairWorkflow?.allowed_actions.includes('REJECT') ||
      rejectingRepair ||
      applyingRepair
    ) return;
    try {
      setRejectingRepair(true);
      setRepairError('');
      const workflow = await api.rejectRepair(selectedFailure.id, selectedAnalysisId);
      setRepairWorkflow(workflow);
      setRepairProposal(workflow.repair_proposal as LocatorRepairProposal | null);
      setSelectedCandidate('');
      setSemanticReview(null);
      const rows = await api.getFailureAnalyses(selectedFailure.id);
      setAnalysisHistory(rows);
      const rejectedAnalysis = rows.find((item) => item.id === selectedAnalysisId);
      if (rejectedAnalysis) restoreAnalysis(rejectedAnalysis);
    } catch (error) {
      setRepairError(t('alertRejectRepairFailed', {
        error: error instanceof Error ? error.message : String(error),
      }));
    } finally {
      setRejectingRepair(false);
    }
  };

  const handleStartRepairTask = async () => {
    if (repairTaskId) {
      onTaskStarted(repairTaskId, true);
      return;
    }
    if (!selectedFailure || !currentProjectId || startingRepairTask) return;
    try {
      setStartingRepairTask(true);
      setRepairError('');
      const task = await api.createTask({
        type: 'FIX_FAILURE',
        goal: t('codeRepairTaskGoal', { nodeid: selectedFailure.test_nodeid }),
        project_id: currentProjectId,
        workspace_id: sourceRun?.workspace_id ?? currentProjectId,
        inputs: {
          failure_id: selectedFailure.id,
          origin: 'failure',
          origin_id: selectedFailure.id,
        },
      });
      setRepairTaskId(task.id);
      onTaskStarted(task.id, true);
    } catch (error) {
      setRepairError(t('codeRepairTaskFailed', {
        error: error instanceof Error ? error.message : String(error),
      }));
    } finally {
      setStartingRepairTask(false);
    }
  };

  const dispatchVerificationRun = async (repairAnalysisId?: string): Promise<boolean> => {
    if (!selectedFailure || rerunning) return false;
    if (repairAnalysisId && !repairWorkflow?.allowed_actions.includes('VERIFY')) return false;
    if (!repairAnalysisId && (!repairWorkflow?.analysis_id || !repairWorkflow.allowed_actions.includes('RETRY'))) return false;
    try {
      setRerunning(true);
      setRerunMessage(t('rerunTriggering'));
      const analysisId = repairAnalysisId ?? repairWorkflow!.analysis_id!;
      const run = repairAnalysisId
        ? await api.startFailureVerification(selectedFailure.id, analysisId)
        : await api.startFailureRetry(selectedFailure.id, analysisId);
      setVerificationRun(run);
      const workflow = await api.getFailureRepairWorkflow(selectedFailure.id, analysisId);
      if (selectedFailureIdRef.current === selectedFailure.id) setRepairWorkflow(workflow);
      setRerunMessage(
        t('rerunDispatched', { runId: run.id.slice(0, 8), status: run.status }),
      );
      if (onNavigateToRuns) {
        setTimeout(() => onNavigateToRuns(run.id), 1200);
      }
      return true;
    } catch (err: any) {
      setRerunMessage(t('rerunError', { error: err.message || err }));
      return false;
    } finally {
      setRerunning(false);
    }
  };

  const handleRerunTest = async () => {
    if (!selectedFailure || !repairWorkflow?.allowed_actions.includes('RETRY') || rerunning) return;
    await dispatchVerificationRun();
  };

  const handleVerifyRepair = async () => {
    if (!repairWorkflow?.allowed_actions.includes('VERIFY') || !repairWorkflow.analysis_id) return;
    await dispatchVerificationRun(repairWorkflow.analysis_id);
  };

  const handleRollbackRepair = async () => {
    if (
      !selectedFailure ||
      !repairWorkflow?.analysis_id ||
      !repairWorkflow.allowed_actions.includes('ROLLBACK') ||
      rollingBackRepair
    ) return;
    try {
      setRollingBackRepair(true);
      const result = await api.rollbackRepair(selectedFailure.id, repairWorkflow.analysis_id);
      setRepairWorkflow(result.repair);
      setRerunMessage(t('patchRolledBack', { file: result.file_path }));
      const rows = await api.getFailureAnalyses(selectedFailure.id);
      setAnalysisHistory(rows);
      const rolledBackAnalysis = rows.find((item) => item.id === repairWorkflow.analysis_id);
      if (rolledBackAnalysis) restoreAnalysis(rolledBackAnalysis);
    } catch (error) {
      setRepairError(t('rollbackFailed', { error: error instanceof Error ? error.message : String(error) }));
    } finally {
      setRollingBackRepair(false);
    }
  };

  const handleOpenJiraBugModal = async () => {
    if (!selectedFailure || !repairWorkflow?.allowed_actions.includes('CREATE_ISSUE_DRAFT')) return;
    setIsJiraBugModalOpen(true);
    setGeneratingJiraDraft(true);
    setJiraBugResult(null);
    try {
      const draft = await api.generateJiraBugDraft({
        failure_id: selectedFailure.id,
        project_key: 'QA',
        issue_type: 'Bug',
      });
      setJiraBugDraft(draft);
    } catch (err) {
      console.error('Failed to generate Jira bug draft', err);
    } finally {
      setGeneratingJiraDraft(false);
    }
  };

  const handleConfirmCreateJiraBug = async (confirmPublish: boolean) => {
    if (!jiraBugDraft) return;
    setCreatingJiraBug(true);
    try {
      const res = await api.createJiraBug({
        draft: jiraBugDraft,
        confirm_publish: confirmPublish,
      });
      setJiraBugResult(res);
    } catch (err) {
      console.error('Failed to create Jira bug', err);
    } finally {
      setCreatingJiraBug(false);
    }
  };

  const handlePrimaryAction = () => {
    if (primaryAction === 'RUN_DIAGNOSIS') {
      if (useLocatorDiagnosis && !repairTaskId) void handleDiagnoseAI();
      else void handleStartRepairTask();
    }
    else if (primaryAction === 'RETRY') void handleRerunTest();
    else if (primaryAction === 'VERIFY_FIX') void handleVerifyRepair();
    else if (primaryAction === 'CREATE_ISSUE_DRAFT') void handleOpenJiraBugModal();
    else if (primaryAction === 'REVIEW_REPAIR') document.getElementById('failure-repair-proposal')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div>
      {projects.length === 0 ? (
        <div className="card">
          <div
            className="card-body"
            style={{
              padding: '40px',
              textAlign: 'center',
              color: 'var(--text-muted)',
            }}
          >
            {t('noProject')}
          </div>
        </div>
      ) : (
        <div className="failure-workbench-grid">
          {selectedFailure ? (
            <div className="failure-workspace-detail">
              <FailureOverview
                failure={selectedFailure}
                sourceRun={sourceRun}
                verificationRun={verificationRun}
                verificationRunId={repairWorkflow?.retry_run_id ?? repairWorkflow?.verification_run_id ?? selectedAnalysis?.result.verification_run_id}
                linkedVerificationStatus={repairWorkflow?.retry_run_status ?? repairWorkflow?.verification_run_status ?? selectedAnalysis?.result.verification_run_status}
                diagnosis={aiDiagnosis}
                state={diagnosisState}
                primaryAction={primaryAction}
                primaryActionLabel={primaryAction === 'RUN_DIAGNOSIS'
                  ? startingRepairTask
                    ? t('preparingCodeRepair')
                    : repairTaskId
                      ? t('openCodeRepairTask')
                      : t('primaryActions.RUN_DIAGNOSIS')
                  : undefined}
                primaryDisabled={primaryActionDisabled}
                showPrimaryAction={showFailurePrimaryAction && !repairWorkflowLoading && !repairWorkflowError}
                showReanalysis={showReanalysis}
                reanalysisPending={diagnosing}
                workflowLoading={repairWorkflowLoading}
                workflowLoadError={repairWorkflowError}
                onRetryWorkflowLoad={() => setRepairWorkflowLoadAttempt((attempt) => attempt + 1)}
                reanalysisBlockedReason={reanalysisBlockedReason}
                primaryReason={primaryActionReason}
                onPrimaryAction={handlePrimaryAction}
                onReanalysis={() => void handleDiagnoseAI()}
                canRetry={canRetry}
                rerunning={rerunning}
                onRetry={() => void handleRerunTest()}
                onOpenStudio={onOpenInStudio ? () => void handleOpenFailureInStudio() : undefined}
                onDebug={onOpenInStudio ? () => void handleOpenFailureInStudio(true) : undefined}
                canCreateJiraDraft={canCreateJiraDraft}
                onCreateJiraDraft={() => void handleOpenJiraBugModal()}
                relatedTests={sharedFailures.map((item) => item.test_nodeid)}
                repairProposed={Boolean(repairProposal)}
                repairApplied={repairApplied}
                repairRejected={repairRejected}
                rerunMessage={rerunMessage}
                hasRepairTask={Boolean(repairTaskId)}
              />
              {repairError && <div className="alert alert-error" role="alert">{repairError}</div>}

              {aiDiagnosis && (
                <section className="card failure-diagnosis-card" aria-labelledby="failure-diagnosis-heading">
                  <div className="card-header">
                    <span className="card-title" id="failure-diagnosis-heading">{t('diagnosisTitle', { classification: displayedFailureClassification(selectedFailure.failure_kind ?? selectedFailure.classification) })}</span>
                    <span className="failure-diagnosis-confidence">{t('confidence', { value: (aiDiagnosis.confidence * 100).toFixed(0) })}</span>
                  </div>
                  <div className="card-body">
                    {(aiDiagnosis.fallback_used || aiDiagnosis.provider === 'fake') && <p className="failure-diagnosis-warning" role="status">{t(aiDiagnosis.provider === 'fake' ? 'simulatedDiagnosis' : 'fallbackDiagnosis')}</p>}
                    <dl className="failure-diagnosis-grid">
                      <div><dt>{t('repairEligibility')}</dt><dd>{repairReady ? t('repairEligible') : t('repairabilityUnknown')}</dd></div>
                      {aiDiagnosis.root_cause && <div className="is-wide"><dt>{t('rootCause')}</dt><dd><a href="#failure-root-cause">{t('rootCauseShownInOverview')}</a></dd></div>}
                      <div><dt>{t('evidence')}</dt><dd><ul>{aiDiagnosis.evidence.map((item, index) => <li key={index}>{item}</li>)}</ul></dd></div>
                      <div><dt>{t('recommended')}</dt><dd><ul>{aiDiagnosis.recommended_actions.map((item, index) => <li key={index}>{item}</li>)}</ul></dd></div>
                    </dl>
                    <p className="failure-diagnosis-unprovided">{t('diagnosisMissingSignals')}</p>
                    <p className="failure-diagnosis-provider">{t('aiAnalysisSource')}: {aiDiagnosis.provider || t('unknownProvider')}</p>
                  </div>
                </section>
              )}

              <FailureEvidence
                failure={selectedFailure}
                environment={sourceRun?.environment}
                browser={sourceRun?.browser}
                browserSession={sourceRun?.browser_sessions?.find((session) => session.nodeid === selectedFailure.test_nodeid)}
                browserArtifacts={sourceRun?.external_artifacts}
              />

              {/* Locator Repair Proposal Card */}
              {repairWorkflow?.repair_proposal && repairProposal && (
                <div id="failure-repair-proposal" className="card failure-repair-proposal">
                  <div
                    className="card-header"
                    style={{ background: 'var(--accent-green-soft)' }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                      }}
                    >
                      <Sparkles size={16} color="var(--accent-green)" />
                      <span className="card-title" style={{ color: 'var(--accent-green)' }}>
                        {t('proposalTitle', {
                          value:
                            repairProposal.confidence == null
                              ? t('unrated')
                              : (repairProposal.confidence * 100).toFixed(0),
                        })}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={reviewingSemantic}
                        onClick={handleSemanticReview}
                      >
                        <ShieldCheck size={13} color="var(--accent-blue)" />{' '}
                        {reviewingSemantic
                          ? t('reviewing')
                          : t('semanticReview')}
                      </button>
                      {repairRejected ? (
                        <span className="badge badge-failed" role="status">
                          {t('proposalRejected')}
                        </span>
                      ) : repairApplied ? (
                        <span className="badge badge-ready">
                          {t('repairApplied')}
                        </span>
                      ) : repairWorkflow?.allowed_actions.includes('APPLY') ? (
                        <button
                          className="btn btn-secondary btn-sm"
                          disabled={applyingRepair || rejectingRepair || rerunning || !repairProposal.source_locator || !repairProposal.code_diff}
                          onClick={handleApplyRepair}
                        >
                          <Check size={13} />{' '}
                          {applyingRepair ? t('applying') : t('applyRepair')}
                        </button>
                      ) : null}
                      {repairWorkflow?.allowed_actions.includes('VERIFY') && (
                        <button
                          className="btn btn-secondary btn-sm"
                          disabled={rerunning}
                          onClick={() => void handleVerifyRepair()}
                        >
                          {rerunning ? t('rerunTriggering') : t('verifyRepair')}
                        </button>
                      )}
                      {repairWorkflow?.allowed_actions.includes('ROLLBACK') && (
                          <button
                            className="btn btn-secondary btn-sm"
                            disabled={rollingBackRepair}
                            onClick={() => void handleRollbackRepair()}
                          >
                            {rollingBackRepair ? t('rollingBack') : t('rollbackRepair')}
                          </button>
                      )}
                      {repairWorkflow?.allowed_actions.includes('REJECT') && (
                        <button
                          className="btn btn-secondary btn-sm"
                          disabled={rejectingRepair || applyingRepair}
                          onClick={() => void handleRejectRepair()}
                        >
                          <XCircle size={13} />{' '}
                          {t(rejectingRepair ? 'rejectingProposal' : 'rejectProposal')}
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="card-body">
                    {!repairVerified && (
                      <p
                        role="status"
                        style={{
                          margin: '0 0 12px',
                          color: 'var(--accent-amber)',
                          background: 'var(--accent-amber-soft)',
                          border: '1px solid var(--accent-amber-soft)',
                          borderRadius: 4,
                          padding: '8px 10px',
                          fontSize: 12,
                        }}
                      >
                        <>
                          {repairRejected
                            ? t('proposalRejectedDetail')
                            : !repairWorkflow?.allowed_actions.includes('APPLY') || !repairProposal.verified
                              ? t('repairNotVerified')
                            : repairProposal.decision_summary?.verification_source === 'captured_browser_evidence'
                              ? t('repairCandidateVerifiedFromEvidence')
                              : t('repairCandidateVerifiedByPlaywright')}
                          {repairProposal.verification_reason ? ` · ${repairProposal.verification_reason}` : ''}
                        </>
                      </p>
                    )}
                    <dl className="failure-repair-facts">
                      <div><dt>{t('decisionEngine')}</dt><dd>{repairProposal.provider === 'jev' ? 'Jev' : t('localFallback')}{repairProposal.model ? ` · ${repairProposal.model}` : ''}{repairProposal.candidate_id ? ` · ${repairProposal.candidate_id}` : ''}</dd></div>
                      <div><dt>{t('decisionConfidence')}</dt><dd>{repairProposal.confidence == null ? t('unrated') : `${Math.round(repairProposal.confidence * 100)}%`}{repairProposal.latency_ms == null ? '' : ` · ${Math.round(repairProposal.latency_ms)} ms`}</dd></div>
                      <div><dt>{t('aiDiagnosisProvider')}</dt><dd>{repairProposal.ai_provider || t('unknownProvider')}{repairProposal.ai_fallback_used ? ` · ${t('fallbackDiagnosis')}` : ''}</dd></div>
                      <div><dt>{t('repairType')}</dt><dd>{repairProposal.strategy}</dd></div>
                      <div><dt>{t('repairFiles')}</dt><dd><code>{repairProposal.file_path || t('unknownProvider')}</code></dd></div>
                      <div><dt>{t('repairSummary')}</dt><dd>{repairProposal.reason || repairProposal.proposed_locator}</dd></div>
                      <div><dt>{t('riskLabel')}</dt><dd>{semanticReview?.risk_warning || t('riskUnknown')}</dd></div>
                    </dl>
                    <details style={{ marginBottom: 12 }}>
                      <summary
                        style={{
                          cursor: 'pointer',
                          fontSize: 12,
                          color: 'var(--text-muted)',
                        }}
                      >
                        {t('viewEvidence')}
                      </summary>
                      <div style={{ paddingTop: 8 }}>
                        <div
                          style={{
                            marginBottom: 8,
                            fontSize: 11,
                            color: 'var(--text-muted)',
                          }}
                        >
                          {t('caseExecution')}: {selectedFailure?.execution_id}
                        </div>
                        <AIExecutionTimeline
                          events={repairProposal.execution_trace ?? []}
                          running={diagnosing}
                        />
                      </div>
                    </details>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: '12px',
                        marginBottom: '12px',
                      }}
                    >
                      <div
                        style={{
                          background: 'var(--accent-red-soft)',
                          padding: '10px',
                          borderRadius: 'var(--r-xs)',
                          border: '1px solid var(--accent-red-soft)',
                        }}
                      >
                        <div
                          style={{
                            fontSize: '11px',
                            color: 'var(--accent-red)',
                            fontWeight: 700,
                          }}
                        >
                          {t('brokenLocator')}
                        </div>
                        <code
                          style={{
                            fontSize: '12px',
                            color: 'var(--accent-red)',
                            wordBreak: 'break-all',
                          }}
                        >
                          {repairProposal.source_locator || repairProposal.old_locator || t('unknownValue')}
                        </code>
                      </div>
                      <div
                        style={{
                          background: 'var(--accent-green-soft)',
                          padding: '10px',
                          borderRadius: 'var(--r-xs)',
                          border: '1px solid var(--accent-green-soft)',
                        }}
                      >
                        <div
                          style={{
                            fontSize: '11px',
                            color: 'var(--accent-green)',
                            fontWeight: 700,
                          }}
                        >
                          {t('proposedReplacement', {
                            strategy: repairProposal.strategy,
                          })}
                        </div>
                        <code
                          style={{
                            fontSize: '12px',
                            color: 'var(--accent-green)',
                            wordBreak: 'break-all',
                          }}
                        >
                          {selectedCandidate || repairProposal.proposed_locator}
                        </code>
                      </div>
                    </div>

                    {/* Semantic Review Results Banner */}
                    {semanticReview && (
                      <div
                        style={{
                          marginBottom: '12px',
                          padding: '10px 12px',
                          borderRadius: 'var(--r-xs)',
                          background: semanticReview.is_semantically_equivalent
                            ? 'var(--accent-green-soft)'
                            : 'var(--accent-amber-soft)',
                          border: `1px solid ${semanticReview.is_semantically_equivalent ? 'var(--accent-green-soft)' : 'var(--accent-amber-soft)'}`,
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            marginBottom: '4px',
                          }}
                        >
                          <span
                            style={{
                              fontSize: '12px',
                              fontWeight: 700,
                              color: semanticReview.is_semantically_equivalent
                                ? 'var(--accent-green)'
                                : 'var(--accent-amber)',
                            }}
                          >
                            {semanticReview.is_semantically_equivalent
                              ? t('semanticallyEquivalent')
                              : t('nonEquivalent')}
                          </span>
                          <span
                            style={{
                              fontSize: '11px',
                              color: 'var(--text-muted)',
                            }}
                          >
                            {t('reviewConfidence', {
                              value: (semanticReview.confidence * 100).toFixed(
                                0,
                              ),
                            })}
                          </span>
                        </div>
                        <p
                          style={{
                            fontSize: '12px',
                            color: 'var(--ink-soft)',
                            margin: 0,
                          }}
                        >
                          {semanticReview.explanation}
                        </p>
                        {semanticReview.risk_warning && (
                          <p
                            style={{
                              fontSize: '11px',
                              color: 'var(--accent-red)',
                              margin: '4px 0 0 0',
                              fontWeight: 600,
                            }}
                          >
                            {t('riskWarning', {
                              warning: semanticReview.risk_warning,
                            })}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Diff Preview */}
                    <details className="failure-repair-diff">
                      <summary>
                        {t('diffPreview', {
                          file: repairProposal.file_path || t('unknownValue'),
                        })}
                      </summary>
                      <pre className="failure-evidence-code failure-diff-code">
                        {repairProposal.code_diff || t('noDiffAvailable')}
                      </pre>
                    </details>
                  </div>
                </div>
              )}

              {!repairProposal && (
                <section className="card failure-repair-unavailable" aria-label={t('repairEligibility')}>
                  <div className="card-header"><span className="card-title">{t('repairEligibility')}</span></div>
                  <div className="card-body">
                    <strong>{repairEligibilityMessage}</strong>
                    {locatorRepairReason && <p>{locatorRepairReason}</p>}
                    {repairReady && <p>{t('proposalFlowHint')}</p>}
                  </div>
                </section>
              )}

              {(diagnosing || diagnosisEvents.length > 0 || analysisHistory.length > 0 || diagnosisError) && (
                <FailureWorkflowPanel
                  events={diagnosisEvents}
                  running={diagnosing}
                  history={analysisHistory}
                  selectedId={selectedAnalysisId}
                  failureCreatedAt={selectedFailure.created_at}
                  changesAppliedOverride={repairApplied}
                  failure={selectedFailure}
                  classification={selectedFailure.failure_kind ?? selectedFailure.classification}
                  error={diagnosisError}
                  primaryAction={primaryAction}
                  primaryActionDisabled={primaryActionDisabled || repairWorkflowLoading}
                  workflowLoading={repairWorkflowLoading}
                  workflowError={repairWorkflowError}
                  primaryActionReason={primaryActionReason}
                  primaryActionPending={diagnosing}
                  showPrimaryAction={
                    !repairWorkflowError && primaryAction !== 'RUN_DIAGNOSIS' &&
                    (workflowActions.length > 0 || primaryAction === 'BLOCKED')
                  }
                  onPrimaryAction={handlePrimaryAction}
                  onOpenStudio={onOpenInStudio ? () => void handleOpenFailureInStudio() : undefined}
                  onDebug={onOpenInStudio ? () => void handleOpenFailureInStudio(true) : undefined}
                  onCancel={handleCancelDiagnosis}
                  onSelect={(id) => void handleSelectAnalysis(id)}
                />
              )}



              {/* Similar Past Failures / Recurrence History */}
              <div className="card">
                <div className="card-header">
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <History size={15} color="var(--ink-muted)" />
                    <span className="card-title">
                      {recurrenceError
                        ? t('recurrenceTitleUnavailable')
                        : t('recurrenceTitle', { count: recurrenceList.length })}
                    </span>
                  </div>
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  {loadingRecurrence ? (
                    <div
                      style={{
                        padding: '16px',
                        textAlign: 'center',
                        color: 'var(--text-muted)',
                        fontSize: '12px',
                      }}
                    >
                      {t('recurrenceLoading')}
                    </div>
                  ) : recurrenceError ? (
                    <ErrorState
                      message={t('recurrenceLoadFailed')}
                      onRetry={() => selectedFailure && void fetchRecurrence(selectedFailure.id)}
                    />
                  ) : recurrenceList.length === 0 ? (
                    <div
                      style={{
                        padding: '16px',
                        textAlign: 'center',
                        color: 'var(--text-muted)',
                        fontSize: '12px',
                      }}
                    >
                      {t('recurrenceEmpty')}
                    </div>
                  ) : (
                    <table className="data-table" style={{ fontSize: '11px' }}>
                      <thead>
                        <tr>
                          <th style={{ padding: '6px 8px' }}>
                            {t('category')}
                          </th>
                          <th style={{ padding: '6px 8px' }}>{t('runId')}</th>
                          <th style={{ padding: '6px 8px' }}>
                            {t('recordedAt')}
                          </th>
                          <th style={{ padding: '6px 8px' }}>
                            {t('errorDetails')}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {recurrenceList.map((rec) => (
                          <tr key={rec.failure_id}>
                            <td style={{ padding: '6px 8px' }}>
                              <span
                                className="badge badge-draft"
                                style={{ fontSize: '10px' }}
                              >
                                {rec.classification}
                              </span>
                            </td>
                            <td
                              style={{
                                padding: '6px 8px',
                                fontFamily: 'var(--font-mono)',
                              }}
                            >
                              #{rec.run_id.slice(0, 8)}
                            </td>
                            <td
                              style={{
                                padding: '6px 8px',
                                color: 'var(--text-muted)',
                              }}
                            >
                              {new Date(rec.created_at).toLocaleDateString()}
                            </td>
                            <td
                              style={{ padding: '6px 8px' }}
                            >
                              {rec.error_message ? (
                                <details className="failure-history-error">
                                  <summary>{t('errorDetails')}</summary>
                                  <pre className="failure-evidence-code">{rec.error_message}</pre>
                                </details>
                              ) : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="card failure-select-prompt">
              {loadError ? (
                <ErrorState
                  message={t('loadFailed', { message: loadError })}
                  onRetry={() => void fetchFailures()}
                />
              ) : (
                t('selectPrompt')
              )}
            </div>
          )}
        </div>
      )}

      {/* Jira Bug Ticket Creation Modal (Phase 9) */}
      {isJiraBugModalOpen && (
        <div className="modal-backdrop">
          <div className="modal" style={{ maxWidth: '750px', width: '90%' }}>
            <div className="modal-header">
              <div
                style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
              >
                <Bug size={18} color="var(--accent-red)" />
                <h3 className="modal-title">{t('jiraModalTitle')}</h3>
              </div>
              <button
                className="btn btn-icon"
                onClick={() => setIsJiraBugModalOpen(false)}
                style={{ padding: '4px' }}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              {generatingJiraDraft ? (
                <div
                  style={{
                    padding: '40px',
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                  }}
                >
                  <Sparkles
                    size={24}
                    className="spin"
                    style={{ margin: '0 auto 12px', color: 'var(--accent-red)' }}
                  />
                  <p>{t('jiraSynthesizing')}</p>
                </div>
              ) : jiraBugDraft ? (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '14px',
                  }}
                >
                  {jiraBugResult && (
                    <div
                      style={{
                        padding: '12px 16px',
                        borderRadius: 'var(--r-xs)',
                        backgroundColor: jiraBugResult.published
                          ? 'var(--accent-green-soft)'
                          : 'var(--accent-blue-soft)',
                        border: `1px solid ${jiraBugResult.published ? 'var(--accent-green)' : 'var(--accent-blue)'}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: '13px',
                            color: jiraBugResult.published
                              ? 'var(--accent-green)'
                              : 'var(--accent-blue)',
                          }}
                        >
                          {jiraBugResult.message}
                        </div>
                        {jiraBugResult.url && (
                          <a
                            href={jiraBugResult.url}
                            target="_blank"
                            rel="noreferrer"
                            style={{
                              fontSize: '12px',
                              color: 'var(--accent-blue)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              marginTop: '4px',
                            }}
                          >
                            {t('openJiraIssue', { key: jiraBugResult.key })}{' '}
                            <ExternalLink size={12} />
                          </a>
                        )}
                      </div>
                      <span
                        className="badge badge-draft"
                        style={{ fontSize: '11px' }}
                      >
                        {jiraBugResult.status}
                      </span>
                    </div>
                  )}

                  <div className="form-group">
                    <label className="form-label">{t('issueSummary')}</label>
                    <input
                      type="text"
                      className="form-input"
                      value={jiraBugDraft.summary}
                      onChange={(e) =>
                        setJiraBugDraft({
                          ...jiraBugDraft,
                          summary: e.target.value,
                        })
                      }
                    />
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr 1fr',
                      gap: '12px',
                    }}
                  >
                    <div className="form-group">
                      <label className="form-label">{t('projectKey')}</label>
                      <input
                        type="text"
                        className="form-input"
                        value={jiraBugDraft.project_key}
                        onChange={(e) =>
                          setJiraBugDraft({
                            ...jiraBugDraft,
                            project_key: e.target.value,
                          })
                        }
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('issueType')}</label>
                      <input
                        type="text"
                        className="form-input"
                        value={jiraBugDraft.issue_type}
                        onChange={(e) =>
                          setJiraBugDraft({
                            ...jiraBugDraft,
                            issue_type: e.target.value,
                          })
                        }
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">
                        {t('common:priority')}
                      </label>
                      <select
                        className="form-select"
                        value={jiraBugDraft.priority}
                        onChange={(e) =>
                          setJiraBugDraft({
                            ...jiraBugDraft,
                            priority: e.target.value,
                          })
                        }
                      >
                        <option value="Critical">
                          {t('priorityCritical')}
                        </option>
                        <option value="High">{t('priorityHigh')}</option>
                        <option value="Medium">{t('priorityMedium')}</option>
                        <option value="Low">{t('priorityLow')}</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      {t('descriptionDiagnostics')}
                    </label>
                    <textarea
                      rows={5}
                      className="form-textarea"
                      value={jiraBugDraft.description}
                      onChange={(e) =>
                        setJiraBugDraft({
                          ...jiraBugDraft,
                          description: e.target.value,
                        })
                      }
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      {t('reproductionSteps')}
                    </label>
                    <div
                      style={{
                        background: 'var(--surface-inset)',
                        border: '1px solid var(--border-color)',
                        borderRadius: 'var(--r-xs)',
                        padding: '10px 12px',
                      }}
                    >
                      <ol
                        style={{
                          paddingLeft: '18px',
                          margin: 0,
                          fontSize: '12px',
                          color: 'var(--ink-soft)',
                        }}
                      >
                        {jiraBugDraft.steps_to_reproduce.map((st, i) => (
                          <li key={i}>{st}</li>
                        ))}
                      </ol>
                    </div>
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    padding: '30px',
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                  }}
                >
                  {t('jiraDraftFailed')}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setIsJiraBugModalOpen(false)}
              >
                {t('common:close')}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={!jiraBugDraft || creatingJiraBug}
                onClick={() => handleConfirmCreateJiraBug(false)}
              >
                {t('validateDryRun')}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!jiraBugDraft || creatingJiraBug}
                onClick={() => handleConfirmCreateJiraBug(true)}
              >
                {creatingJiraBug ? t('creatingTicket') : t('createTicket')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
