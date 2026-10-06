import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AIFailureDiagnosisResponse,
  FailureAnalysisRun,
  AITraceEvent,
  FailureCategory,
  FailureRecurrenceItem,
  FailureRecord,
  JiraBugDraft,
  JiraCreateBugResponse,
  LocatorRepairProposal,
  LocatorSemanticReviewResponse,
  Project,
  RunnerType,
  TestRun,
} from '../types';
import { api } from '../api/client';
import { AIExecutionTimeline } from '../components/AIExecutionTimeline';
import { FailureWorkflowPanel } from '../components/FailureWorkflowPanel';
import { FailureEvidence } from '../features/failures/FailureEvidence';
import { FailureOverview } from '../features/failures/FailureOverview';
import {
  displayedFailureClassification,
  deriveDiagnosisState,
  failedLocatorFromFailure,
  normalizeFailureClassification,
  primaryActionFor,
  relatedFailures,
  repairEligibility,
  summarizeFailureError,
  storedRepairProposal,
} from '../features/failures/failureWorkspaceModel';
import {
  AlertTriangle,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  ChevronRight,
  Check,
  ShieldCheck,
  History,
  Bug,
  ExternalLink,
} from 'lucide-react';

interface FailuresPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  /** Deep-link target: when set, this failure is selected once the list resolves. */
  initialFailureId?: string | null;
  /** Lets the router shell mirror row selection into the URL. */
  onSelectFailure?: (failureId: string) => void;
  /** Opens the failing test file in the Automation Studio. */
  onOpenInStudio?: (
    filePath: string,
    lineNumber?: number,
    debugNodeId?: string,
    failureContext?: { failureId: string; runId: string },
  ) => void;
  onNavigateToRuns?: (runId?: string) => void;
  /** Reuses the repair lifecycle inside Workspace while the parent owns context navigation. */
  workspaceMode?: boolean;
}

export const FailuresPage: React.FC<FailuresPageProps> = ({
  projects,
  selectedProjectId,
  initialFailureId,
  onSelectFailure,
  onOpenInStudio,
  onNavigateToRuns,
  workspaceMode = false,
}) => {
  const { t, i18n } = useTranslation('failures');
  const currentProjectId = selectedProjectId || projects[0]?.id || null;

  const [failures, setFailures] = useState<FailureRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
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
  const [selectedAnalysisId, setSelectedAnalysisId] = useState('');
  const selectedFailureIdRef = useRef<string | null>(null);
  selectedFailureIdRef.current = selectedFailure?.id ?? null;
  const diagnosisController = useRef<AbortController | null>(null);

  const restoreAnalysis = (analysis: FailureAnalysisRun) => {
    setSelectedAnalysisId(analysis.id);
    setDiagnosisEvents(analysis.events);
    setAiDiagnosis(analysis.result.diagnosis ?? null);
    setDiagnosisError('');
  };

  useEffect(() => {
    setAnalysisHistory([]);
    setSelectedAnalysisId('');
    if (!selectedFailure?.id) return;
    let active = true;
    void api
      .getFailureAnalyses(selectedFailure.id)
      .then((rows) => {
        if (!active) return;
        setAnalysisHistory(rows);
        if (rows[0] && !diagnosisController.current) restoreAnalysis(rows[0]);
      })
      .catch((error) => {
        if (active) setDiagnosisError(String(error));
      });
    return () => {
      active = false;
    };
  }, [selectedFailure?.id]);

  const selectedAnalysis = analysisHistory.find(
    (item) => item.id === selectedAnalysisId,
  );
  const trustedCompletedAnalysis = Boolean(
    selectedAnalysis?.status === 'COMPLETED' &&
      selectedAnalysis.events.some((event) => {
        const provider = event.metadata.provider;
        return (
          event.type === 'model.completed' &&
          typeof provider === 'string' &&
          provider !== 'fake' &&
          event.metadata.fallback_used !== true
        );
      }),
  );
  const verificationRunStatus = verificationRun?.status ??
    selectedAnalysis?.result.verification_run_status;
  useEffect(() => {
    if (
      !selectedFailure?.id ||
      !['QUEUED', 'RUNNING'].includes(verificationRunStatus ?? '')
    )
      return;
    let active = true;
    const timer = window.setInterval(() => {
      void api
        .getFailureAnalyses(selectedFailure.id)
        .then((rows) => {
          if (!active || diagnosisController.current) return;
          setAnalysisHistory(rows);
          const selected = rows.find((item) => item.id === selectedAnalysisId);
          if (selected) restoreAnalysis(selected);
        })
        .catch(() => undefined);
    }, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [selectedFailure?.id, selectedAnalysisId, verificationRunStatus]);

  useEffect(() => () => diagnosisController.current?.abort(), []);

  // Locator Repair Proposal State
  const [generatingProposal, setGeneratingProposal] = useState<boolean>(false);
  const [repairProposal, setRepairProposal] =
    useState<LocatorRepairProposal | null>(null);
  const [repairError, setRepairError] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState<string>('');

  // Semantic Review State
  const [reviewingSemantic, setReviewingSemantic] = useState<boolean>(false);
  const [semanticReview, setSemanticReview] =
    useState<LocatorSemanticReviewResponse | null>(null);

  // Recurrence State
  const [recurrenceList, setRecurrenceList] = useState<FailureRecurrenceItem[]>(
    [],
  );
  const [loadingRecurrence, setLoadingRecurrence] = useState<boolean>(false);

  // Jira Bug Ticket State (Phase 9)
  const [isJiraBugModalOpen, setIsJiraBugModalOpen] = useState<boolean>(false);
  const [jiraBugDraft, setJiraBugDraft] = useState<JiraBugDraft | null>(null);
  const [generatingJiraDraft, setGeneratingJiraDraft] =
    useState<boolean>(false);
  const [creatingJiraBug, setCreatingJiraBug] = useState<boolean>(false);
  const [jiraBugResult, setJiraBugResult] =
    useState<JiraCreateBugResponse | null>(null);

  const [applyingRepair, setApplyingRepair] = useState<boolean>(false);
  const [repairApplied, setRepairApplied] = useState<boolean>(false);
  const [patchedFailureIds, setPatchedFailureIds] = useState<string[]>([]);
  const repairVerified = Boolean(
    repairProposal?.execution_trace?.some(
      (event) =>
        event.type === 'verification_completed' &&
        event.metadata?.verified === true,
    ),
  );
  const repairCheck = selectedFailure
    ? repairEligibility({
        failure: selectedFailure,
        diagnosis: aiDiagnosis,
        trustedAnalysis: trustedCompletedAnalysis,
      })
    : { eligible: false, reason: 'missing-evidence' };
  const locatorRepairApplicable = repairCheck.eligible;
  const storedClassification = normalizeFailureClassification(
    selectedFailure?.failure_kind ?? selectedFailure?.classification,
  );
  const locatorRepairReason =
    repairCheck.reason === 'not-diagnosed' && storedClassification !== 'LOCATOR_CHANGED'
      ? t('locatorRepairNotApplicable', { classification: storedClassification })
      : repairCheck.reason === 'missing-locator'
      ? t('missingFailedLocator')
      : repairCheck.reason === 'not-diagnosed'
        ? t('primaryReasons.diagnosisRequired')
        : repairCheck.reason === 'untrusted-diagnosis'
          ? t('simulatedDiagnosis')
          : repairCheck.reason === 'missing-evidence'
            ? t('repairUnavailableUntilDiagnosis')
          : t('locatorRepairNotApplicable', {
              classification: normalizeFailureClassification(
                aiDiagnosis?.classification ?? selectedFailure?.classification,
              ),
            });

  const diagnosisState = selectedFailure
    ? deriveDiagnosisState({
        diagnosing,
        diagnosis: aiDiagnosis,
        repairProposed: Boolean(repairProposal),
        repairApplied,
        verificationStatus: verificationRunStatus,
        verified: selectedAnalysis?.result.verified,
        analysis: selectedAnalysis,
        error: diagnosisError,
      })
    : 'NOT_ANALYZED';
  const trustedDiagnosis = Boolean(
    aiDiagnosis && aiDiagnosis.provider !== 'fake' && !aiDiagnosis.fallback_used,
  );
  const diagnosedClassification = trustedDiagnosis
    ? aiDiagnosis?.classification
    : aiDiagnosis
      ? 'UNKNOWN'
      : undefined;
  const primaryAction = selectedFailure
    ? primaryActionFor({
        state: diagnosisState,
        classification: selectedFailure.failure_kind ?? selectedFailure.classification,
        diagnosedClassification,
        hasFailedLocator: Boolean(failedLocatorFromFailure(selectedFailure)),
      })
    : 'BLOCKED';
  const sharedFailures = selectedFailure
    ? relatedFailures(failures, selectedFailure)
    : [];
  const canRetry = Boolean(
    selectedFailure &&
      trustedDiagnosis &&
      ['LOCATOR_CHANGED', 'AUTOMATION_DEFECT', 'ENVIRONMENT', 'NETWORK', 'TIMING', 'TEST_DATA'].includes(
        normalizeFailureClassification(aiDiagnosis?.classification),
      ),
  );
  const canCreateJiraDraft = Boolean(
    trustedDiagnosis &&
      ['PRODUCT_DEFECT', 'ENVIRONMENT'].includes(
        normalizeFailureClassification(aiDiagnosis?.classification),
      ),
  );

  const [rerunning, setRerunning] = useState<boolean>(false);
  const [rerunMessage, setRerunMessage] = useState<string | null>(null);
  const primaryActionDisabled =
    ['ANALYZING', 'VERIFYING', 'VERIFIED', 'BLOCKED'].includes(primaryAction) ||
    (primaryAction === 'GENERATE_LOCATOR_REPAIR' && !locatorRepairApplicable) ||
    generatingProposal || rerunning || generatingJiraDraft;
  const showFailurePrimaryAction = !['ANALYZING', 'VERIFYING', 'VERIFIED'].includes(primaryAction);
  const primaryActionReason =
    primaryAction === 'GENERATE_LOCATOR_REPAIR' && !locatorRepairApplicable
      ? locatorRepairReason
      : primaryAction === 'BLOCKED'
    ? diagnosisState === 'DIAGNOSED' &&
        normalizeFailureClassification(aiDiagnosis?.classification) === 'AUTOMATION_DEFECT'
      ? t('primaryReasons.automationRepairUnavailable')
      : diagnosisState === 'DIAGNOSED' &&
          normalizeFailureClassification(aiDiagnosis?.classification) === 'LOCATOR_CHANGED'
        ? t('primaryReasons.locatorUnavailable')
        : t('primaryReasons.repairUnavailable')
    : undefined;
  const handleOpenFailureInStudio = async (startDebug = false) => {
    if (!selectedFailure || !onOpenInStudio) return;
    const filePath = selectedFailure.test_nodeid.split('::')[0];
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
      failureBreakpoint?.line_number,
      startDebug ? selectedFailure.test_nodeid : undefined,
      { failureId: selectedFailure.id, runId: selectedFailure.run_id },
    );
  };

  const fetchFailures = async () => {
    try {
      setLoading(true);
      const data = await api.getFailures(currentProjectId || undefined);
      setFailures(data);
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
    } finally {
      setLoading(false);
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
    setSelectedFailure(f);
    setSourceRun(null);
    setVerificationRun(null);
    setAiDiagnosis(null);
    setRepairProposal(savedRepair);
    setRepairError('');
    setSelectedCandidate(savedRepair?.proposed_locator ?? '');
    setSemanticReview(null);
    setRepairApplied(savedRepair?.applied ?? false);
    setRerunMessage(null);
    fetchRecurrence(f.id);
  };

  const fetchRecurrence = async (failureId: string) => {
    try {
      setLoadingRecurrence(true);
      const list = await api.getFailureRecurrence(failureId);
      setRecurrenceList(list);
    } catch (err) {
      console.error('Failed to fetch recurrence', err);
      setRecurrenceList([]);
    } finally {
      setLoadingRecurrence(false);
    }
  };

  const handleDiagnoseAI = async () => {
    if (!selectedFailure) return;
    diagnosisController.current?.abort();
    const controller = new AbortController();
    diagnosisController.current = controller;
    setAiDiagnosis(null);
    setDiagnosisEvents([]);
    setDiagnosisError('');
    setDiagnosing(true);
    let terminal = false;
    let analysisId = '';
    try {
      await api.streamFailureWorkflow(
        selectedFailure.id,
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
            const result = event.metadata?.diagnosis as unknown as
              AIFailureDiagnosisResponse | undefined;
            if (!result) throw new Error(t('diagnosisStreamIncomplete'));
            terminal = true;
            setAiDiagnosis(result);
          } else if (event.type === 'run.failed') {
            terminal = true;
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
      void api
        .getFailureAnalyses(selectedFailure.id)
        .then((rows) => {
          if (
            selectedFailureIdRef.current !== selectedFailure.id ||
            diagnosisController.current
          )
            return;
          setAnalysisHistory(rows);
          const saved = rows.find((item) => item.id === analysisId);
          if (saved) restoreAnalysis(saved);
        })
        .catch(() => undefined);
    }
  };

  const handleCancelDiagnosis = () => {
    diagnosisController.current?.abort();
    diagnosisController.current = null;
    setDiagnosing(false);
    setDiagnosisError(t('diagnosisCancelled'));
  };

  const handleGenerateProposal = async () => {
    if (!selectedFailure) return;
    if (!locatorRepairApplicable) {
      setRepairError(locatorRepairReason);
      return;
    }
    try {
      setGeneratingProposal(true);
      setRepairError('');
      setRepairProposal(null);
      const proposal = await api.generateRepairProposal(selectedFailure.id);
      if (
        !proposal.proposed_locator.trim() ||
        proposal.proposed_locator.trim() === proposal.old_locator.trim()
      ) {
        setRepairError(t('noAlternativeLocator'));
        return;
      }
      setRepairProposal(proposal);
      setSemanticReview(null);
      if (proposal.proposed_locator) {
        setSelectedCandidate(proposal.proposed_locator);
      }
    } catch (err: any) {
      setRepairError(t('alertProposalFailed', { error: err.message || err }));
    } finally {
      setGeneratingProposal(false);
    }
  };

  const handleSemanticReview = async () => {
    if (!selectedFailure || !repairProposal) return;
    const chosenLocator = selectedCandidate || repairProposal.proposed_locator;
    try {
      setReviewingSemantic(true);
      const review = await api.getSemanticLocatorReview(
        selectedFailure.id,
        repairProposal.old_locator,
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
      !currentProjectId ||
      !locatorRepairApplicable ||
      !repairVerified ||
      semanticReview?.is_semantically_equivalent === false
    )
      return;
    const chosenLocator = selectedCandidate || repairProposal.proposed_locator;
    if (
      !chosenLocator.trim() ||
      chosenLocator.trim() === repairProposal.old_locator.trim()
    ) {
      setRepairError(t('noAlternativeLocator'));
      return;
    }
    const filePath =
      repairProposal.file_path || selectedFailure.test_nodeid.split('::')[0];
    try {
      setApplyingRepair(true);
      // The API replaces `old_code` with `new_code` inside the workspace file, so the exact text
      // must exist: check first and say so plainly instead of sending a patch that cannot apply.
      const file = await api.readWorkspaceFile(currentProjectId, filePath);
      if (!file.content.includes(repairProposal.old_locator)) {
        alert(
          t('alertRepairLocatorNotFound', {
            file: filePath,
            locator: repairProposal.old_locator,
          }),
        );
        return;
      }

      await api.applyRepair(
        selectedFailure.id,
        {
          file_path: filePath,
          old_code: repairProposal.old_locator,
          new_code: chosenLocator,
        },
        currentProjectId,
      );
      setRepairApplied(true);
      setPatchedFailureIds((prev) =>
        prev.includes(selectedFailure.id)
          ? prev
          : [...prev, selectedFailure.id],
      );
      alert(t('alertRepairApplied', { file: filePath }));
    } catch (err: any) {
      alert(t('alertApplyRepairFailed', { error: err.message || err }));
    } finally {
      setApplyingRepair(false);
    }
  };

  const handleRerunTest = async () => {
    if (!selectedFailure || !currentProjectId || rerunning) return;
    try {
      setRerunning(true);
      setRerunMessage(t('rerunTriggering'));
      const target = selectedFailure.test_nodeid;
      const originalRun = await api.getTestRun(selectedFailure.run_id);
      const run = await api.createTestRun({
        project_id: currentProjectId,
        workspace_id: currentProjectId,
        nodeids: [target],
        parent_run_id: selectedFailure.run_id,
        origin_failure_id: selectedFailure.id,
        environment: originalRun.environment,
        browser: originalRun.browser,
        runner_type: originalRun.runner_type as RunnerType | undefined,
        runner_profile_id: originalRun.runner_profile_id,
        requested_by: `Re-run verification for failure #${selectedFailure.id.slice(0, 8)}`,
      });
      setVerificationRun(run);
      if (
        selectedAnalysisId &&
        analysisHistory.some((item) => item.id === selectedAnalysisId)
      ) {
        await api.linkFailureVerification(
          selectedFailure.id,
          selectedAnalysisId,
          run.id,
        );
        const rows = await api.getFailureAnalyses(selectedFailure.id);
        if (selectedFailureIdRef.current === selectedFailure.id) {
          setAnalysisHistory(rows);
          const selected = rows.find((item) => item.id === selectedAnalysisId);
          if (selected) restoreAnalysis(selected);
        }
      }
      setRerunMessage(
        t('rerunDispatched', { runId: run.id.slice(0, 8), status: run.status }),
      );
      if (onNavigateToRuns) {
        setTimeout(() => onNavigateToRuns(run.id), 1200);
      }
    } catch (err: any) {
      setRerunMessage(t('rerunError', { error: err.message || err }));
    } finally {
      setRerunning(false);
    }
  };

  const handleOpenJiraBugModal = async () => {
    if (!selectedFailure || !canCreateJiraDraft) return;
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
    if (primaryAction === 'RUN_DIAGNOSIS') void handleDiagnoseAI();
    else if (primaryAction === 'GENERATE_LOCATOR_REPAIR') void handleGenerateProposal();
    else if (primaryAction === 'RETRY' || primaryAction === 'VERIFY_FIX') void handleRerunTest();
    else if (primaryAction === 'CREATE_ISSUE_DRAFT') void handleOpenJiraBugModal();
    else if (primaryAction === 'REVIEW_REPAIR') document.getElementById('failure-repair-proposal')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const getCategoryBadge = (cat?: FailureCategory | string) => {
    const classification = normalizeFailureClassification(cat);
    const style =
      classification === 'LOCATOR_CHANGED'
        ? { background: 'var(--accent-violet-soft)', color: 'var(--accent-violet)' }
        : classification === 'TIMING'
          ? { background: 'var(--accent-amber-soft)', color: 'var(--accent-amber)' }
          : classification === 'ASSERTION_FAILURE' || classification === 'PRODUCT_DEFECT'
            ? { background: 'var(--accent-red-soft)', color: 'var(--accent-red)' }
            : { background: 'var(--surface-inset)', color: 'var(--ink-muted)' };
    switch (classification) {
      case 'LOCATOR_CHANGED':
      case 'TIMING':
      case 'ASSERTION_FAILURE':
      case 'ENVIRONMENT':
      case 'NETWORK':
      case 'TEST_DATA':
      case 'AUTOMATION_DEFECT':
      case 'PRODUCT_DEFECT':
      case 'UNKNOWN':
        return <span className="badge badge-draft" style={style}>{classification}</span>;
      default:
        return <span className="badge badge-draft" style={style}>{classification}</span>;
    }
  };

  return (
    <div className={workspaceMode ? 'failure-page-workspace-mode' : undefined}>
      {!workspaceMode && <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '18px',
        }}
      >
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>{t('title')}</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            {t('subtitle')}
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchFailures}>
          <RefreshCw size={14} /> {t('refresh')}
        </button>
      </div>}

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
        <div
          className="failure-workbench-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: workspaceMode ? 'minmax(0, 1fr)' : 'minmax(0, 1.2fr) minmax(0, 2fr)',
            gap: '20px',
          }}
        >
          {/* Left: compact failure queue */}
          {!workspaceMode && <section className="card failure-list-card" aria-label={t('recordedCount', { count: failures.length })}>
            <div className="card-header">
              <span className="card-title">{t('recordedCount', { count: failures.length })}</span>
            </div>
            <div className="card-body failure-list-body">
              {loading ? (
                <div className="failure-list-empty">{t('loading')}</div>
              ) : failures.length === 0 ? (
                <div className="failure-list-empty">
                  <CheckCircle2 size={32} aria-hidden="true" />
                  <strong>{t('emptyTitle')}</strong>
                  <p>{t('emptyBody')}</p>
                </div>
              ) : failures.map((failure) => {
                const isSelected = selectedFailure?.id === failure.id;
                const summary = summarizeFailureError(failure.error_message);
                const summaryText = summary === 'browserLaunchEperm'
                  ? t('summary.browserLaunch', { platform: '' })
                  : summary === 'timeout'
                    ? t('summary.timeout')
                    : summary === 'assertion'
                      ? t('summary.assertion')
                      : t('summary.generic', { detail: summary });
                return (
                  <button
                    key={failure.id}
                    type="button"
                    aria-current={isSelected ? 'true' : undefined}
                    onClick={() => {
                      handleSelectFailure(failure);
                      onSelectFailure?.(failure.id);
                    }}
                    className={`failure-select-row${isSelected ? ' is-selected' : ''}`}
                  >
                    <span className="failure-select-marker" aria-hidden="true"><AlertTriangle size={15} /></span>
                    <span className="failure-select-content">
                      <span className="failure-select-badges">
                        {getCategoryBadge(failure.classification)}
                        {patchedFailureIds.includes(failure.id) && <span className="badge">{t('patchAwaitingVerification')}</span>}
                      </span>
                      <strong>{failure.test_name || failure.test_nodeid.split('::').at(-1)}</strong>
                      <span className="failure-select-summary">{summaryText}</span>
                      <time dateTime={failure.created_at}>{new Date(failure.created_at).toLocaleString()}</time>
                    </span>
                    <ChevronRight size={16} aria-hidden="true" />
                  </button>
                );
              })}
            </div>
          </section>}

          {selectedFailure ? (
            <div className="failure-workspace-detail">
              <FailureOverview
                failure={selectedFailure}
                sourceRun={sourceRun}
                verificationRun={verificationRun}
                verificationRunId={selectedAnalysis?.result.verification_run_id}
                linkedVerificationStatus={selectedAnalysis?.result.verification_run_status}
                diagnosis={aiDiagnosis}
                state={diagnosisState}
                primaryAction={primaryAction}
                primaryDisabled={primaryActionDisabled}
                showPrimaryAction={showFailurePrimaryAction}
                primaryReason={primaryActionReason}
                onPrimaryAction={handlePrimaryAction}
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
                rerunMessage={rerunMessage}
              />
              {repairError && <div className="alert alert-error" role="alert">{repairError}</div>}

              {aiDiagnosis && (
                <section className="card failure-diagnosis-card" aria-labelledby="failure-diagnosis-heading">
                  <div className="card-header">
                    <span className="card-title" id="failure-diagnosis-heading">{t('diagnosisTitle', { classification: displayedFailureClassification(selectedFailure.classification, aiDiagnosis) })}</span>
                    <span className="failure-diagnosis-confidence">{t('confidence', { value: (aiDiagnosis.confidence * 100).toFixed(0) })}</span>
                  </div>
                  <div className="card-body">
                    {(aiDiagnosis.fallback_used || aiDiagnosis.provider === 'fake') && <p className="failure-diagnosis-warning" role="status">{t(aiDiagnosis.provider === 'fake' ? 'simulatedDiagnosis' : 'fallbackDiagnosis')}</p>}
                    <dl className="failure-diagnosis-grid">
                      <div><dt>{t('repairEligibility')}</dt><dd>{locatorRepairApplicable ? t('repairEligible') : t('repairabilityUnknown')}</dd></div>
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
              />

              {/* Locator Repair Proposal Card */}
              {locatorRepairApplicable && repairProposal && (
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
                            repairProposal.confidence === null
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
                      {repairApplied ? (
                        <span className="badge badge-ready">
                          {t('repairApplied')}
                        </span>
                      ) : (
                        <button
                          className="btn btn-secondary btn-sm"
                          disabled={applyingRepair || !repairVerified || semanticReview?.is_semantically_equivalent === false}
                          onClick={handleApplyRepair}
                        >
                          <Check size={13} />{' '}
                          {applyingRepair ? t('applying') : t('applyRepair')}
                        </button>
                      )}
                      {!repairApplied && (
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setRepairProposal(null);
                            setSelectedCandidate('');
                            setSemanticReview(null);
                          }}
                        >
                          {t('ignoreProposal')}
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
                        {t('repairNotVerified')}
                      </p>
                    )}
                    <dl className="failure-repair-facts">
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
                          running={generatingProposal}
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
                          {repairProposal.old_locator || t('unknownValue')}
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
                    <strong>{locatorRepairApplicable ? t('repairProposalNotCreated') : t('repairNotRecommended')}</strong>
                    {!locatorRepairApplicable && <p>{locatorRepairReason}</p>}
                    {locatorRepairApplicable && <p>{t('proposalFlowHint')}</p>}
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
                  failure={selectedFailure}
                  classification={selectedFailure.failure_kind ?? selectedFailure.classification}
                  error={diagnosisError}
                  primaryAction={primaryAction}
                  primaryActionDisabled={primaryActionDisabled}
                  primaryActionReason={primaryActionReason}
                  primaryActionPending={generatingProposal}
                  showPrimaryAction={!aiDiagnosis || primaryAction === 'BLOCKED'}
                  onPrimaryAction={handlePrimaryAction}
                  onOpenStudio={onOpenInStudio ? () => void handleOpenFailureInStudio() : undefined}
                  onDebug={onOpenInStudio ? () => void handleOpenFailureInStudio(true) : undefined}
                  onCancel={handleCancelDiagnosis}
                  onSelect={(id) => {
                    const analysis = analysisHistory.find((item) => item.id === id);
                    if (analysis) restoreAnalysis(analysis);
                  }}
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
                      {t('recurrenceTitle', { count: recurrenceList.length })}
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
            <div className="card failure-select-prompt">{t('selectPrompt')}</div>
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
