import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  clearRecorderRunIdempotencyKey,
  recorderRunConfigFields,
  recorderRunIdempotencyKey,
  type RecorderRunConfig,
} from './recorderRunModel';

type StepAction = RecorderStep['action'];
type RecorderSocketState = 'disconnected' | 'connecting' | 'connected' | 'closed' | 'error';
type ElementPreview = { tag?: string; id?: string; class?: string; role?: string | null; name?: string; text?: string; value_redacted?: boolean; attributes?: Record<string, string>; bounding_box?: { x: number; y: number; width: number; height: number }; frame_path?: string[]; shadow_path?: string[]; candidates?: RecorderLocatorCandidate[]; parent_summary?: string; visible?: boolean; actionable?: boolean };
type Frame = { type: string; action?: string; image?: string; url?: string; title?: string; state?: string; steps?: RecorderStep[]; locator_trace?: AITraceEvent[]; locator_verification?: Record<string, unknown> | null; hovered?: ElementPreview | null; tabs?: Array<{index:number;url:string;title:string;active:boolean}>; picked?: (ElementPreview & { action: string; evidence?: RecorderStep['evidence']; ranked_candidates?: RecorderLocatorCandidate[]; selection?: { selected_candidate?: RecorderLocatorCandidate; summary?: RecorderStep['locator_decision'] } | null }) | null; message?: string };
type PendingAgentGoal = { goal: string; sessionId: string; startUrl: string; strategy: 'fast' | 'agent'; waitingForNavigation: boolean; trustedDomains: string[]; minimumFrameRevision?: number };

const actions: StepAction[] = ['navigate','back','scroll','click','double_click','fill','select','check','uncheck','press','hover','wait','assert_visible','assert_text','assert_url','assert_title','assert_count'];
const blankDiff: GitDiffResult = { diff: '', changed_files: [] };
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
  const [searchParams] = useSearchParams();
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
  const [restoreCheckedProjectId, setRestoreCheckedProjectId] = useState<string | null>(null);
  const [socketState, setSocketState] = useState<RecorderSocketState>('disconnected');
  const [socketDetail, setSocketDetail] = useState('');
  const [frame, setFrame] = useState<Frame | null>(null);
  const [steps, setSteps] = useState<RecorderStep[]>([]);
  const [optimization, setOptimization] = useState<Awaited<ReturnType<typeof api.optimizeRecorder>> | null>(null);
  const [previewMode, setPreviewMode] = useState<'raw' | 'optimized'>('raw');
  const previewDrafts = useRef({ raw: '', optimized: '' });
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [caseName, setCaseName] = useState(() => t('defaults.caseName'));
  const [requirement, setRequirement] = useState('');
  const [browserStrategy, setBrowserStrategy] = useState<'fast' | 'agent'>('agent');
  const [trustedDomainsText, setTrustedDomainsText] = useState('');
  const [filePath, setFilePath] = useState('tests/test_recorded_case.py');
  const [testName, setTestName] = useState('test_recorded_case');
  const [suiteName, setSuiteName] = useState(() => t('defaults.suiteName'));
  const [tagsText, setTagsText] = useState('recorder');
  const [markersText, setMarkersText] = useState('');
  const [code, setCode] = useState('');
  const [scriptGeneration, setScriptGeneration] = useState(0);
  const [editorReady, setEditorReady] = useState(false);
  const [showCodeFallback, setShowCodeFallback] = useState(false);
  const [exploreMobilePanel, setExploreMobilePanel] = useState<'browser' | 'task'>('browser');
  const [naturalFlowOpen, setNaturalFlowOpen] = useState(embedded);
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
  const wsRef = useRef<WebSocket | null>(null);
  const frameRevisionRef = useRef(0);
  const urlInputRef = useRef<HTMLInputElement | null>(null);
  const pendingUrlRef = useRef<string | null>(null);
  const browserRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<MonacoEditorInstance | null>(null);
  const stepStorageKey = sessionId ? `ai-qa.recorder.steps.${sessionId}` : '';
  const projectStepsKey = projectId ? `ai-qa.recorder.draft-steps.${projectId}` : '';
  const projectCodeKey = projectId ? `ai-qa.recorder.code.${projectId}` : '';
  const tab = useMemo<EditorTab | undefined>(() => code ? ({ path: filePath, name: filePath.split('/').pop() || 'test.py', content: code, initialContent: code, isDirty: false }) : undefined, [code, filePath]);

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
      setSessionId(saved.id);
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
      setSessionId(saved.id);
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
    if (!sessionId) return;
    let active = true;
    let socket: WebSocket | null = null;
    setSocketState('connecting');
    setSocketDetail('');
    void Promise.all([
      getRecorderSocketUrl(sessionId),
      api.createStreamTicket('recorder', sessionId),
    ]).then(([url, streamTicket]) => {
      if (!active) return;
      const ws = new WebSocket(url);
      socket = ws;
      wsRef.current = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth', stream_ticket: streamTicket }));
        setSocketState('connected');
        setSocketDetail('');
      };
      ws.onclose = (event) => {
        setSocketState(event.code === 1000 ? 'closed' : 'error');
        setSocketDetail(event.code === 1000 ? '' : t('connection.interrupted', { code: event.code }));
      };
      ws.onerror = () => { setSocketState('error'); setSocketDetail(t('connection.error')); };
      ws.onmessage = (event) => {
      if (!active) return;
      const data = JSON.parse(event.data) as Frame;
      if (data.type === 'frame') {
        frameRevisionRef.current += 1;
        setFrame(data);
        if (data.steps) setSteps(data.steps);
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
        if (data.url && !pendingUrlRef.current && document.activeElement !== urlInputRef.current) setUrl(data.url);
      } else if (data.type === 'command_success' && data.action === 'navigate') {
        pendingUrlRef.current = null;
        if (data.url) setUrl(data.url);
        setError('');
        setPendingAgentGoal((pending) => pending?.sessionId === sessionId && pending.waitingForNavigation
          ? { ...pending, waitingForNavigation: false, minimumFrameRevision: frameRevisionRef.current + 1 }
          : pending);
      } else if (data.type === 'error' || data.type === 'command_error') {
        if (data.type === 'command_error' && data.url) pendingUrlRef.current = data.url;
        setPendingAgentGoal((pending) => pending?.sessionId === sessionId ? null : pending);
        setError(recorderErrorMessage(data.message || t('errors.browserOperationFailed'), data.url));
      }
      };
    }).catch((error) => {
      if (active) {
        setSocketState('error');
        setSocketDetail(error instanceof Error ? error.message : t('connection.error'));
      }
    });
    return () => { active = false; socket?.close(); if (wsRef.current === socket) wsRef.current = null; };
  }, [sessionId, recorderErrorMessage, t]);

  useEffect(() => {
    frameRevisionRef.current = 0;
    setFrame(null);
    setPickedElement(null);
    setSelectionMode(false);
    setLocatorTraceEvents([]);
  }, [sessionId]);

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
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action, ...payload }));
  }, []);

  const createSession = async () => {
    if (!projectId) { setError(t('errors.noProject')); return; }
    const startUrl = normalizeBrowserUrl(url);
    setUrl(startUrl);
    setBusy(true); setError('');
    try {
      const created = await api.createRecorderSession(projectId, startUrl, steps);
      setSessionId(created.id); setRecording(false);
      if (created.navigation_error) {
        pendingUrlRef.current = created.requested_url;
        setError(recorderErrorMessage(created.navigation_error, created.requested_url));
      } else pendingUrlRef.current = null;
    } catch (e) { setError(recorderErrorMessage(e, startUrl)); }
    finally { setBusy(false); }
  };

  const closeSession = async () => {
    if (sessionId) { try { await api.closeRecorderSession(sessionId); } catch { /* session may already have ended */ } }
    if (projectId) window.localStorage.removeItem(`ai-qa.recorder.session.${projectId}`);
    wsRef.current?.close(1000); pendingUrlRef.current = null; setSessionId(null); setFrame(null); setRecording(false); setSocketState('disconnected'); setSocketDetail('');
  };

  const navigateBrowser = (target: string) => {
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

  const updateStep = (index: number, patch: Partial<RecorderStep>) => setSteps((current) => current.map((step, i) => {
    if (i !== index) return step;
    const updated = { ...step, ...patch };
    send('edit_step', { step: updated });
    return updated;
  }));
  const updateStepEvidence = (stepId: string, patch: Partial<NonNullable<RecorderStep['evidence']>>) => {
    setSteps((current) => current.map((step) => step.id === stepId
      ? { ...step, evidence: { ...(step.evidence ?? { schema_version: 1, element: {}, context: {}, locator_candidates: [], decision: {}, status: 'partial', missing: [] }), ...patch } }
      : step));
  };
  const requestAiLocator = async (step: RecorderStep) => {
    if (!sessionId || locatorAnalysisBusy) return;
    setAiAnalysisStep(step.id);
    setError('');
    try {
      const result = await api.analyzeRecorderLocator(sessionId, step.id);
      updateStepEvidence(step.id, { ai_analysis: result });
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setAiAnalysisStep(null); }
  };
  const requestJevLocator = async (step: RecorderStep) => {
    if (!sessionId || locatorAnalysisBusy) return;
    setJevDecisionStep(step.id);
    setError('');
    try {
      const result = await api.requestRecorderJevDecision(sessionId, step.id);
      updateStepEvidence(step.id, { jev_analysis: result });
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setJevDecisionStep(null); }
  };
  const verifyCandidate = (step: RecorderStep, candidate?: RecorderLocatorCandidate, source: 'ai' | 'jev' | 'manual' = 'manual') => {
    if (locatorAnalysisBusy || (!step.locator && !candidate)) return;
    send('verify_locator', { step_id: step.id, candidate_id: candidate?.candidate_id, source });
  };

  const addAssertion = (action: StepAction) => {
    const step: RecorderStep = { id: crypto.randomUUID().replaceAll('-', '').slice(0,12), action, description: actionLabel(action), locator: action.startsWith('assert_') && !['assert_url','assert_title'].includes(action) ? { kind:'css', value:'#result', exact:false } : undefined, value: action === 'assert_count' ? '1' : '' };
    setSteps((current) => [...current, step]); send('add_step', { step });
  };

  const generate = async () => {
    if (!sessionId || busy) return;
    setBusy(true); setError('');
    try {
      const result = await api.generateRecorderCode(sessionId, { case_name: caseName, file_path: filePath, test_name: testName, steps });
      setCode(result.code);
      setOptimization(null); setPreviewMode('raw');
      setScriptGeneration((current) => current + 1);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const generateFromAgent = async () => {
    const task = aiTask.task;
    const output = browserAgentOutput;
    if (!sessionId || !task || !output || !canGenerateAgentScript || busy) return;
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
      setOptimization(null);
      setPreviewMode('raw');
      setAgentScriptSource({ taskId: task.id, actionCount: generated.actionCount, jevCount: generated.jevCount, assertionCount: generated.assertionCount });
      setScriptGeneration((current) => current + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  };

  const optimize = async () => {
    if (!sessionId || busy || !steps.length) return;
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
    if (!projectId || !sessionId || agentTaskRunning) return;
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
        setSessionId(created.id);
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
    if (!projectId || !sessionId) throw new Error(t('errors.noRecorderSession'));
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
    if (!projectId || !sessionId) return;
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
    if (!projectId || !sessionId) return;
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
      <input className="recorder-step-field recorder-step-locator" aria-label={t('steps.locator')} value={locatorValue} placeholder={locatorRequired ? t('steps.locator') : t('steps.noLocator')} disabled={!locatorRequired} onChange={(e) => updateStep(index, { locator: { ...(step.locator || {kind:'text', exact:true}), value:e.target.value } })} />
      <input className="recorder-step-field recorder-step-parameter" aria-label={parameterLabel} value={parameter} disabled={step.value_redacted} placeholder={parameterPlaceholder} onChange={(e) => updateStep(index, step.action==='navigate' ? {url:e.target.value} : step.action==='press' ? {key:e.target.value} : {value:e.target.value})} />
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
  const agentTaskRunning = Boolean(aiTask.task && !['COMPLETED','FAILED','BLOCKED','CANCELLED'].includes(aiTask.task.status));
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
    if (!pending || pending.sessionId !== sessionId || pending.waitingForNavigation || !isNavigationFrameFresh(frameRevisionRef.current, pending.minimumFrameRevision) || socketState !== 'connected' || !projectId || aiTask.busy || frame?.type !== 'frame') return;
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
          {recording && <span className="status-pill status-pill-warning">{t('header.recording')}</span>}
        </div>

        <div className="recorder-actions" role="group" aria-label={t('header.actions')} tabIndex={embedded ? 0 : undefined}>
          <button
            type="button"
            className={`btn ${recording ? 'btn-secondary' : 'btn-primary'}`}
            disabled={busy || agentTaskRunning || !sessionId}
            onClick={() => { const next = !recording; setRecording(next); send(recording ? 'pause' : 'start'); }}
          >
            {recording ? <CirclePause size={16} /> : <CirclePlay size={16} />}
            {recording ? t('header.pause') : t('header.start')}
          </button>
          <button type="button" className="btn btn-secondary" disabled={!sessionId || agentTaskRunning} onClick={() => { send('stop'); setRecording(false); }}>
            <Square size={15} /> {t('header.stop')}
          </button>
          <button
            type="button"
            className={`btn ${selectionMode ? 'btn-primary recorder-select-mode-active' : 'btn-secondary'}`}
            disabled={!sessionId || !isConnected || agentTaskRunning}
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
          <button type="button" className="btn btn-secondary" disabled={!sessionId || busy || agentTaskRunning} onClick={generate}>
            <Code2 size={16} /> {busy ? t('header.processing') : code ? t('header.regenerateScript') : t('header.generateScript')}
          </button>
          <button className="btn btn-primary" disabled={!sessionId || !steps.length || busy || aiTask.busy || agentTaskRunning} onClick={() => startAiTask('CREATE_TEST')}>
            <Code2 size={16} /> {t('header.createVerifyTest')}
          </button>
          <button className="btn btn-secondary" disabled={!sessionId || busy || aiTask.busy || agentTaskRunning} onClick={() => startAiTask('EXPLORE_PAGE')}>
            {t('header.explorePage')}
          </button>
          <button type="button" className="btn btn-secondary" disabled={!sessionId || busy || aiTask.busy || agentTaskRunning || !code} onClick={saveAndRun}>
            <Save size={16} /> {t('header.saveAndRun')}
          </button>
        </div>
      </header>

      {error && (
        <section className="alert alert-error recorder-error" role="alert">
          <div className="alert-content">
            <AlertTriangle size={17} aria-hidden="true" />
            <div className="alert-copy">
              <strong>{t('header.errorTitle')}</strong>
              <p>{error}</p>
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
              onClick={() => sessionId ? navigateBrowser(pendingUrlRef.current ?? url) : void createSession()}
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
              disabled={!projectId || !requirement.trim() || busy || aiTask.busy || agentTaskRunning || !!pendingAgentGoal || (!sessionId && restoreCheckedProjectId !== projectId) || (!!sessionId && !isConnected)}
              onClick={() => void startNaturalLanguageFlow()}
            >
              <CirclePlay size={15} aria-hidden="true" />
              {pendingAgentGoal || aiTask.busy || agentTaskRunning
                ? t(browserStrategy === 'agent' ? 'naturalFlow.agentRunning' : 'naturalFlow.fastRunning')
                : t(browserStrategy === 'agent' ? 'naturalFlow.agentStart' : 'naturalFlow.fastStart')}
            </button>
            {canGenerateAgentScript && (
              <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void generateFromAgent()}>
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
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && navigateBrowser(url)}
          placeholder={t('naturalFlow.addressPlaceholder')}
        />
        <button type="button" className="btn btn-secondary btn-icon" aria-label={t('naturalFlow.back')} title={t('naturalFlow.back')} disabled={!sessionId} onClick={() => send('back')}>←</button>
        <button type="button" className="btn btn-secondary btn-icon" aria-label={t('naturalFlow.forward')} title={t('naturalFlow.forward')} disabled={!sessionId} onClick={() => send('forward')}>→</button>
        <button type="button" className="btn btn-secondary btn-icon" aria-label={t('naturalFlow.reload')} title={t('naturalFlow.reload')} disabled={!sessionId} onClick={() => send('reload')}><RotateCw size={16} /></button>
        {!sessionId ? (
          <button type="button" className="btn btn-primary" disabled={busy || restoreCheckedProjectId !== projectId} onClick={createSession}>{t('naturalFlow.startBrowser')}</button>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={closeSession}>{t('naturalFlow.closeBrowser')}</button>
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
            <select aria-label={t('steps.addAssertion')} defaultValue="" onChange={(e) => { if (e.target.value) addAssertion(e.target.value as StepAction); e.target.value = ''; }}>
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
                    <select className="recorder-step-field recorder-step-action" aria-label={t('steps.actionType')} value={step.action} onChange={(e) => updateStep(index, { action: e.target.value as StepAction })}>
                      {actions.map((action) => <option key={action} value={action}>{actionLabel(action)}</option>)}
                    </select>
                    <input className="recorder-step-field recorder-step-description" aria-label={t('steps.description')} value={step.description} onChange={(e) => updateStep(index, { description: e.target.value })} />
                    {actionInputs(step, index)}
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm recorder-step-pick"
                      title={t('steps.pickTitle')}
                      disabled={!sessionId || !isConnected || locatorAnalysisBusy}
                      onClick={() => { pickTargetStepRef.current = step.id; setPickTargetStep(step.id); setSelectionMode(true); send('pick_element', { step_action: step.action }); }}
                    >
                      <Crosshair size={14} />{pickTargetStep === step.id ? t('steps.pickPrompt') : t('steps.pick')}
                    </button>
                    <div className="recorder-step-controls">
                      <button type="button" className="btn btn-secondary btn-icon" aria-label={t('steps.reverify')} title={t('steps.reverify')} disabled={!sessionId || !step.locator || locatorAnalysisBusy} onClick={() => verifyCandidate(step)}><RotateCw size={14} /></button>
                      <button type="button" className="btn btn-secondary btn-icon" aria-label={t('steps.moveUp')} title={t('steps.moveUp')} disabled={index === 0} onClick={() => { const next = [...steps]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; setSteps(next); send('reorder', { ids: next.map((s) => s.id) }); }}><ArrowUp size={14} /></button>
                      <button type="button" className="btn btn-secondary btn-icon" aria-label={t('steps.moveDown')} title={t('steps.moveDown')} disabled={index === steps.length - 1} onClick={() => { const next = [...steps]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; setSteps(next); send('reorder', { ids: next.map((s) => s.id) }); }}><ArrowDown size={14} /></button>
                      <button type="button" className="btn btn-secondary btn-icon" aria-label={t('steps.delete')} title={t('steps.delete')} onClick={() => { setSteps(steps.filter((_, i) => i !== index)); send('delete_step', { id: step.id }); }}><Trash2 size={14} /></button>
                    </div>
                  </div>
                  {evidence && <details className="recorder-step-evidence">
                    <summary>{t('steps.evidenceSummary', { version: evidence.schema_version, count: evidence.locator_candidates.length, status: t(evidence.status === 'available' ? 'steps.evidenceAvailable' : evidence.status === 'stale' ? 'steps.evidenceStale' : 'steps.evidencePartial') })}</summary>
                    <div className="recorder-evidence-actions">
                      <button type="button" className="btn btn-secondary btn-sm" disabled={!sessionId || locatorAnalysisBusy} onClick={() => void requestAiLocator(step)}>{aiAnalysisStep === step.id ? t('steps.analyzing') : t('steps.requestAiAnalysis')}</button>
                      <button type="button" className="btn btn-secondary btn-sm" disabled={!sessionId || locatorAnalysisBusy} onClick={() => void requestJevLocator(step)}>{jevDecisionStep === step.id ? t('steps.jevDeciding') : t('steps.requestJevDecision')}</button>
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
                            <button type="button" className="btn btn-secondary btn-sm" disabled={!sessionId || locatorAnalysisBusy} onClick={() => verifyCandidate(step, candidate)}>{step.locator?.value === candidate.value && step.locator?.kind === candidate.kind ? t('steps.validateCurrent') : t('steps.verifyAndUse')}</button>
                            {aiRecommended && <button type="button" className="btn btn-secondary btn-sm" disabled={!sessionId || locatorAnalysisBusy} onClick={() => verifyCandidate(step, candidate, 'ai')}>{t('steps.useAi')}</button>}
                            {jevRecommended && <button type="button" className="btn btn-secondary btn-sm" disabled={!sessionId || locatorAnalysisBusy} onClick={() => verifyCandidate(step, candidate, 'jev')}>{t('steps.useJev')}</button>}
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
                <button type="button" className="btn btn-secondary btn-sm" disabled={!sessionId || !steps.length || busy} onClick={() => void optimize()}>{t('script.optimize')}</button>
                {code && (
                  <>
                    <button type="button" className="btn btn-secondary btn-sm" aria-label={t('script.regenerateAria')} title={t('script.regenerateTitle')} disabled={!sessionId || busy} onClick={generate}>
                      <RotateCw size={13} aria-hidden="true" /> {t('script.regenerate')}
                    </button>
                    <button type="button" className="btn btn-primary btn-sm" disabled={!sessionId || busy} onClick={() => void openRecordedCaseInStudio()}>
                      <Code2 size={13} aria-hidden="true" /> {t('script.saveOpen')}
                    </button>
                  </>
                )}
              </div>
            </div>
            {optimization && <div className="recorder-optimization-summary"><div role="group" aria-label={t('script.optimizationComparison')}><button type="button" className="btn btn-secondary btn-sm" aria-pressed={previewMode === 'raw'} onClick={() => { switchPreview('raw'); }}>{t('script.raw', { count: optimization.raw_steps.length })}</button> <button type="button" className="btn btn-secondary btn-sm" aria-pressed={previewMode === 'optimized'} onClick={() => { switchPreview('optimized'); }}>{t('script.optimized', { count: optimization.optimized_steps.length })}</button></div><p>{optimization.provider} / {optimization.model} · {optimization.prompt_version} · {t('script.needsVerification')}</p><details><summary>{t('script.optimizationBasis')}</summary><ul>{optimization.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></details></div>}
            <div className="recorder-editor-surface">
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
