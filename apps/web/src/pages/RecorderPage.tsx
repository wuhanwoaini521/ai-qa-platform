import { Link } from 'react-router-dom';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RecorderApiCall } from '../features/api-cases/apiCase';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AlertTriangle, ArrowDown, ArrowUp, CirclePause, CirclePlay, Code2, Crosshair, MousePointer2, RotateCw, Save, Square, Trash2 } from 'lucide-react';
import { api, getRecorderSocketUrl } from '../api/client';
import { AIExecutionTimeline } from '../components/AIExecutionTimeline';
import { ContextTaskProgress, useContextTask } from '../components/ContextTaskProgress';
import { MonacoEditorPane, MonacoEditorInstance } from '../features/automation-studio/components/MonacoEditorPane';
import { buildWorkspaceHref } from '../app/workspaceContext';
import { EditorTab } from '../features/automation-studio/types';
import { AITraceEvent, GitDiffResult, Project, RecorderLocatorCandidate, RecorderStep, TestCasePriority, TestRunCreate } from '../types';
import { flowStartUrl, isNavigationFrameFresh, normalizeTrustedDomains } from './browserGoalModel';
import { recorderStepsFromAgent } from './recorderAgentModel';
import {
  acknowledgeRecorderNavigationCommand,
  canCloseRecorderSession,
  canStartRecorderClose,
  canStartRecorderSessionWork,
  canSendRecorderSessionCommand,
  isQueueableRecorderNavigationCommand,
  prepareNextPendingRecorderNavigationCommand,
  reconcilePendingRecorderNavigationCommands,
  isRecorderSessionAlreadyClosed,
  isRecorderCloseRetryBlocked,
  recorderBrowserCommandBlocksClose,
  recorderBrowserCommandMayNavigate,
  recorderNavigationPendingAfterCommand,
  recorderNavigationPendingAfterReconnect,
  recorderNavigationPendingAfterSnapshot,
  recorderNavigationPendingAfterError,
  recorderStepSnapshotPendingAfterCommandError,
  recorderStepSnapshotPendingAfterSnapshot,
  recorderErrorRecoveryFor,
  shouldApplyRecorderSessionCloseCleanup,
  shouldConnectRecorderSessionSocket,
  shouldReconcileRecorderCommands,
  createPendingRecorderNavigationCommand,
  tryPersistPendingRecorderNavigationCommandsForSession,
  tryRestorePendingRecorderNavigationCommandsForSession,
  type PendingRecorderNavigationCommand,
  type RecorderErrorRecovery,
} from './recorderSessionCloseModel';
import {
  acknowledgeRecorderStepCommand,
  createPendingRecorderStepCommand,
  isRetryableRecorderStepCommandError,
  PENDING_RECORDER_STEP_COMMANDS_STORAGE_VERSION,
  prepareNextPendingRecorderStepCommand,
  reconcilePendingRecorderStepSnapshot,
  tryPersistPendingRecorderStepCommands,
  tryRestorePendingRecorderStepCommands,
  type PendingRecorderStepCommand,
} from './recorderStepSyncModel';
import {
  clearRecorderRunIdempotencyKey,
  recorderRunConfigFields,
  recorderRunIdempotencyKey,
  type RecorderRunConfig,
} from './recorderRunModel';

type StepAction = RecorderStep['action'];
type RecorderSocketState = 'disconnected' | 'connecting' | 'connected' | 'closed' | 'error';
type ElementPreview = { tag?: string; id?: string; class?: string; role?: string | null; name?: string; text?: string; value_redacted?: boolean; attributes?: Record<string, string>; bounding_box?: { x: number; y: number; width: number; height: number }; frame_path?: string[]; shadow_path?: string[]; candidates?: RecorderLocatorCandidate[]; parent_summary?: string; visible?: boolean; actionable?: boolean };
type Frame = { type: string; action?: string; command_id?: string; image?: string; url?: string; title?: string; state?: string; steps?: RecorderStep[]; steps_revision?: number; applied_step_command_ids?: string[]; processed_navigation_command_ids?: string[]; settled_navigation_count?: number; code?: string; locator_trace?: AITraceEvent[]; locator_verification?: Record<string, unknown> | null; hovered?: ElementPreview | null; tabs?: Array<{index:number;url:string;title:string;active:boolean}>; picked?: (ElementPreview & { action: string; evidence?: RecorderStep['evidence']; ranked_candidates?: RecorderLocatorCandidate[]; selection?: { selected_candidate?: RecorderLocatorCandidate; summary?: RecorderStep['locator_decision'] } | null }) | null; message?: string };
type PendingAgentGoal = { goal: string; sessionId: string; startUrl: string; strategy: 'fast' | 'agent'; waitingForNavigation: boolean; trustedDomains: string[]; minimumFrameRevision?: number };

const actions: StepAction[] = ['navigate','back','scroll','click','double_click','fill','select','check','uncheck','press','hover','wait','assert_visible','assert_text','assert_url','assert_title','assert_count'];
const blankDiff: GitDiffResult = { diff: '', changed_files: [] };
const recorderPendingStepCommandsKey = (sessionId: string) =>
  `ai-qa.recorder.pending-step-commands.v${PENDING_RECORDER_STEP_COMMANDS_STORAGE_VERSION}.${sessionId}`;
const restoreStoredPendingRecorderStepCommands = (sessionId: string): { commands: PendingRecorderStepCommand[]; available: boolean } => {
  try {
    return tryRestorePendingRecorderStepCommands(window.localStorage, recorderPendingStepCommandsKey(sessionId));
  } catch {
    return { commands: [], available: false };
  }
};
const persistPendingRecorderStepCommands = (sessionId: string, commands: PendingRecorderStepCommand[]): boolean => {
  try {
    return tryPersistPendingRecorderStepCommands(window.localStorage, recorderPendingStepCommandsKey(sessionId), commands);
  } catch {
    return false;
  }
};
const restoreStoredPendingRecorderNavigationCommands = (sessionId: string) => {
  try {
    return tryRestorePendingRecorderNavigationCommandsForSession(window.sessionStorage, sessionId);
  } catch {
    return { commands: [], available: false };
  }
};
const persistPendingRecorderNavigationCommands = (sessionId: string, commands: PendingRecorderNavigationCommand[]): boolean => {
  try {
    return tryPersistPendingRecorderNavigationCommandsForSession(window.sessionStorage, sessionId, commands);
  } catch {
    return false;
  }
};
const normalizeRecorderFilePath = (path: string): string =>
  path.replaceAll(String.fromCharCode(92), '/').split('/').filter(Boolean).join('/');
const normalizeBrowserUrl = (value: string): string => {
  const target = value.trim() || 'about:blank';
  return /^(https?:|about:)/i.test(target) ? target : `https://${target}`;
};
const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
const normalizedHttpUrl = (value: string): string | null => {
  try {
    const parsed = new URL(normalizeBrowserUrl(value));
    return ['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password ? parsed.href : null;
  } catch { return null; }
};

export const RecorderPage: React.FC<{
  projects: Project[];
  selectedProjectId: string | null;
  embedded?: boolean;
  onNavigateToRuns?: (runId: string) => void;
  onOpenRecordedCase?: (savedCase: Awaited<ReturnType<typeof api.saveRecorderCase>>, filePath: string) => void;
  runConfig?: RecorderRunConfig;
}> = ({ projects, selectedProjectId, embedded = false, onNavigateToRuns, onOpenRecordedCase, runConfig }) => {
  const navigate = useNavigate();
  const { t } = useTranslation('recorder');
  const { t: workspaceT } = useTranslation('workspace');
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedSessionId = searchParams.get('session_id');
  const projectId = selectedProjectId ?? projects[0]?.id ?? null;
  const recorderErrorMessage = useCallback((error: unknown, targetUrl?: string) => {
    const message = error instanceof Error ? error.message : String(error);
    return message.includes('ERR_NETWORK_ACCESS_DENIED')
      ? t('errors.networkAccessDenied', { target: targetUrl ? `“${targetUrl}”` : t('errors.targetWebsite') })
      : message;
  }, [t]);
  const actionLabel = (action: StepAction) => t(`actions.${action}`);
  const [url, setUrl] = useState('about:blank');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const activeSessionIdRef = useRef(sessionId);
  const setActiveSessionId = useCallback((nextSessionId: string | null) => {
    activeSessionIdRef.current = nextSessionId;
    setSessionId(nextSessionId);
  }, []);
  const [restoreCheckedProjectId, setRestoreCheckedProjectId] = useState<string | null>(null);
  const [socketState, setSocketState] = useState<RecorderSocketState>('disconnected');
  const [socketDetail, setSocketDetail] = useState('');
  const [socketAttempt, setSocketAttempt] = useState(0);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [steps, setSteps] = useState<RecorderStep[]>([]);
  const [optimization, setOptimization] = useState<Awaited<ReturnType<typeof api.optimizeRecorder>> | null>(null);
  const [previewMode, setPreviewMode] = useState<'raw' | 'optimized'>('raw');
  const previewDrafts = useRef({ raw: '', optimized: '' });
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setErrorState] = useState('');
  const [errorRecovery, setErrorRecovery] = useState<RecorderErrorRecovery | null>(null);
  const [stepOutboxStorageUnavailable, setStepOutboxStorageUnavailable] = useState(false);
  const stepOutboxStorageUnavailableRef = useRef(false);
  const [navigationOutboxStorageUnavailable, setNavigationOutboxStorageUnavailable] = useState(false);
  const navigationOutboxStorageUnavailableRef = useRef(false);
  const setStepOutboxStorageAvailability = useCallback((available: boolean) => {
    const unavailable = !available;
    stepOutboxStorageUnavailableRef.current = unavailable;
    setStepOutboxStorageUnavailable(unavailable);
  }, []);
  const setNavigationOutboxStorageAvailability = useCallback((available: boolean) => {
    const unavailable = !available;
    navigationOutboxStorageUnavailableRef.current = unavailable;
    setNavigationOutboxStorageUnavailable(unavailable);
  }, []);
  const setError = useCallback((message: string, requestedRecovery?: RecorderErrorRecovery, preserveCloseRecovery = false) => {
    setErrorState(message);
    setErrorRecovery((current) => recorderErrorRecoveryFor(message, requestedRecovery, current, preserveCloseRecovery));
  }, []);
  const persistRecorderOutbox = useCallback((targetSessionId: string, commands: PendingRecorderStepCommand[]) => {
    const available = persistPendingRecorderStepCommands(targetSessionId, commands);
    setStepOutboxStorageAvailability(available);
    return available;
  }, [setStepOutboxStorageAvailability]);
  const persistRecorderNavigationOutbox = useCallback((targetSessionId: string, commands: PendingRecorderNavigationCommand[]) => {
    const available = persistPendingRecorderNavigationCommands(targetSessionId, commands);
    setNavigationOutboxStorageAvailability(available);
    return available;
  }, [setNavigationOutboxStorageAvailability]);
  const [closePending, setClosePending] = useState(false);
  const [pendingBrowserCommands, setPendingBrowserCommands] = useState(0);
  const [navigationPending, setNavigationPending] = useState(false);
  const closeInFlightSessionRef = useRef<string | null>(null);
  const closedSessionRef = useRef<string | null>(null);
  const recorderSessionWorkAllowed = canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current);
  const [caseName, setCaseName] = useState(() => t('defaults.caseName'));
  const [requirement, setRequirement] = useState('');
  const [browserStrategy, setBrowserStrategy] = useState<'fast' | 'agent'>('agent');
  const [trustedDomainsText, setTrustedDomainsText] = useState('');
  const [filePath, setFilePath] = useState('tests/test_recorded_case.py');
  const [testName, setTestName] = useState('test_recorded_case');
  const [suiteName, setSuiteName] = useState(() => t('defaults.suiteName'));
  const [tagsText, setTagsText] = useState('recorder');
  const [markersText, setMarkersText] = useState('');
  const [apiCalls, setApiCalls] = useState<RecorderApiCall[]>([]);
  const [apiCallsBusy, setApiCallsBusy] = useState(false);
  const [apiCallsError, setApiCallsError] = useState('');
  const [apiCallSaving, setApiCallSaving] = useState<string | null>(null);
  const [apiCallMessage, setApiCallMessage] = useState('');
  const [apiCallCaseId, setApiCallCaseId] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [variables, setVariables] = useState<{ name: string; default: string; source: string; hint?: string }[]>([]);
  const [scriptGeneration, setScriptGeneration] = useState(0);
  const [editorReady, setEditorReady] = useState(false);
  const [showCodeFallback, setShowCodeFallback] = useState(false);
  const [exploreMobilePanel, setExploreMobilePanel] = useState<'browser' | 'task'>('browser');
  const [naturalFlowOpen, setNaturalFlowOpen] = useState(() => embedded && window.matchMedia('(max-width: 820px)').matches);
  const [pendingAgentGoal, setPendingAgentGoal] = useState<PendingAgentGoal | null>(null);
  const [agentScriptSource, setAgentScriptSource] = useState<{ taskId: string; actionCount: number; jevCount: number; assertionCount: number } | null>(null);
  const [pickTargetStep, setPickTargetStep] = useState<string | null>(null);
  const [selectionMode, setSelectionMode] = useState(false);
  const [pickedElement, setPickedElement] = useState<Frame['picked']>(null);
  const [aiAnalysisStep, setAiAnalysisStep] = useState<string | null>(null);
  const [jevDecisionStep, setJevDecisionStep] = useState<string | null>(null);
  const locatorAnalysisBusy = aiAnalysisStep !== null || jevDecisionStep !== null;
  const [locatorTraceEvents, setLocatorTraceEvents] = useState<AITraceEvent[]>([]);
  const pickTargetStepRef = useRef<string | null>(null);
  const [priority, setPriority] = useState<TestCasePriority>('P2');
  const aiTask = useContextTask(projectId, 'recorder', sessionId);

  useEffect(() => {
    if (!sessionId) {
      setApiCalls([]);
      return;
    }
    let alive = true;
    const load = async () => {
      try {
        const result = await api.getRecorderApiCalls(sessionId);
        if (alive) {
          setApiCalls(result.calls);
          setApiCallsError('');
        }
      } catch (reason) {
        if (alive) setApiCallsError(String(reason));
      }
    };
    void load();
    const timer = window.setInterval(load, 5000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [sessionId]);

  const saveApiCall = async (call: RecorderApiCall) => {
    if (!projectId) return;
    setApiCallSaving(call.id);
    setApiCallMessage('');
    try {
      const saved = await api.saveRecorderApiCase(sessionId as string, call.id);
      setApiCallCaseId(saved.test_case.id);
      setApiCallMessage(t('apiCalls.saved', { path: saved.file_path }));
    } catch (reason) {
      setApiCallMessage(t('apiCalls.saveFailed', { reason: String(reason) }));
    } finally {
      setApiCallSaving(null);
    }
  };
  const agentTaskRunning = Boolean(aiTask.task && !['COMPLETED','FAILED','BLOCKED','CANCELLED'].includes(aiTask.task.status));
  const closeAllowed = canCloseRecorderSession({
    closePending,
    pageBusy: busy || pendingBrowserCommands > 0 || navigationPending || stepOutboxStorageUnavailable || navigationOutboxStorageUnavailable,
    taskStarting: aiTask.busy,
    taskRunning: agentTaskRunning,
    agentGoalPending: Boolean(pendingAgentGoal),
    locatorAnalysisBusy,
  });
  const closeRetryBlocked = isRecorderCloseRetryBlocked(sessionId, errorRecovery, closeAllowed);
  const wsRef = useRef<WebSocket | null>(null);
  const wsSessionIdRef = useRef<string | null>(null);
  const socketReadyRef = useRef(false);
  const pendingNavigationSnapshotsRef = useRef(0);
  const pendingNavigationCommandsRef = useRef<PendingRecorderNavigationCommand[]>([]);
  const navigationCommandInFlightRef = useRef(false);
  const pendingCanonicalStepSnapshotsRef = useRef(0);
  const pendingStepCommandsRef = useRef<PendingRecorderStepCommand[]>([]);
  const sentStepCommandIdsRef = useRef<Set<string>>(new Set());
  const lastStepsRevisionRef = useRef<number | null>(null);
  const frameRevisionRef = useRef(0);
  const urlInputRef = useRef<HTMLInputElement | null>(null);
  const pendingUrlRef = useRef<string | null>(null);
  const browserRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<MonacoEditorInstance | null>(null);
  const stepStorageKey = sessionId ? `ai-qa.recorder.steps.${sessionId}` : '';
  const projectStepsKey = projectId ? `ai-qa.recorder.draft-steps.${projectId}` : '';
  const projectCodeKey = projectId ? `ai-qa.recorder.code.${projectId}` : '';
  const tab = useMemo<EditorTab | undefined>(() => code ? ({ path: filePath, name: filePath.split('/').pop() || 'test.py', content: code, initialContent: code, isDirty: false }) : undefined, [code, filePath]);

  const flushNextPendingRecorderStepCommand = useCallback(() => {
    const socket = wsRef.current;
    if (
      stepOutboxStorageUnavailableRef.current
      || !socketReadyRef.current
      || socket?.readyState !== WebSocket.OPEN
    ) return;

    const pendingBefore = pendingStepCommandsRef.current;
    const prepared = prepareNextPendingRecorderStepCommand(
      pendingBefore,
      sentStepCommandIdsRef.current,
      lastStepsRevisionRef.current,
    );
    pendingStepCommandsRef.current = prepared.pending;
    if (sessionId && (
      pendingBefore.length !== prepared.pending.length
      || pendingBefore.some((command, index) => command !== prepared.pending[index])
    ) && !persistRecorderOutbox(sessionId, prepared.pending)) return;
    if (!prepared.command) return;
    try {
      socket.send(JSON.stringify(prepared.command));
      sentStepCommandIdsRef.current.add(prepared.command.command_id);
    } catch { /* keep the command pending for the next socket snapshot */ }
  }, [sessionId, persistRecorderOutbox]);

  const flushNextPendingRecorderNavigationCommand = useCallback(() => {
    const socket = wsRef.current;
    if (
      navigationOutboxStorageUnavailableRef.current
      || !socketReadyRef.current
      || socket?.readyState !== WebSocket.OPEN
      || navigationCommandInFlightRef.current
    ) return;
    const prepared = prepareNextPendingRecorderNavigationCommand(
      pendingNavigationCommandsRef.current,
      navigationCommandInFlightRef.current,
    );
    const command = prepared.command;
    if (!command) return;
    try {
      socket.send(JSON.stringify({ action: command.action, ...command.payload, command_id: command.command_id }));
      navigationCommandInFlightRef.current = true;
    } catch { /* retain the unsent navigation for the next connection */ }
  }, []);

  useEffect(() => {
    if (!scriptGeneration || !editorReady) return;
    editorRef.current?.setPosition({ lineNumber: 1, column: 1 });
    editorRef.current?.setScrollPosition({ scrollTop: 0, scrollLeft: 0 });
  }, [scriptGeneration, editorReady]);

  useEffect(() => {
    if (!code) { setEditorReady(false); setShowCodeFallback(false); return; }
    setShowCodeFallback(false);
    const timer = window.setTimeout(() => { if (!editorRef.current) setShowCodeFallback(true); }, 2500);
    return () => window.clearTimeout(timer);
  }, [code]);

  useEffect(() => {
    if (!projectId || sessionId || requestedSessionId) return;
    try {
      const savedSteps = window.localStorage.getItem(`ai-qa.recorder.draft-steps.${projectId}`);
      if (savedSteps) setSteps(JSON.parse(savedSteps) as RecorderStep[]);
      const savedCode = window.localStorage.getItem(`ai-qa.recorder.code.${projectId}`);
      if (savedCode) setCode(savedCode);
    } catch { /* ignore damaged local drafts and restore the session below */ }
    const storedId = window.localStorage.getItem(`ai-qa.recorder.session.${projectId}`);
    if (!storedId) { setRestoreCheckedProjectId(projectId); return; }
    try {
      const savedSteps = window.localStorage.getItem(`ai-qa.recorder.steps.${storedId}`);
      if (savedSteps) setSteps(JSON.parse(savedSteps) as RecorderStep[]);
    } catch { /* ignore damaged local drafts and restore the session below */ }
    let active = true;
    api.getRecorderSession(storedId).then((saved) => {
      if (!active || saved.project_id !== projectId) return;
      setActiveSessionId(saved.id);
      setSteps(saved.steps);
      if (saved.navigation_error) {
        pendingUrlRef.current = saved.requested_url;
        setUrl(saved.requested_url);
        setError(recorderErrorMessage(saved.navigation_error, saved.requested_url));
      } else setUrl(saved.url);
      setRecording(saved.state === 'RECORDING');
    }).catch(() => window.localStorage.removeItem(`ai-qa.recorder.session.${projectId}`)).finally(() => { if (active) setRestoreCheckedProjectId(projectId); });
    return () => { active = false; };
  }, [projectId, requestedSessionId, sessionId, recorderErrorMessage]);

  useEffect(() => {
    if (!projectId || !requestedSessionId || sessionId === requestedSessionId) return;
    let active = true;
    void api.getRecorderSession(requestedSessionId).then((saved) => {
      if (!active) return;
      if (saved.project_id !== projectId) {
        setError(t('errors.sessionWrongProject'));
        return;
      }
      setActiveSessionId(saved.id);
      setSteps(saved.steps);
      setUrl(saved.navigation_error ? saved.requested_url : saved.url);
      setError(saved.navigation_error ? recorderErrorMessage(saved.navigation_error, saved.requested_url) : '');
      setRecording(saved.state === 'RECORDING');
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : String(cause));
    });
    return () => { active = false; };
  }, [projectId, requestedSessionId, sessionId, recorderErrorMessage, t]);

  useEffect(() => {
    if (!sessionId) { socketReadyRef.current = false; return; }
    let active = true;
    let socket: WebSocket | null = null;
    const canUseSessionSocket = () => shouldConnectRecorderSessionSocket(
      sessionId,
      active,
      closeInFlightSessionRef.current,
      closedSessionRef.current,
    );
    if (!canUseSessionSocket()) return;
    socketReadyRef.current = false;
    lastStepsRevisionRef.current = null;
    sentStepCommandIdsRef.current.clear();
    setSocketState('connecting');
    setSocketDetail('');
    void Promise.all([
      getRecorderSocketUrl(sessionId),
      api.createStreamTicket('recorder', sessionId),
    ]).then(([url, streamTicket]) => {
      if (!canUseSessionSocket()) return;
      const ws = new WebSocket(url);
      socket = ws;
      wsRef.current = ws;
      wsSessionIdRef.current = sessionId;
      ws.onopen = () => {
        if (!canUseSessionSocket()) {
          ws.close(1000);
          if (wsRef.current === ws) {
            wsRef.current = null;
            wsSessionIdRef.current = null;
          }
          return;
        }
        ws.send(JSON.stringify({ type: 'auth', stream_ticket: streamTicket }));
        setSocketState('connecting');
        setSocketDetail('');
      };
      ws.onclose = (event) => {
        if (!canUseSessionSocket()) return;
        socketReadyRef.current = false;
        navigationCommandInFlightRef.current = false;
        if (wsRef.current === ws) {
          wsRef.current = null;
          wsSessionIdRef.current = null;
        }
        setSocketState(event.code === 1000 ? 'closed' : 'error');
        setSocketDetail(event.code === 1000 ? '' : t('connection.interrupted', { code: event.code }));
      };
      ws.onerror = () => {
        if (!canUseSessionSocket()) return;
        socketReadyRef.current = false;
        setSocketState('error');
        setSocketDetail(t('connection.error'));
      };
      ws.onmessage = (event) => {
      if (!canUseSessionSocket()) return;
      const data = JSON.parse(event.data) as Frame;
      const pendingNavigationBeforeSnapshot = pendingNavigationCommandsRef.current;
      pendingNavigationCommandsRef.current = reconcilePendingRecorderNavigationCommands(
        pendingNavigationBeforeSnapshot,
        data.processed_navigation_command_ids ?? [],
      );
      const navigationOutboxChanged = pendingNavigationBeforeSnapshot.length !== pendingNavigationCommandsRef.current.length;
      if (sessionId && (navigationOutboxChanged || navigationOutboxStorageUnavailableRef.current)) {
        persistRecorderNavigationOutbox(sessionId, pendingNavigationCommandsRef.current);
      }
      const reconciling = shouldReconcileRecorderCommands(socketReadyRef.current, data.type);
      const pendingBeforeSnapshot = pendingStepCommandsRef.current;
      const stepReconciliation = reconcilePendingRecorderStepSnapshot(
        data,
        pendingBeforeSnapshot,
        sentStepCommandIdsRef.current,
      );
      pendingStepCommandsRef.current = stepReconciliation.pending;
      if (
        pendingBeforeSnapshot.length !== stepReconciliation.pending.length
        || pendingBeforeSnapshot.some((command, index) => command !== stepReconciliation.pending[index])
      ) {
        persistRecorderOutbox(sessionId, stepReconciliation.pending);
      }
      if (typeof data.steps_revision === 'number') lastStepsRevisionRef.current = data.steps_revision;
      if (stepReconciliation.steps !== undefined) setSteps(stepReconciliation.steps);
      const pendingCanonicalBefore = pendingCanonicalStepSnapshotsRef.current;
      pendingCanonicalStepSnapshotsRef.current = recorderStepSnapshotPendingAfterSnapshot(
        pendingCanonicalBefore,
        Array.isArray(data.steps),
      );
      const settledCanonicalSnapshots = pendingCanonicalBefore - pendingCanonicalStepSnapshotsRef.current;
      if (reconciling) {
        socketReadyRef.current = true;
        setSocketState('connected');
        setSocketDetail('');
        setPendingBrowserCommands(
          pendingStepCommandsRef.current.length
            + pendingCanonicalStepSnapshotsRef.current
            + pendingNavigationCommandsRef.current.length,
        );
        pendingNavigationSnapshotsRef.current = recorderNavigationPendingAfterReconnect(
          pendingNavigationCommandsRef.current.length,
          data.type,
        );
        setNavigationPending(pendingNavigationSnapshotsRef.current > 0);
      } else if (settledCanonicalSnapshots > 0) {
        setPendingBrowserCommands((pending) => Math.max(0, pending - settledCanonicalSnapshots));
      }
      if (socketReadyRef.current) {
        flushNextPendingRecorderStepCommand();
        flushNextPendingRecorderNavigationCommand();
      }
      if (
        reconciling
        && data.type !== 'error'
        && !pendingNavigationCommandsRef.current.some((command) => command.action === 'navigate')
      ) pendingUrlRef.current = null;
      if (data.type === 'frame') {
        pendingNavigationSnapshotsRef.current = recorderNavigationPendingAfterSnapshot(
          pendingNavigationSnapshotsRef.current,
          data.type,
          data.settled_navigation_count ?? 0,
        );
        setNavigationPending(pendingNavigationSnapshotsRef.current > 0);
        frameRevisionRef.current += 1;
        setFrame(data);
        if (data.locator_trace?.length) {
          setLocatorTraceEvents((current) => current[0]?.event_id === data.locator_trace?.[0]?.event_id ? current : data.locator_trace ?? []);
        }
        if (data.picked) setPickedElement(data.picked);
        if (data.picked) setSelectionMode(false);
        if (data.picked && pickTargetStepRef.current) {
          const recommended = data.picked.selection?.selected_candidate;
          const best = recommended?.verification?.verified ? recommended : data.picked.ranked_candidates?.find((candidate) => candidate.verification?.verified);
          if (best) {
            setCode('');
            setSteps((current) => current.map((step) => {
              if (step.id !== pickTargetStepRef.current) return step;
              const updated = { ...step, locator: best, frame_path: data.picked?.frame_path || [], locator_decision: data.picked?.selection?.summary ?? null, evidence: data.picked?.evidence ?? step.evidence };
              send('edit_step', { step: updated });
              return updated;
            }));
          }
          pickTargetStepRef.current = null;
          setPickTargetStep(null);
        }
        if (data.url && !pendingUrlRef.current && document.activeElement !== urlInputRef.current) setUrl(data.url);
        if (data.state) setRecording(data.state === 'RECORDING');
      } else if (data.type === 'navigating') {
        pendingNavigationSnapshotsRef.current = Math.max(1, pendingNavigationSnapshotsRef.current);
        setNavigationPending(true);
        if (data.url && !pendingUrlRef.current && document.activeElement !== urlInputRef.current) setUrl(data.url);
      } else if (data.type === 'command_success') {
        if (typeof data.steps_revision === 'number') lastStepsRevisionRef.current = data.steps_revision;
        if (data.command_id) {
          pendingStepCommandsRef.current = acknowledgeRecorderStepCommand(pendingStepCommandsRef.current, data.command_id);
          persistRecorderOutbox(sessionId, pendingStepCommandsRef.current);
          sentStepCommandIdsRef.current.delete(data.command_id);
        }
        if (data.action && recorderBrowserCommandBlocksClose(data.action)) {
          setPendingBrowserCommands((pending) => Math.max(0, pending - 1));
        }
        if (data.action && isQueueableRecorderNavigationCommand(data.action)) {
          pendingNavigationCommandsRef.current = acknowledgeRecorderNavigationCommand(
            pendingNavigationCommandsRef.current,
            data.command_id,
          );
          persistRecorderNavigationOutbox(sessionId, pendingNavigationCommandsRef.current);
          navigationCommandInFlightRef.current = false;
        }
        if (data.action === 'navigate') {
          const nextQueuedUrl = [...pendingNavigationCommandsRef.current].reverse().find((command) =>
            command.action === 'navigate' && typeof command.payload.url === 'string'
          )?.payload.url;
          if (typeof nextQueuedUrl === 'string') {
            pendingUrlRef.current = nextQueuedUrl;
            setUrl(nextQueuedUrl);
          } else {
            pendingUrlRef.current = null;
            if (data.url) setUrl(data.url);
          }
          setError('');
          setPendingAgentGoal((pending) => pending?.sessionId === sessionId && pending.waitingForNavigation
            ? { ...pending, waitingForNavigation: false, minimumFrameRevision: frameRevisionRef.current + 1 }
            : pending);
        }
        flushNextPendingRecorderStepCommand();
        flushNextPendingRecorderNavigationCommand();
      } else if (data.type === 'command_error') {
        if (data.command_id) {
          if (!isRetryableRecorderStepCommandError(data.action, data.code)) {
            pendingStepCommandsRef.current = acknowledgeRecorderStepCommand(pendingStepCommandsRef.current, data.command_id);
          }
          persistRecorderOutbox(sessionId, pendingStepCommandsRef.current);
          sentStepCommandIdsRef.current.delete(data.command_id);
        }
        const pendingCanonicalBefore = pendingCanonicalStepSnapshotsRef.current;
        pendingCanonicalStepSnapshotsRef.current = data.action
          ? recorderStepSnapshotPendingAfterCommandError(pendingCanonicalBefore, data.action)
          : pendingCanonicalBefore;
        const stepCommandRejected = pendingCanonicalStepSnapshotsRef.current > pendingCanonicalBefore;
        if (!data.action || (recorderBrowserCommandBlocksClose(data.action) && !stepCommandRejected)) {
          setPendingBrowserCommands((pending) => Math.max(0, pending - 1));
        }
        if (data.action && isQueueableRecorderNavigationCommand(data.action)) {
          pendingNavigationCommandsRef.current = acknowledgeRecorderNavigationCommand(
            pendingNavigationCommandsRef.current,
            data.command_id,
          );
          persistRecorderNavigationOutbox(sessionId, pendingNavigationCommandsRef.current);
          navigationCommandInFlightRef.current = false;
        }
        if (data.action && recorderBrowserCommandMayNavigate(data.action)) {
          pendingNavigationSnapshotsRef.current = recorderNavigationPendingAfterError(pendingNavigationSnapshotsRef.current, data.action);
          setNavigationPending(pendingNavigationSnapshotsRef.current > 0);
        }
        // The following serialized snapshot, not the command error, confirms navigation has settled.
        const nextQueuedUrl = [...pendingNavigationCommandsRef.current].reverse().find((command) =>
          command.action === 'navigate' && typeof command.payload.url === 'string'
        )?.payload.url;
        if (typeof nextQueuedUrl === 'string') pendingUrlRef.current = nextQueuedUrl;
        else if (data.url) pendingUrlRef.current = data.url;
        setPendingAgentGoal((pending) => pending?.sessionId === sessionId ? null : pending);
        if (!isRetryableRecorderStepCommandError(data.action, data.code)) {
          setError(recorderErrorMessage(data.message || t('errors.browserOperationFailed'), data.url));
        }
      } else if (data.type === 'error') {
        pendingNavigationSnapshotsRef.current = recorderNavigationPendingAfterSnapshot(
          pendingNavigationSnapshotsRef.current,
          data.type,
          data.settled_navigation_count ?? 0,
        );
        setNavigationPending(pendingNavigationSnapshotsRef.current > 0);
        setPendingAgentGoal((pending) => pending?.sessionId === sessionId ? null : pending);
        setError(recorderErrorMessage(data.message || t('errors.browserOperationFailed'), data.url), undefined, true);
      }
      if (['frame', 'navigating', 'error'].includes(data.type)) {
        flushNextPendingRecorderNavigationCommand();
      }
      };
    }).catch((error) => {
      if (canUseSessionSocket()) {
        setSocketState('error');
        setSocketDetail(error instanceof Error ? error.message : t('connection.error'));
      }
    });
    return () => {
      active = false;
      socketReadyRef.current = false;
      navigationCommandInFlightRef.current = false;
      socket?.close();
      if (wsRef.current === socket) {
        wsRef.current = null;
        wsSessionIdRef.current = null;
      }
    };
  }, [sessionId, socketAttempt, recorderErrorMessage, t, flushNextPendingRecorderStepCommand, flushNextPendingRecorderNavigationCommand, persistRecorderOutbox, persistRecorderNavigationOutbox]);

  useEffect(() => {
    frameRevisionRef.current = 0;
    lastStepsRevisionRef.current = null;
    socketReadyRef.current = false;
    pendingNavigationSnapshotsRef.current = 0;
    navigationCommandInFlightRef.current = false;
    pendingCanonicalStepSnapshotsRef.current = 0;
    const restoredSteps = sessionId
      ? restoreStoredPendingRecorderStepCommands(sessionId)
      : { commands: [], available: true };
    const restoredNavigation = sessionId
      ? restoreStoredPendingRecorderNavigationCommands(sessionId)
      : { commands: [], available: true };
    pendingStepCommandsRef.current = restoredSteps.commands;
    pendingNavigationCommandsRef.current = restoredNavigation.commands;
    sentStepCommandIdsRef.current.clear();
    setPendingBrowserCommands(restoredSteps.commands.length + restoredNavigation.commands.length);
    setStepOutboxStorageAvailability(restoredSteps.available);
    setNavigationOutboxStorageAvailability(restoredNavigation.available);
    setNavigationPending(!restoredNavigation.available);
    setFrame(null);
    setPickedElement(null);
    setSelectionMode(false);
    setLocatorTraceEvents([]);
  }, [sessionId, setStepOutboxStorageAvailability, setNavigationOutboxStorageAvailability]);

  useEffect(() => {
    if (!projectId) return;
    const key = `ai-qa.recorder.session.${projectId}`;
    if (sessionId) window.localStorage.setItem(key, sessionId);
  }, [projectId, sessionId]);

  useEffect(() => {
    if (!stepStorageKey) return;
    try { window.localStorage.setItem(stepStorageKey, JSON.stringify(steps)); } catch { /* keep current editor state */ }
  }, [steps, stepStorageKey]);

  useEffect(() => {
    if (!projectId || restoreCheckedProjectId !== projectId || !projectStepsKey) return;
    try { window.localStorage.setItem(projectStepsKey, JSON.stringify(steps)); } catch { /* local recovery is best effort */ }
  }, [steps, projectId, projectStepsKey, restoreCheckedProjectId]);

  useEffect(() => {
    if (projectCodeKey && code) window.localStorage.setItem(projectCodeKey, code);
  }, [code, projectCodeKey]);

  const send = useCallback((action: string, payload: Record<string, unknown> = {}) => {
    if (!canSendRecorderSessionCommand(sessionId, closeInFlightSessionRef.current)) return;
    const commandPayload = action === 'replace_steps' && lastStepsRevisionRef.current !== null
      ? { ...payload, base_steps_revision: lastStepsRevisionRef.current }
      : payload;
    const pendingCommand = createPendingRecorderStepCommand(crypto.randomUUID(), action, commandPayload);
    if (pendingCommand) {
      if (!sessionId) return;
      const pendingBefore = pendingStepCommandsRef.current;
      let nextPending = [...pendingBefore, pendingCommand];
      if (stepOutboxStorageUnavailableRef.current) {
        const restored = restoreStoredPendingRecorderStepCommands(sessionId);
        if (!restored.available) {
          pendingStepCommandsRef.current = nextPending;
          setPendingBrowserCommands((pending) => pending + 1);
          setStepOutboxStorageAvailability(false);
          return;
        }
        const seenCommandIds = new Set<string>();
        nextPending = [...restored.commands, ...nextPending].filter((command) => {
          if (seenCommandIds.has(command.command_id)) return false;
          seenCommandIds.add(command.command_id);
          return true;
        });
      }
      pendingStepCommandsRef.current = nextPending;
      setPendingBrowserCommands((pending) => pending + nextPending.length - pendingBefore.length);
      if (!persistRecorderOutbox(sessionId, nextPending)) return;
      flushNextPendingRecorderStepCommand();
      return;
    }
    if (isQueueableRecorderNavigationCommand(action)) {
      if (!sessionId) return;
      const command = createPendingRecorderNavigationCommand(crypto.randomUUID(), action, commandPayload);
      if (!command) return;
      let pendingBefore = pendingNavigationCommandsRef.current;
      const pendingCountBefore = pendingBefore.length;
      if (navigationOutboxStorageUnavailableRef.current) {
        const restored = restoreStoredPendingRecorderNavigationCommands(sessionId);
        if (!restored.available) return;
        const seenCommandIds = new Set<string>();
        pendingBefore = [...restored.commands, ...pendingBefore].filter((pending) => {
          if (seenCommandIds.has(pending.command_id)) return false;
          seenCommandIds.add(pending.command_id);
          return true;
        });
      }
      const nextPending = [...pendingBefore, command];
      if (!persistRecorderNavigationOutbox(sessionId, nextPending)) {
        if (action === 'navigate') pendingUrlRef.current = null;
        return;
      }
      pendingNavigationCommandsRef.current = nextPending;
      setPendingBrowserCommands((pending) => pending + nextPending.length - pendingCountBefore);
      pendingNavigationSnapshotsRef.current = recorderNavigationPendingAfterCommand(pendingNavigationSnapshotsRef.current, action);
      setNavigationPending(true);
      flushNextPendingRecorderNavigationCommand();
      return;
    }
    const command = { action, ...commandPayload };
    const ws = wsRef.current;
    if (!socketReadyRef.current || ws?.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(JSON.stringify(command));
      if (recorderBrowserCommandBlocksClose(action)) {
        setPendingBrowserCommands((pending) => pending + 1);
      }
      if (recorderBrowserCommandMayNavigate(action)) {
        pendingNavigationSnapshotsRef.current = recorderNavigationPendingAfterCommand(pendingNavigationSnapshotsRef.current, action);
        setNavigationPending(true);
      }
    } catch { /* browser command is not retried after ambiguous delivery */ }
  }, [sessionId, flushNextPendingRecorderStepCommand, flushNextPendingRecorderNavigationCommand, persistRecorderOutbox, persistRecorderNavigationOutbox, setStepOutboxStorageAvailability]);

  const createSession = async () => {
    if (closeInFlightSessionRef.current) return;
    if (!projectId) { setError(t('errors.noProject')); return; }
    const startUrl = normalizeBrowserUrl(url);
    setUrl(startUrl);
    setBusy(true); setError('');
    try {
      const created = await api.createRecorderSession(projectId, startUrl, steps);
      setActiveSessionId(created.id); setRecording(false);
      if (created.navigation_error) {
        pendingUrlRef.current = created.requested_url;
        setError(recorderErrorMessage(created.navigation_error, created.requested_url));
      } else pendingUrlRef.current = null;
    } catch (e) { setError(recorderErrorMessage(e, startUrl)); }
    finally { setBusy(false); }
  };

  const closeSession = async () => {
    if (!canStartRecorderClose(sessionId, closeInFlightSessionRef.current) || !closeAllowed) return;
    const closingSessionId = sessionId;
    closeInFlightSessionRef.current = closingSessionId;
    socketReadyRef.current = false;
    setClosePending(true);
    setError('');

    try {
      await api.closeRecorderSession(closingSessionId);
    } catch (closeError) {
      if (!isRecorderSessionAlreadyClosed(closeError)) {
        closeInFlightSessionRef.current = null;
        if (shouldApplyRecorderSessionCloseCleanup(activeSessionIdRef.current, closingSessionId)) {
          setError(recorderErrorMessage(closeError), 'close');
          setSocketAttempt((attempt) => attempt + 1);
        }
        setClosePending(false);
        return;
      }
    }

    closedSessionRef.current = closingSessionId;
    const socket = wsRef.current;
    if (socket && wsSessionIdRef.current === closingSessionId) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.close(1000);
      wsRef.current = null;
      wsSessionIdRef.current = null;
    }
    if (projectId) {
      const storageKey = `ai-qa.recorder.session.${projectId}`;
      try {
        if (window.localStorage.getItem(storageKey) === closingSessionId) window.localStorage.removeItem(storageKey);
      } catch { /* closed session state is authoritative */ }
    }
    setSearchParams((current) => {
      if (current.get('session_id') !== closingSessionId) return current;
      const next = new URLSearchParams(current);
      next.delete('session_id');
      return next;
    }, { replace: true });
    persistPendingRecorderStepCommands(closingSessionId, []);
    persistPendingRecorderNavigationCommands(closingSessionId, []);

    if (shouldApplyRecorderSessionCloseCleanup(activeSessionIdRef.current, closingSessionId)) {
      pendingUrlRef.current = null;
      pendingStepCommandsRef.current = [];
      sentStepCommandIdsRef.current.clear();
      pendingNavigationSnapshotsRef.current = 0;
      pendingNavigationCommandsRef.current = [];
      navigationCommandInFlightRef.current = false;
      pendingCanonicalStepSnapshotsRef.current = 0;
      setPendingBrowserCommands(0);
      setNavigationPending(false);
      setActiveSessionId(null);
      setPendingAgentGoal(null);
      setFrame(null);
      setRecording(false);
      setSocketState('disconnected');
      setSocketDetail('');
      setError('');
    }
    closeInFlightSessionRef.current = null;
    setClosePending(false);
  };

  const navigateBrowser = (target: string) => {
    if (!canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current)) return;
    const normalized = normalizeBrowserUrl(target);
    pendingUrlRef.current = normalized;
    setError('');
    setFrame(null);
    setUrl(normalized); send('navigate', { url: normalized });
  };

  const browserKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && selectionMode) {
      event.preventDefault();
      send('cancel_pick');
      setSelectionMode(false);
      pickTargetStepRef.current = null;
      setPickTargetStep(null);
      return;
    }
    if (event.key === 'Escape' && event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      urlInputRef.current?.focus();
      return;
    }
    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) send('type', { text: event.key });
    else if (['Enter','Tab','Escape','Backspace','Delete','ArrowDown','ArrowUp','ArrowLeft','ArrowRight',' '].includes(event.key)) { event.preventDefault(); send('press', { key: event.key === ' ' ? 'Space' : event.key }); }
  };

  const browserPoint = (event: React.MouseEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const scale = Math.min(bounds.width / 1280, bounds.height / 720);
    const offsetX = (bounds.width - 1280 * scale) / 2;
    return { x: (event.clientX - bounds.left - offsetX) / scale, y: (event.clientY - bounds.top) / scale };
  };
  const lastPointerMove = useRef(0);
  const browserPointerMove = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!selectionMode || performance.now() - lastPointerMove.current < 45) return;
    lastPointerMove.current = performance.now();
    send('move', browserPoint(event));
  };
  const browserClick = (event: React.MouseEvent<HTMLDivElement>) => {
    send(event.detail > 1 ? 'double_click' : 'click', browserPoint(event));
    event.currentTarget.focus();
  };

  const updateStep = (index: number, patch: Partial<RecorderStep>) => {
    if (!canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current)) return;
    setSteps((current) => current.map((step, i) => {
      if (i !== index) return step;
      const updated = { ...step, ...patch };
      send('edit_step', { step: updated });
      return updated;
    }));
  };
  const updateStepEvidence = (stepId: string, patch: Partial<NonNullable<RecorderStep['evidence']>>) => {
    setSteps((current) => current.map((step) => step.id === stepId
      ? { ...step, evidence: { ...(step.evidence ?? { schema_version: 1, element: {}, context: {}, locator_candidates: [], decision: {}, status: 'partial', missing: [] }), ...patch } }
      : step));
  };
  const requestAiLocator = async (step: RecorderStep) => {
    if (!canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current) || locatorAnalysisBusy) return;
    setAiAnalysisStep(step.id);
    setError('');
    try {
      const result = await api.analyzeRecorderLocator(sessionId, step.id);
      updateStepEvidence(step.id, { ai_analysis: result });
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setAiAnalysisStep(null); }
  };
  const requestJevLocator = async (step: RecorderStep) => {
    if (!canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current) || locatorAnalysisBusy) return;
    setJevDecisionStep(step.id);
    setError('');
    try {
      const result = await api.requestRecorderJevDecision(sessionId, step.id);
      updateStepEvidence(step.id, { jev_analysis: result });
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setJevDecisionStep(null); }
  };
  const verifyCandidate = (step: RecorderStep, candidate?: RecorderLocatorCandidate, source: 'ai' | 'jev' | 'manual' = 'manual') => {
    if (!canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current) || locatorAnalysisBusy || (!step.locator && !candidate)) return;
    send('verify_locator', { step_id: step.id, candidate_id: candidate?.candidate_id, source });
  };

  const addAssertion = (action: StepAction) => {
    if (!canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current)) return;
    const step: RecorderStep = { id: crypto.randomUUID().replaceAll('-', '').slice(0,12), action, description: actionLabel(action), locator: action.startsWith('assert_') && !['assert_url','assert_title'].includes(action) ? { kind:'css', value:'#result', exact:false } : undefined, value: action === 'assert_count' ? '1' : '' };
    setSteps((current) => [...current, step]); send('add_step', { step });
  };

  const generate = async () => {
    if (!canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current) || busy) return;
    setBusy(true); setError('');
    try {
      const result = await api.generateRecorderCode(sessionId, { case_name: caseName, file_path: filePath, test_name: testName, steps });
      setCode(result.code);
      setVariables(result.variables ?? []);
      setOptimization(null); setPreviewMode('raw');
      setScriptGeneration((current) => current + 1);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const generateFromAgent = async () => {
    const task = aiTask.task;
    const output = browserAgentOutput;
    if (!canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current) || !task || !output || !canGenerateAgentScript || busy) return;
    const startUrl = normalizedHttpUrl(String(task.inputs.url ?? ''));
    if (!startUrl) { setError(t('errors.noAgentStartUrl')); return; }
    const generated = recorderStepsFromAgent(output, startUrl);
    if (!generated || generated.actionCount === 0) { setError(t('errors.noReusableActions')); return; }

    setBusy(true);
    setError('');
    try {
      const result = await api.generateRecorderCode(sessionId, {
        case_name: caseName,
        file_path: filePath,
        test_name: testName,
        steps: generated.steps,
      });
      send('replace_steps', { steps: generated.steps });
      setSteps(generated.steps);
      setCode(result.code);
      setVariables(result.variables ?? []);
      setOptimization(null);
      setPreviewMode('raw');
      setAgentScriptSource({ taskId: task.id, actionCount: generated.actionCount, jevCount: generated.jevCount, assertionCount: generated.assertionCount });
      setScriptGeneration((current) => current + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  };

  const optimize = async () => {
    if (!canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current) || busy || !steps.length) return;
    setBusy(true); setError('');
    try {
      const result = await api.optimizeRecorder(sessionId, { case_name: caseName, file_path: filePath, test_name: testName, steps });
      setOptimization(result); setPreviewMode('optimized'); setCode(result.optimized_code);
      previewDrafts.current = { raw: result.raw_code, optimized: result.optimized_code };
      setScriptGeneration((current) => current + 1);
    } catch (error) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  };

  const switchPreview = (mode: 'raw' | 'optimized') => {
    if (mode === previewMode) return;
    previewDrafts.current[previewMode] = code;
    setPreviewMode(mode);
    setCode(previewDrafts.current[mode]);
  };

  const startAiTask = (type: 'CREATE_TEST' | 'EXPLORE_PAGE') => {
    if (!projectId || !canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current) || agentTaskRunning) return;
    void aiTask.start({
      type,
      goal: type === 'CREATE_TEST' ? (requirement.trim() || t('defaults.testGoal', { caseName })) : t('defaults.exploreGoal', { url }),
      project_id: projectId,
      workspace_id: type === 'CREATE_TEST' ? projectId : undefined,
      inputs: {
        url,
        recorder_session_id: sessionId,
        ...(type === 'CREATE_TEST' ? { recorded_steps: steps, file_path: filePath, case_name: caseName, test_name: testName, requirement: requirement.trim() || caseName } : {}),
      },
    });
  };

  const startNaturalLanguageFlow = async () => {
    if (closeInFlightSessionRef.current) return;
    const goal = requirement.trim();
    const trustedDomains = normalizeTrustedDomains(trustedDomainsText);
    const strategy = browserStrategy;
    if (!projectId) { setError(t('errors.noProject')); return; }
    if (goal.length < 8) { setError(t('errors.goalTooShort')); return; }
    const currentPageUrl = frame?.url && frame.url !== 'about:blank' ? frame.url : url;
    const startUrl = flowStartUrl(goal, currentPageUrl);
    if (!startUrl) { setError(t('errors.missingStartUrl')); return; }

    setBusy(true);
    setError('');
    setPendingAgentGoal(null);
    setAgentScriptSource(null);
    try {
      if (!sessionId) {
        setSocketState('connecting');
        setSocketDetail('');
        const created = await api.createRecorderSession(projectId, startUrl, steps);
        setActiveSessionId(created.id);
        setFrame(null);
        setUrl(created.url || startUrl);
        setRecording(false);
        if (created.navigation_error) {
          setError(recorderErrorMessage(created.navigation_error, created.requested_url));
          return;
        }
        setPendingAgentGoal({ goal, sessionId: created.id, startUrl, strategy, waitingForNavigation: false, trustedDomains });
        return;
      }
      if (!isConnected) throw new Error(t('errors.connectionNotReady'));
      const currentUrl = normalizedHttpUrl(currentPageUrl);
      const needsNavigation = currentUrl !== startUrl;
      setPendingAgentGoal({ goal, sessionId, startUrl, strategy, waitingForNavigation: needsNavigation, trustedDomains });
      if (needsNavigation) navigateBrowser(startUrl);
    } catch (cause) {
      setPendingAgentGoal(null);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  };

  const saveRecorderCase = async (normalizedPath: string) => {
    if (!projectId || !canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current)) throw new Error(t('errors.noRecorderSession'));
    const tags = [...new Set([...tagsText.split(',').map((tag)=>tag.trim()).filter(Boolean), ...(suiteName.trim() ? [`suite:${suiteName.trim()}`] : [])])];
    const normalizedTestName = testName.replace(/\\W+/g, '_').replace(/^_+|_+$/g, '') || 'test_recorded_case';
    const safeTestName = normalizedTestName.startsWith('test_') ? normalizedTestName : `test_${normalizedTestName}`;
    return api.saveRecorderCase(sessionId, {
      test_case: {
        project_id: projectId,
        title: caseName,
        steps: steps.map((step) => step.description || actionLabel(step.action)),
        expected_result: t('defaults.expectedResult'),
        priority,
        automation_status: 'AUTOMATED',
        tags,
      },
      file_path: normalizedPath,
      test_name: safeTestName,
    });
  };

  const openRecordedCaseInStudio = async () => {
    if (!projectId || !canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current)) return;
    if (!code.trim()) { await generate(); return; }
    setBusy(true); setError('');
    try {
      const normalizedPath = normalizeRecorderFilePath(filePath);
      if (!normalizedPath.endsWith('.py') || normalizedPath.split('/').includes('..')) throw new Error(t('errors.pythonFilePath'));
      // PUT creates or overwrites, so re-recording the same case no longer dead-ends in a 409.
      await api.writeWorkspaceFile(projectId, normalizedPath, code);
      const savedCase = await saveRecorderCase(normalizedPath);
      if (onOpenRecordedCase) onOpenRecordedCase(savedCase, normalizedPath);
      else navigate(buildWorkspaceHref({
        projectId,
        testCaseId: savedCase.test_case.id,
        automationBindingId: savedCase.binding.id,
        file: normalizedPath,
        nodeId: savedCase.nodeid,
        stage: 'automation',
        view: 'code',
        returnTo: 'workspace',
      }));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const saveAndRun = async () => {
    if (!projectId || !canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current)) return;
    if (!code.trim()) { await generate(); return; }
    setBusy(true); setError('');
    try {
      const normalizedPath = normalizeRecorderFilePath(filePath);
      if (!normalizedPath.endsWith('.py') || normalizedPath.split('/').includes('..')) throw new Error(t('errors.pythonFilePath'));
      // PUT creates or overwrites, so re-recording the same case no longer dead-ends in a 409.
      await api.writeWorkspaceFile(projectId, normalizedPath, code);
      const savedCase = await saveRecorderCase(normalizedPath);
      const markers = markersText.split(',').map((marker)=>marker.trim()).filter(Boolean);
      const runRequest: Omit<TestRunCreate, 'idempotency_key'> = {
        project_id: projectId,
        workspace_id: projectId,
        nodeids: [savedCase.nodeid],
        markers,
        runner_type: 'LOCAL',
        requested_by: `Recorder · ${caseName}`,
        ...recorderRunConfigFields(runConfig),
      };
      const idempotencyScope = `${projectId}:${savedCase.nodeid}`;
      const idempotencyKey = recorderRunIdempotencyKey(idempotencyScope, runRequest);
      const run = await api.createTestRun({ ...runRequest, idempotency_key: idempotencyKey });
      clearRecorderRunIdempotencyKey(idempotencyScope);
      if (onNavigateToRuns) onNavigateToRuns(run.id);
      else navigate(`/runs/${run.id}`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const actionInputs = (step: RecorderStep, index: number) => {
    const locatorRequired = !['navigate','back','scroll','wait','assert_url','assert_title'].includes(step.action);
    const locatorValue = step.locator?.value ?? '';
    const parameter = step.value_redacted
      ? step.secret_env_var ?? `QA_RECORDER_SECRET_${step.id.toUpperCase()}`
      : step.action === 'navigate' ? step.url ?? '' : step.action === 'press' ? step.key ?? '' : step.value ?? '';
    const parameterLabel = step.value_redacted ? t('steps.secretVariable') : t('steps.parameter');
    const parameterPlaceholder = step.value_redacted ? t('steps.secretValuePlaceholder')
      : step.action === 'wait' ? t('steps.milliseconds')
        : step.action === 'scroll' ? t('steps.scrollDirection')
          : step.action === 'assert_count' ? t('steps.count') : t('steps.parameterValue');
    return <>
      <input className="recorder-step-field recorder-step-locator" aria-label={t('steps.locator')} value={locatorValue} placeholder={locatorRequired ? t('steps.locator') : t('steps.noLocator')} disabled={!recorderSessionWorkAllowed || !locatorRequired} onChange={(e) => updateStep(index, { locator: { ...(step.locator || {kind:'text', exact:true}), value:e.target.value } })} />
      <input className="recorder-step-field recorder-step-parameter" aria-label={parameterLabel} value={parameter} disabled={!recorderSessionWorkAllowed || step.value_redacted} placeholder={parameterPlaceholder} onChange={(e) => updateStep(index, step.action==='navigate' ? {url:e.target.value} : step.action==='press' ? {key:e.target.value} : {value:e.target.value})} />
    </>;
  };

  const projectName = projects.find((project) => project.id === projectId)?.name;
  const isConnected = socketState === 'connected';
  const socketLabel = socketDetail || t(`connection.${socketState}`);
  const browserAgentOutput = asRecord(aiTask.task?.plan.find((step) => step.key === 'browser_agent')?.outputs);
  const canGenerateAgentScript = aiTask.task?.type === 'EXPLORE_PAGE'
    && aiTask.task.status === 'COMPLETED'
    && browserAgentOutput?.verified === true
    && ['ai_jev_browser_agent', 'fast_browser_agent'].includes(String(browserAgentOutput.kind))
    && Array.isArray(browserAgentOutput.actions);
  const locatorDecisionMetadata = [...locatorTraceEvents].reverse().find((event) => event.type === 'decision_completed')?.metadata ?? {};
  const locatorVerificationMetadata = [...locatorTraceEvents].reverse().find((event) => event.type === 'verification_completed')?.metadata ?? {};
  const verificationFacts = (['unique', 'visible', 'enabled', 'editable', 'clickable'] as const)
    .filter((key) => typeof locatorVerificationMetadata[key] === 'boolean')
    .map((key) => `${key}=${locatorVerificationMetadata[key] === true ? 'yes' : 'no'}`);
  const locatorEngine = String(locatorDecisionMetadata.engine ?? t('locator.localStrategy'));
  const locatorModel = locatorEngine === 'Jev' && typeof locatorDecisionMetadata.model === 'string' ? locatorDecisionMetadata.model : '';
  const locatorLatency = locatorEngine === 'Jev' && typeof locatorDecisionMetadata.latency_ms === 'number' ? t('locator.latency', { value: `${locatorDecisionMetadata.latency_ms.toFixed(1)} ms` }) : '';

  useEffect(() => {
    const pending = pendingAgentGoal;
    if (!pending || pending.sessionId !== sessionId || !canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current) || pending.waitingForNavigation || !isNavigationFrameFresh(frameRevisionRef.current, pending.minimumFrameRevision) || socketState !== 'connected' || !projectId || aiTask.busy || frame?.type !== 'frame') return;
    if (!/^https?:\/\//i.test(frame.url || '')) {
      setPendingAgentGoal(null);
      setError(t('errors.noActionablePage', { url: frame.url || t('errors.targetWebsite') }));
      return;
    }
    setPendingAgentGoal(null);
    void aiTask.start({
      type: 'EXPLORE_PAGE',
      goal: pending.goal,
      project_id: projectId,
      inputs: {
        url: pending.startUrl,
        recorder_session_id: pending.sessionId,
        strategy: pending.strategy,
        require_jev_decisions: pending.strategy === 'agent',
        ...(pending.trustedDomains.length ? { trusted_domains: pending.trustedDomains } : {}),
      },
    });
  }, [pendingAgentGoal, sessionId, socketState, projectId, aiTask.busy, aiTask.start, frame, t]);

  return (
    <div className={`recorder-page${embedded ? ' is-embedded' : ''}`} data-mobile-panel={embedded ? exploreMobilePanel : undefined}>
      <header className="recorder-page-header">
        <div className="recorder-page-heading">
          <h2><MousePointer2 size={20} aria-hidden="true" /> {t('header.title')}</h2>
          {projectName && <span className="recorder-project-label">{projectName}</span>}
          <span className={`status-pill ${isConnected ? 'status-pill-online' : 'status-pill-draft'}`}>
            {t('connection.session', { state: socketLabel })}
          </span>
          {sessionId && (socketState === 'error' || socketState === 'closed') && (
            <button
              type="button"
              className="btn btn-secondary btn-icon"
              aria-label={t('header.retry')}
              title={t('header.retry')}
              disabled={!recorderSessionWorkAllowed}
              onClick={() => {
                if (!canStartRecorderSessionWork(sessionId, closeInFlightSessionRef.current)) return;
                socketReadyRef.current = false;
                setSocketAttempt((attempt) => attempt + 1);
              }}
            >
              <RotateCw size={15} />
            </button>
          )}
          {recording && <span className="status-pill status-pill-warning">{t('header.recording')}</span>}
        </div>

        <div className="recorder-actions" role="group" aria-label={t('header.actions')} tabIndex={embedded ? 0 : undefined}>
          <button
            type="button"
            className={`btn ${recording ? 'btn-secondary' : 'btn-primary'}`}
            disabled={!recorderSessionWorkAllowed || busy || agentTaskRunning}
            onClick={() => { const next = !recording; setRecording(next); send(recording ? 'pause' : 'start'); }}
          >
            {recording ? <CirclePause size={16} /> : <CirclePlay size={16} />}
            {recording ? t('header.pause') : t('header.start')}
          </button>
          <button type="button" className="btn btn-secondary" disabled={!recorderSessionWorkAllowed || agentTaskRunning} onClick={() => { send('stop'); setRecording(false); }}>
            <Square size={15} /> {t('header.stop')}
          </button>
          <button
            type="button"
            className={`btn ${selectionMode ? 'btn-primary recorder-select-mode-active' : 'btn-secondary'}`}
            disabled={!recorderSessionWorkAllowed || !isConnected || agentTaskRunning}
            aria-pressed={selectionMode}
            onClick={() => {
              if (selectionMode) {
                send('cancel_pick');
                setSelectionMode(false);
                pickTargetStepRef.current = null;
                setPickTargetStep(null);
              } else {
                setSelectionMode(true);
                pickTargetStepRef.current = null;
                setPickTargetStep(null);
                send('pick_element', { step_action: 'click' });
              }
            }}
          >
            <Crosshair size={15} /> {selectionMode ? t('header.cancelSelection') : t('header.selectElement')}
          </button>
          <button type="button" className="btn btn-secondary" disabled={!recorderSessionWorkAllowed || busy || agentTaskRunning} onClick={generate}>
            <Code2 size={16} /> {busy ? t('header.processing') : code ? t('header.regenerateScript') : t('header.generateScript')}
          </button>
          <button className="btn btn-primary" disabled={!recorderSessionWorkAllowed || !steps.length || busy || aiTask.busy || agentTaskRunning} onClick={() => startAiTask('CREATE_TEST')}>
            <Code2 size={16} /> {t('header.createVerifyTest')}
          </button>
          <button className="btn btn-secondary" disabled={!recorderSessionWorkAllowed || busy || aiTask.busy || agentTaskRunning} onClick={() => startAiTask('EXPLORE_PAGE')}>
            {t('header.explorePage')}
          </button>
          <button type="button" className="btn btn-secondary" disabled={!recorderSessionWorkAllowed || busy || aiTask.busy || agentTaskRunning || !code} onClick={saveAndRun}>
            <Save size={16} /> {t('header.saveAndRun')}
          </button>
        </div>
      </header>

      {(stepOutboxStorageUnavailable || navigationOutboxStorageUnavailable) && (
        <section className="alert alert-error recorder-error" role="alert">
          <div className="alert-content">
            <AlertTriangle size={17} aria-hidden="true" />
            <div className="alert-copy">
              <strong>{t('header.errorTitle')}</strong>
              {stepOutboxStorageUnavailable && <p>{t('errors.stepOutboxStorageUnavailable')}</p>}
              {navigationOutboxStorageUnavailable && <p>{t('errors.navigationOutboxStorageUnavailable')}</p>}
            </div>
          </div>
        </section>
      )}
      {error && (
        <section className="alert alert-error recorder-error" role="alert">
          <div className="alert-content">
            <AlertTriangle size={17} aria-hidden="true" />
            <div className="alert-copy">
              <strong>{t('header.errorTitle')}</strong>
              <p>{error}</p>
              {closeRetryBlocked && <p>{t('naturalFlow.closeBlocked')}</p>}
              <details className="alert-details">
                <summary>{t('header.errorDetails')}</summary>
                <pre>{JSON.stringify({ sessionId, targetUrl: pendingUrlRef.current ?? url, connection: socketState }, null, 2)}</pre>
              </details>
            </div>
          </div>
          <div className="alert-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={closeRetryBlocked}
              onClick={() => {
                if (sessionId && errorRecovery === 'close') {
                  void closeSession();
                } else if (sessionId) {
                  navigateBrowser(pendingUrlRef.current ?? url);
                } else {
                  void createSession();
                }
              }}
            >
              {t('header.retry')}
            </button>
          </div>
        </section>
      )}

      {embedded && <nav className="recorder-explore-mobile-nav" aria-label={workspaceT('mobile.explore.navigation')}>
        {(['browser', 'task'] as const).map((panel) => <button key={panel} type="button" aria-pressed={exploreMobilePanel === panel} className={exploreMobilePanel === panel ? 'is-current' : ''} onClick={() => setExploreMobilePanel(panel)}>{workspaceT(`mobile.explore.${panel}`)}</button>)}
      </nav>}
      <div className="recorder-explore-layout">
      <section className="recorder-explore-task">
      <details className="recorder-natural-flow" open={naturalFlowOpen} onToggle={(event) => setNaturalFlowOpen(event.currentTarget.open)} aria-labelledby="recorder-natural-flow-title">
        <summary id="recorder-natural-flow-title">{t('naturalFlow.title')}</summary>
        <div className="recorder-natural-flow-body">
        <div className="recorder-natural-flow-prompt">
          <label htmlFor="recorder-natural-flow-input">{t('naturalFlow.promptLabel')}</label>
          <textarea
            id="recorder-natural-flow-input"
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
            placeholder={t('naturalFlow.placeholder')}
            rows={3}
          />
          <details className="recorder-trusted-domains">
            <summary>{t('naturalFlow.trustedDomains')}</summary>
            <input
              aria-label={t('naturalFlow.trustedDomainsLabel')}
              value={trustedDomainsText}
              onChange={(event) => setTrustedDomainsText(event.target.value)}
              placeholder={t('naturalFlow.trustedDomainsPlaceholder')}
            />
            <small>{t('naturalFlow.trustedDomainsHelp')}</small>
          </details>
        </div>
        <div className="recorder-natural-flow-actions">
          <p>{t(browserStrategy === 'agent' ? 'naturalFlow.agentDescription' : 'naturalFlow.fastDescription')} {t('naturalFlow.scriptDescription')}</p>
          <div>
            <label className="recorder-strategy-control">
              <span>{t('naturalFlow.strategy')}</span>
              <select aria-label={t('naturalFlow.strategyLabel')} value={browserStrategy} disabled={Boolean(pendingAgentGoal || aiTask.busy || agentTaskRunning)} onChange={(event) => setBrowserStrategy(event.target.value as 'fast' | 'agent')}>
                <option value="agent">{t('naturalFlow.agentStrategy')}</option>
                <option value="fast">{t('naturalFlow.fastStrategy')}</option>
              </select>
            </label>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!projectId || (sessionId ? !recorderSessionWorkAllowed || !isConnected : restoreCheckedProjectId !== projectId) || !requirement.trim() || busy || aiTask.busy || agentTaskRunning || !!pendingAgentGoal}
              onClick={() => void startNaturalLanguageFlow()}
            >
              <CirclePlay size={15} aria-hidden="true" />
              {pendingAgentGoal || aiTask.busy || agentTaskRunning
                ? t(browserStrategy === 'agent' ? 'naturalFlow.agentRunning' : 'naturalFlow.fastRunning')
                : t(browserStrategy === 'agent' ? 'naturalFlow.agentStart' : 'naturalFlow.fastStart')}
            </button>
            {canGenerateAgentScript && (
              <button type="button" className="btn btn-secondary" disabled={!recorderSessionWorkAllowed || busy} onClick={() => void generateFromAgent()}>
                <Code2 size={15} aria-hidden="true" /> {busy ? t('naturalFlow.generatingScript') : t('naturalFlow.generateFromVerified')}
              </button>
            )}
          </div>
          {agentScriptSource && (
            <small role="status">
              {t('naturalFlow.scriptSource', { actions: agentScriptSource.actionCount, decisions: agentScriptSource.jevCount, assertions: agentScriptSource.assertionCount })}
            </small>
          )}
        </div>
        </div>
      </details>

      <ContextTaskProgress task={aiTask.task} error={aiTask.error} />
      </section>
      <section className="recorder-explore-browser">
      <div className="recorder-urlbar">
        <input
          ref={urlInputRef}
          className="recorder-url-input"
          aria-label={t('naturalFlow.browserAddress')}
          value={url}
          disabled={closePending}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && navigateBrowser(url)}
          placeholder={t('naturalFlow.addressPlaceholder')}
        />
        <button type="button" className="btn btn-secondary btn-icon" aria-label={t('naturalFlow.back')} title={t('naturalFlow.back')} disabled={!recorderSessionWorkAllowed} onClick={() => send('back')}>←</button>
        <button type="button" className="btn btn-secondary btn-icon" aria-label={t('naturalFlow.forward')} title={t('naturalFlow.forward')} disabled={!recorderSessionWorkAllowed} onClick={() => send('forward')}>→</button>
        <button type="button" className="btn btn-secondary btn-icon" aria-label={t('naturalFlow.reload')} title={t('naturalFlow.reload')} disabled={!recorderSessionWorkAllowed} onClick={() => send('reload')}><RotateCw size={16} /></button>
        {!sessionId ? (
          <button type="button" className="btn btn-primary" disabled={busy || restoreCheckedProjectId !== projectId} onClick={createSession}>{t('naturalFlow.startBrowser')}</button>
        ) : (
          <button
            type="button"
            className="btn btn-secondary"
            disabled={!closeAllowed}
            aria-busy={closePending}
            title={!closeAllowed && !closePending ? t('naturalFlow.closeBlocked') : undefined}
            onClick={() => void closeSession()}
          >
            {closePending ? t('naturalFlow.closingBrowser') : closeAllowed ? t('naturalFlow.closeBrowser') : t('naturalFlow.closeBlocked')}
          </button>
        )}
      </div>

        <section className="recorder-panel recorder-browser-panel">
          <div className="recorder-panel-heading">
            <strong>{t('browser.view')}</strong>
            <span className="recorder-keyboard-hint" id="recorder-keyboard-help">{t('browser.keyboardHint')}</span>
            <span className="recorder-browser-meta" title={`${frame?.title || t('browser.remoteScreen')} · ${frame?.url || url}`}>
              {frame?.title || t('browser.remoteScreen')} · {frame?.url || url}
            </span>
          </div>
          <div
            ref={browserRef}
            className="recorder-browser-viewport"
            role="region"
            tabIndex={0}
            aria-label={t('browser.interactiveView')}
            aria-describedby="recorder-keyboard-help"
            onClick={browserClick}
            onMouseMove={browserPointerMove}
            onMouseLeave={() => send('clear_hover')}
            onKeyDown={browserKeyDown}
            onWheel={(e) => {
              const bounds = browserRef.current?.getBoundingClientRect();
              if (bounds) {
                const scale = Math.min(bounds.width / 1280, bounds.height / 720);
                send('wheel', { delta_x: e.deltaX / scale, delta_y: e.deltaY / scale });
              }
            }}
          >
            {frame?.image ? (
              <img className="recorder-browser-image" draggable={false} src={`data:image/jpeg;base64,${frame.image}`} alt={t('browser.imageAlt')} />
            ) : (
              <div className="recorder-browser-empty">
                <MousePointer2 size={22} aria-hidden="true" />
                <strong>{t('browser.emptyTitle')}</strong>
                <span>{t('browser.emptyDescription')}</span>
              </div>
            )}
          </div>
          {frame?.tabs && frame.tabs.length > 1 && (
            <div className="recorder-browser-tabs" role="group" aria-label={t('browser.tabs')}>
              {frame.tabs.map((item) => (
                <button
                  type="button"
                  key={item.index}
                  className={`recorder-browser-tab ${item.active ? 'active' : ''}`}
                  aria-pressed={item.active}
                  title={item.title || item.url}
                  onClick={() => send('tab', { index: item.index })}
                >
                  {item.title || item.url}
                </button>
              ))}
            </div>
          )}
        </section>
      </section>
      <section className="recorder-explore-steps">
        <section className={`recorder-panel recorder-inspector-panel${locatorTraceEvents.length ? ' has-locator-trace' : ''}${selectionMode || pickedElement ? ' has-element-evidence' : ''}`}>
          {(selectionMode || pickedElement) && (
            <div className="recorder-element-evidence" aria-live="polite">
              <div className="recorder-element-evidence-heading">
                <strong>{t(selectionMode ? 'selection.mode' : 'selection.selected')}</strong>
                {selectionMode && <button type="button" className="btn btn-secondary btn-sm" onClick={() => { send('cancel_pick'); setSelectionMode(false); }}>{t('selection.cancel')}</button>}
              </div>
              {selectionMode && frame?.hovered && <p>{t('selection.current', { element: `${frame.hovered.role || frame.hovered.tag} · ${frame.hovered.name || frame.hovered.text || t('selection.noAccessibleName')}` })}</p>}
              {pickedElement && <>
                <p>{pickedElement.role || pickedElement.tag} · {pickedElement.name || pickedElement.text || t('selection.noName')}{pickedElement.value_redacted ? ` · ${t('selection.sensitiveRedacted')}` : ''}</p>
                <small>{pickedElement.parent_summary || t('selection.noParentSummary')}{pickedElement.bounding_box ? ` · ${t('selection.size', { width: pickedElement.bounding_box.width, height: pickedElement.bounding_box.height })}` : ''}{pickedElement.frame_path?.length ? ` · ${t('selection.frame', { path: pickedElement.frame_path.join(' › ') })}` : ''}{pickedElement.shadow_path?.length ? ` · ${t('selection.shadow', { path: pickedElement.shadow_path.join(' › ') })}` : ''}</small>
                {pickedElement.attributes && <details><summary>{t('selection.details')}</summary><pre>{JSON.stringify(pickedElement.attributes, null, 2)}</pre><ul>{(pickedElement.ranked_candidates ?? pickedElement.candidates ?? []).slice(0, 8).map((candidate, index) => <li key={`${candidate.kind}-${candidate.value}-${index}`}>{candidate.locator || t('locator.candidateLabel', { kind: candidate.kind, value: candidate.value })}</li>)}</ul></details>}
              </>}
            </div>
          )}
          <div className="recorder-steps-heading">
            <div>
              <strong>{t('steps.title')}</strong>
              <span className="recorder-step-count">{steps.length}</span>
            </div>
            <select aria-label={t('steps.addAssertion')} defaultValue="" disabled={!recorderSessionWorkAllowed} onChange={(e) => { if (e.target.value) addAssertion(e.target.value as StepAction); e.target.value = ''; }}>
              <option value="">+ {t('steps.addAssertion')}</option>
              <option value="assert_visible">{t('steps.assertVisible')}</option>
              <option value="assert_text">{t('steps.assertText')}</option>
              <option value="assert_url">{t('steps.assertUrl')}</option>
              <option value="assert_title">{t('steps.assertTitle')}</option>
              <option value="assert_count">{t('steps.assertCount')}</option>
            </select>
          </div>

          {locatorTraceEvents.length > 0 && (
            <div className="recorder-locator-trace">
              <strong>{t('locator.title')}</strong>
              <div className={`recorder-locator-summary${locatorVerificationMetadata.verified === true ? ' is-verified' : locatorVerificationMetadata.verified === false ? ' is-unverified' : ''}`} role="status">
                <span>
                  {t('locator.decisionEngine', { engine: locatorEngine })}
                  {locatorModel ? ` · ${t('locator.model', { model: locatorModel })}` : ''}
                  {locatorLatency ? ` · ${locatorLatency}` : ''}
                  {' · '}{t('locator.selected', { id: String(locatorDecisionMetadata.candidate_id ?? t('locator.unknown')) })}
                  {' · '}{t('locator.candidateCount', { count: typeof locatorDecisionMetadata.candidate_count === 'number' ? locatorDecisionMetadata.candidate_count : '—' })}
                </span>
                <span>
                  {t('locator.verification', { status: locatorVerificationMetadata.verified === true ? 'PASS' : locatorVerificationMetadata.verified === false ? 'FAILED' : 'UNKNOWN' })}
                  {typeof locatorDecisionMetadata.selected_locator === 'string' ? ` · ${locatorDecisionMetadata.selected_locator}` : ''}
                  {verificationFacts.length > 0 ? ` · ${verificationFacts.join(' · ')}` : ''}
                </span>
              </div>
              <AIExecutionTimeline events={locatorTraceEvents} running={false} />
            </div>
          )}

          <div className="recorder-steps-list" role="region" aria-label={t('steps.title')} tabIndex={0}>
            {steps.map((step, index) => {
              const evidence = step.evidence;
              const aiCandidateId = typeof evidence?.ai_analysis?.candidate_id === 'string' ? evidence.ai_analysis.candidate_id : null;
              const jevCandidateId = typeof evidence?.jev_analysis?.candidate_id === 'string' ? evidence.jev_analysis.candidate_id : null;
              const conflict = Boolean(aiCandidateId && jevCandidateId && aiCandidateId !== jevCandidateId);
              return (
                <div key={step.id} className="recorder-step-item">
                  <div className="recorder-step-row">
                    <select className="recorder-step-field recorder-step-action" aria-label={t('steps.actionType')} value={step.action} disabled={!recorderSessionWorkAllowed} onChange={(e) => updateStep(index, { action: e.target.value as StepAction })}>
                      {actions.map((action) => <option key={action} value={action}>{actionLabel(action)}</option>)}
                    </select>
                    <input className="recorder-step-field recorder-step-description" aria-label={t('steps.description')} value={step.description} disabled={!recorderSessionWorkAllowed} onChange={(e) => updateStep(index, { description: e.target.value })} />
                    {actionInputs(step, index)}
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm recorder-step-pick"
                      title={t('steps.pickTitle')}
                      disabled={!recorderSessionWorkAllowed || !isConnected || locatorAnalysisBusy}
                      onClick={() => { pickTargetStepRef.current = step.id; setPickTargetStep(step.id); setSelectionMode(true); send('pick_element', { step_action: step.action }); }}
                    >
                      <Crosshair size={14} />{pickTargetStep === step.id ? t('steps.pickPrompt') : t('steps.pick')}
                    </button>
                    <div className="recorder-step-controls">
                      <button type="button" className="btn btn-secondary btn-icon" aria-label={t('steps.reverify')} title={t('steps.reverify')} disabled={!recorderSessionWorkAllowed || !step.locator || locatorAnalysisBusy} onClick={() => verifyCandidate(step)}><RotateCw size={14} /></button>
                      <button type="button" className="btn btn-secondary btn-icon" aria-label={t('steps.moveUp')} title={t('steps.moveUp')} disabled={!recorderSessionWorkAllowed || index === 0} onClick={() => { const next = [...steps]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; setSteps(next); send('reorder', { ids: next.map((s) => s.id) }); }}><ArrowUp size={14} /></button>
                      <button type="button" className="btn btn-secondary btn-icon" aria-label={t('steps.moveDown')} title={t('steps.moveDown')} disabled={index === steps.length - 1} onClick={() => { const next = [...steps]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; setSteps(next); send('reorder', { ids: next.map((s) => s.id) }); }}><ArrowDown size={14} /></button>
                      <button type="button" className="btn btn-secondary btn-icon" aria-label={t('steps.delete')} title={t('steps.delete')} onClick={() => { setSteps(steps.filter((_, i) => i !== index)); send('delete_step', { id: step.id }); }}><Trash2 size={14} /></button>
                    </div>
                  </div>
                  {evidence && <details className="recorder-step-evidence">
                    <summary>{t('steps.evidenceSummary', { version: evidence.schema_version, count: evidence.locator_candidates.length, status: t(evidence.status === 'available' ? 'steps.evidenceAvailable' : evidence.status === 'stale' ? 'steps.evidenceStale' : 'steps.evidencePartial') })}</summary>
                    <div className="recorder-evidence-actions">
                      <button type="button" className="btn btn-secondary btn-sm" disabled={!recorderSessionWorkAllowed || locatorAnalysisBusy} onClick={() => void requestAiLocator(step)}>{aiAnalysisStep === step.id ? t('steps.analyzing') : t('steps.requestAiAnalysis')}</button>
                      <button type="button" className="btn btn-secondary btn-sm" disabled={!recorderSessionWorkAllowed || locatorAnalysisBusy} onClick={() => void requestJevLocator(step)}>{jevDecisionStep === step.id ? t('steps.jevDeciding') : t('steps.requestJevDecision')}</button>
                      <span>{evidence.ai_analysis?.status === 'available' ? t('steps.aiAvailable', { provider: String(evidence.ai_analysis.provider), reason: String(evidence.ai_analysis.reason || '') }) : evidence.ai_analysis ? t('steps.aiUnavailable', { reason: String(evidence.ai_analysis.reason) }) : t('steps.aiNotAnalyzed')}</span>
                      <span>{evidence.jev_analysis?.status === 'available' ? t('steps.jevAvailable', { candidate: String(evidence.jev_analysis.candidate_id) }) : evidence.jev_analysis ? t('steps.jevUnavailable', { reason: String(evidence.jev_analysis.reason || evidence.jev_analysis.provider) }) : t('steps.jevNotRequested')}</span>
                    </div>
                    {conflict && <p className="recorder-decision-conflict" role="status">{t('steps.decisionConflict', { ai: aiCandidateId, jev: jevCandidateId })}</p>}
                    <div className="recorder-candidate-list">
                      {evidence.locator_candidates.map((candidate, candidateIndex) => {
                        const aiRecommended = candidate.candidate_id === aiCandidateId && evidence.ai_analysis?.status === 'available';
                        const jevRecommended = candidate.candidate_id === jevCandidateId && evidence.jev_analysis?.status === 'available';
                        const verification = candidate.verification;
                        return <div className="recorder-candidate" key={`${candidate.candidate_id ?? candidateIndex}-${candidate.kind}-${candidate.value}`}>
                          <div><strong>{candidate.kind}</strong><code>{candidate.locator || `${candidate.kind}: ${candidate.value}${candidate.name ? ` · ${candidate.name}` : ''}`}</code><small>{t('steps.candidateMatches', { count: verification?.match_count ?? '—' })} · {verification?.unique ? t('steps.candidateUnique') : verification?.unique === false ? t('steps.candidateAmbiguous') : t('steps.candidateNotVerified')} · {verification?.visible ? t('steps.candidateVisible') : verification?.visible === false ? t('steps.candidateNotVisible') : t('steps.candidateVisibilityUnknown')} · {verification?.verified ? t('steps.candidateVerified') : t('steps.candidateVerificationPending')}</small></div>
                          <div className="recorder-candidate-actions">
                            <button type="button" className="btn btn-secondary btn-sm" disabled={!recorderSessionWorkAllowed || locatorAnalysisBusy} onClick={() => verifyCandidate(step, candidate)}>{step.locator?.value === candidate.value && step.locator?.kind === candidate.kind ? t('steps.validateCurrent') : t('steps.verifyAndUse')}</button>
                            {aiRecommended && <button type="button" className="btn btn-secondary btn-sm" disabled={!recorderSessionWorkAllowed || locatorAnalysisBusy} onClick={() => verifyCandidate(step, candidate, 'ai')}>{t('steps.useAi')}</button>}
                            {jevRecommended && <button type="button" className="btn btn-secondary btn-sm" disabled={!recorderSessionWorkAllowed || locatorAnalysisBusy} onClick={() => verifyCandidate(step, candidate, 'jev')}>{t('steps.useJev')}</button>}
                          </div>
                        </div>;
                      })}
                    </div>
                    {evidence.missing.length > 0 && <small>{t('steps.missingEvidence', { items: evidence.missing.join(', ') })}</small>}
                    <small>{t('steps.target', { element: String(evidence.element.name || evidence.element.text || evidence.element.tag || t('steps.noAccessibleTarget')), url: String(evidence.context.url || t('steps.noAccessibleTarget')), capturedAt: String(evidence.context.captured_at || '') })}</small>
                  </details>}
                </div>
              );
            })}
            {!steps.length && <div className="recorder-steps-empty">{t('steps.noSteps')}</div>}
          </div>

          <details className="recorder-api-calls" open>
            <summary>
              <span>{t('apiCalls.title')}</span>
              <span className="recorder-step-count">{apiCalls.length}</span>
            </summary>
            <div className="recorder-api-calls-body">
              <p className="recorder-api-calls-hint">{t('apiCalls.hint')}</p>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={!sessionId || apiCallsBusy}
                onClick={() => {
                  if (!sessionId) return;
                  setApiCallsBusy(true);
                  void api.getRecorderApiCalls(sessionId)
                    .then((result) => { setApiCalls(result.calls); setApiCallsError(''); })
                    .catch((reason) => setApiCallsError(String(reason)))
                    .finally(() => setApiCallsBusy(false));
                }}
              >
                {apiCallsBusy ? t('apiCalls.refreshing') : t('apiCalls.refresh')}
              </button>
              {apiCallsError && <p className="recorder-api-calls-error" role="alert">{apiCallsError}</p>}
              {apiCallMessage && (
                <p className="recorder-api-calls-message" role="status">
                  {apiCallMessage}
                  {apiCallCaseId && (
                    <>
                      {' · '}
                      <Link to={`/test-cases/${apiCallCaseId}`}>{t('apiCalls.openCase')}</Link>
                    </>
                  )}
                </p>
              )}
              {apiCalls.length === 0 ? (
                <p className="recorder-api-calls-hint">{t('apiCalls.empty')}</p>
              ) : (
                <ul className="recorder-api-calls-list">
                  {apiCalls.map((call) => (
                    <li key={call.id}>
                      <span className={`api-case-method is-${call.method.toLowerCase()}`}>{call.method}</span>
                      <code title={call.url}>{call.url}</code>
                      <span className="recorder-api-calls-status">{call.status ?? '—'}</span>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled={!projectId || apiCallSaving === call.id}
                        onClick={() => void saveApiCall(call)}
                      >
                        {apiCallSaving === call.id ? t('apiCalls.saving') : t('apiCalls.save')}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </details>

          <details className="recorder-case-settings">
            <summary>{t('settings.title')}</summary>
            <div className="recorder-settings-grid">
              <label>{t('settings.caseName')}<input aria-label={t('settings.caseName')} value={caseName} onChange={(e) => setCaseName(e.target.value)} /></label>
              <label>{t('settings.testFunction')}<input aria-label={t('settings.testFunction')} value={testName} onChange={(e) => setTestName(e.target.value)} /></label>
              <label>{t('settings.projectFile')}<input aria-label={t('settings.projectFile')} value={filePath} onChange={(e) => setFilePath(e.target.value)} /></label>
              <label>{t('settings.priority')}<select value={priority} onChange={(e) => setPriority(e.target.value as TestCasePriority)}><option value="P1">{t('settings.high')}</option><option value="P2">{t('settings.medium')}</option><option value="P3">{t('settings.low')}</option></select></label>
              <label>{t('settings.suite')}<input aria-label={t('settings.suite')} value={suiteName} onChange={(e) => setSuiteName(e.target.value)} placeholder={t('settings.suite')} /></label>
              <label>{t('settings.tags')}<input aria-label={t('settings.tags')} value={tagsText} onChange={(e) => setTagsText(e.target.value)} placeholder={t('settings.tagsPlaceholder')} /></label>
              <label>{t('settings.markers')}<input aria-label={t('settings.markers')} value={markersText} onChange={(e) => setMarkersText(e.target.value)} placeholder={t('settings.markersPlaceholder')} /></label>
            </div>
          </details>

          <div className="recorder-editor-panel">
            <div className="recorder-panel-heading">
              <strong>{t('script.title')}</strong>
              <div className="recorder-editor-actions">
                <span>Playwright</span>
                <button type="button" className="btn btn-secondary btn-sm" disabled={!recorderSessionWorkAllowed || !steps.length || busy} onClick={() => void optimize()}>{t('script.optimize')}</button>
                {code && (
                  <>
                    <button type="button" className="btn btn-secondary btn-sm" aria-label={t('script.regenerateAria')} title={t('script.regenerateTitle')} disabled={!recorderSessionWorkAllowed || busy} onClick={generate}>
                      <RotateCw size={13} aria-hidden="true" /> {t('script.regenerate')}
                    </button>
                    <button type="button" className="btn btn-primary btn-sm" disabled={!recorderSessionWorkAllowed || busy} onClick={() => void openRecordedCaseInStudio()}>
                      <Code2 size={13} aria-hidden="true" /> {t('script.saveOpen')}
                    </button>
                  </>
                )}
              </div>
            </div>
            {optimization && <div className="recorder-optimization-summary"><div role="group" aria-label={t('script.optimizationComparison')}><button type="button" className="btn btn-secondary btn-sm" aria-pressed={previewMode === 'raw'} onClick={() => { switchPreview('raw'); }}>{t('script.raw', { count: optimization.raw_steps.length })}</button> <button type="button" className="btn btn-secondary btn-sm" aria-pressed={previewMode === 'optimized'} onClick={() => { switchPreview('optimized'); }}>{t('script.optimized', { count: optimization.optimized_steps.length })}</button></div><p>{optimization.provider} / {optimization.model} · {optimization.prompt_version} · {t('script.needsVerification')}</p><details><summary>{t('script.optimizationBasis')}</summary><ul>{optimization.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></details></div>}
            <div className="recorder-editor-surface">
              {variables.length > 0 && (
                <div className="recorder-variables" aria-label="recorder variables">
                  <strong>{t('variablesCount', { count: variables.length })}</strong>
                  <span className="recorder-variables-hint">{t('variablesHint')}</span>
                  <ul>
                    {variables.map((variable) => (
                      <li key={variable.name}>
                        <code>{variable.name}</code>
                        <span>{variable.default}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <MonacoEditorPane activeTab={tab} loadingFile={false} showDiffView={false} diffResult={blankDiff} editorRef={editorRef} stickyScroll={false} readOnly onEditorReady={() => { setEditorReady(true); setShowCodeFallback(false); }} onChange={(value) => setCode(value || '')} />
              {showCodeFallback && !editorReady && (
                <textarea aria-label={t('script.textarea')} value={code} readOnly spellCheck={false} />
              )}
            </div>
          </div>
        </section>
      </section>
      </div>
    </div>
  );
};
