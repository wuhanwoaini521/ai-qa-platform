import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AlertTriangle, ArrowDown, ArrowUp, CirclePause, CirclePlay, Code2, Crosshair, MousePointer2, RotateCw, Save, Square, Trash2 } from 'lucide-react';
import { api, getRecorderSocketUrl } from '../api/client';
import { AIExecutionTimeline } from '../components/AIExecutionTimeline';
import { ContextTaskProgress, useContextTask } from '../components/ContextTaskProgress';
import { MonacoEditorPane, MonacoEditorInstance } from '../features/automation-studio/components/MonacoEditorPane';
import { EditorTab } from '../features/automation-studio/types';
import { AITraceEvent, GitDiffResult, Project, RecorderStep, TestCasePriority, TestRunCreate } from '../types';
import { flowStartUrl, isNavigationFrameFresh, normalizeTrustedDomains } from './browserGoalModel';
import { recorderStepsFromAgent } from './recorderAgentModel';
import {
  clearRecorderRunIdempotencyKey,
  recorderRunConfigFields,
  recorderRunIdempotencyKey,
  type RecorderRunConfig,
} from './recorderRunModel';

type StepAction = RecorderStep['action'];
type Frame = { type: string; action?: string; image?: string; url?: string; title?: string; state?: string; steps?: RecorderStep[]; locator_trace?: AITraceEvent[]; tabs?: Array<{index:number;url:string;title:string;active:boolean}>; picked?: { action: string; name?: string; frame_path?: string[]; ranked_candidates?: RecorderStep['locator'][]; selection?: { selected_candidate?: RecorderStep['locator']; summary?: RecorderStep['locator_decision'] } | null } | null; message?: string };
type PendingAgentGoal = { goal: string; sessionId: string; startUrl: string; strategy: 'fast' | 'agent'; waitingForNavigation: boolean; trustedDomains: string[]; minimumFrameRevision?: number };

const actions: StepAction[] = ['navigate','back','scroll','click','double_click','fill','select','check','uncheck','press','hover','wait','assert_visible','assert_text','assert_url','assert_title','assert_count'];
const labels: Record<StepAction, string> = { navigate:'打开页面', back:'返回上一页', scroll:'滚动页面', click:'点击', double_click:'双击', fill:'填写', select:'选择', check:'勾选', uncheck:'取消勾选', press:'按键', hover:'悬停', wait:'等待', assert_visible:'断言可见', assert_text:'断言文本', assert_url:'断言 URL', assert_title:'断言标题', assert_count:'断言数量' };
const blankDiff: GitDiffResult = { diff: '', changed_files: [] };
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
const recorderErrorMessage = (error: unknown, targetUrl?: string): string => {
  const message = error instanceof Error ? error.message : String(error);
  if (message.includes('ERR_NETWORK_ACCESS_DENIED')) {
    const target = targetUrl ? `“${targetUrl}”` : '目标网页';
    return `录制器浏览器运行在 API 服务所在主机，当前无法访问${target}（ERR_NETWORK_ACCESS_DENIED）。请使用 API 主机可访问的地址，或在 API 服务配置 BROWSER_PROXY_URL 后重试。`;
  }
  return message;
};

export const RecorderPage: React.FC<{
  projects: Project[];
  selectedProjectId: string | null;
  embedded?: boolean;
  onNavigateToRuns?: (runId: string) => void;
  runConfig?: RecorderRunConfig;
}> = ({ projects, selectedProjectId, embedded = false, onNavigateToRuns, runConfig }) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedSessionId = searchParams.get('session_id');
  const projectId = selectedProjectId ?? projects[0]?.id ?? null;
  const [url, setUrl] = useState('about:blank');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [restoreCheckedProjectId, setRestoreCheckedProjectId] = useState<string | null>(null);
  const [socketState, setSocketState] = useState('未连接');
  const [frame, setFrame] = useState<Frame | null>(null);
  const [steps, setSteps] = useState<RecorderStep[]>([]);
  const [optimization, setOptimization] = useState<Awaited<ReturnType<typeof api.optimizeRecorder>> | null>(null);
  const [previewMode, setPreviewMode] = useState<'raw' | 'optimized'>('raw');
  const previewDrafts = useRef({ raw: '', optimized: '' });
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [caseName, setCaseName] = useState('录制的浏览器用例');
  const [requirement, setRequirement] = useState('');
  const [browserStrategy, setBrowserStrategy] = useState<'fast' | 'agent'>('agent');
  const [trustedDomainsText, setTrustedDomainsText] = useState('');
  const [filePath, setFilePath] = useState('tests/test_recorded_case.py');
  const [testName, setTestName] = useState('test_recorded_case');
  const [suiteName, setSuiteName] = useState('录制用例');
  const [tagsText, setTagsText] = useState('recorder');
  const [markersText, setMarkersText] = useState('');
  const [code, setCode] = useState('');
  const [scriptGeneration, setScriptGeneration] = useState(0);
  const [editorReady, setEditorReady] = useState(false);
  const [showCodeFallback, setShowCodeFallback] = useState(false);
  const [pendingAgentGoal, setPendingAgentGoal] = useState<PendingAgentGoal | null>(null);
  const [agentScriptSource, setAgentScriptSource] = useState<{ taskId: string; actionCount: number; jevCount: number; assertionCount: number } | null>(null);
  const [pickTargetStep, setPickTargetStep] = useState<string | null>(null);
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
  }, [projectId, requestedSessionId, sessionId]);

  useEffect(() => {
    if (!projectId || !requestedSessionId || sessionId === requestedSessionId) return;
    let active = true;
    void api.getRecorderSession(requestedSessionId).then((saved) => {
      if (!active) return;
      if (saved.project_id !== projectId) {
        setError('该浏览器会话不属于当前项目。请先切换到所属项目。');
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
  }, [projectId, requestedSessionId, sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    let socket: WebSocket | null = null;
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
        setSocketState('已连接');
      };
      ws.onclose = (event) => { setSocketState(event.code === 1000 ? '已关闭' : `连接中断 (${event.code})`); };
      ws.onerror = () => setSocketState('连接错误');
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
        if (data.picked && pickTargetStepRef.current) {
          const best = data.picked.selection?.selected_candidate ?? data.picked.ranked_candidates?.[0];
          if (best) {
            setCode('');
            setSteps((current) => current.map((step) => {
              if (step.id !== pickTargetStepRef.current) return step;
              const updated = { ...step, locator: best, frame_path: data.picked?.frame_path || [], locator_decision: data.picked?.selection?.summary ?? null };
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
        setError(recorderErrorMessage(data.message || '浏览器操作失败', data.url));
      }
      };
    }).catch((error) => {
      if (active) setSocketState(error instanceof Error ? error.message : '连接错误');
    });
    return () => { active = false; socket?.close(); if (wsRef.current === socket) wsRef.current = null; };
  }, [sessionId]);

  useEffect(() => {
    frameRevisionRef.current = 0;
    setFrame(null);
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
    if (!projectId) { setError('请先创建或选择项目'); return; }
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
    wsRef.current?.close(1000); pendingUrlRef.current = null; setSessionId(null); setFrame(null); setRecording(false);
  };

  const navigateBrowser = (target: string) => {
    const normalized = normalizeBrowserUrl(target);
    pendingUrlRef.current = normalized;
    setError('');
    setFrame(null);
    setUrl(normalized); send('navigate', { url: normalized });
  };

  const browserKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      urlInputRef.current?.focus();
      return;
    }
    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) send('type', { text: event.key });
    else if (['Enter','Tab','Escape','Backspace','Delete','ArrowDown','ArrowUp','ArrowLeft','ArrowRight',' '].includes(event.key)) { event.preventDefault(); send('press', { key: event.key === ' ' ? 'Space' : event.key }); }
  };

  const browserClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const scale = Math.min(bounds.width / 1280, bounds.height / 720);
    const offsetX = (bounds.width - 1280 * scale) / 2;
    const offsetY = 0;
    send(event.detail > 1 ? 'double_click' : 'click', { x: (event.clientX - bounds.left - offsetX) / scale, y: (event.clientY - bounds.top - offsetY) / scale });
    event.currentTarget.focus();
  };

  const updateStep = (index: number, patch: Partial<RecorderStep>) => setSteps((current) => current.map((step, i) => {
    if (i !== index) return step;
    const updated = { ...step, ...patch };
    send('edit_step', { step: updated });
    return updated;
  }));
  const addAssertion = (action: StepAction) => {
    const step: RecorderStep = { id: crypto.randomUUID().replaceAll('-', '').slice(0,12), action, description: labels[action], locator: action.startsWith('assert_') && !['assert_url','assert_title'].includes(action) ? { kind:'css', value:'#result', exact:false } : undefined, value: action === 'assert_count' ? '1' : '' };
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
    if (!startUrl) { setError('Agent 任务缺少有效的起始网址，不能生成脚本。'); return; }
    const generated = recorderStepsFromAgent(output, startUrl);
    if (!generated || generated.actionCount === 0) { setError('这次 Agent 执行没有可复用的成功动作，未生成脚本。'); return; }

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
      goal: type === 'CREATE_TEST' ? (requirement.trim() || `根据录制步骤生成并验证测试：${caseName}`) : `探索并总结页面：${url}`,
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
    if (!projectId) { setError('请先创建或选择项目'); return; }
    if (goal.length < 8) { setError('请用自然语言描述完整操作流程'); return; }
    const currentPageUrl = frame?.url && frame.url !== 'about:blank' ? frame.url : url;
    const startUrl = flowStartUrl(goal, currentPageUrl);
    if (!startUrl) { setError('请在操作描述中写入起始网址，例如 uniqlo.com'); return; }

    setBusy(true);
    setError('');
    setPendingAgentGoal(null);
    setAgentScriptSource(null);
    try {
      if (!sessionId) {
        setSocketState('连接中');
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
      if (!isConnected) throw new Error('浏览器连接尚未就绪，请稍后重试。');
      const currentUrl = normalizedHttpUrl(currentPageUrl);
      const needsNavigation = currentUrl !== startUrl;
      setPendingAgentGoal({ goal, sessionId, startUrl, strategy, waitingForNavigation: needsNavigation, trustedDomains });
      if (needsNavigation) navigateBrowser(startUrl);
    } catch (cause) {
      setPendingAgentGoal(null);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  };

  const saveAndRun = async () => {
    if (!projectId || !sessionId) return;
    if (!code.trim()) { await generate(); return; }
    setBusy(true); setError('');
    try {
      const normalizedPath = filePath.replaceAll('\\', '/').replace(/^\/+/, '');
      if (!normalizedPath.endsWith('.py') || normalizedPath.split('/').includes('..')) throw new Error('请输入项目内的 .py 文件路径');
      await api.writeWorkspaceFile(projectId, normalizedPath, code);
      const tags = [...new Set([...tagsText.split(',').map((tag)=>tag.trim()).filter(Boolean), ...(suiteName.trim() ? [`suite:${suiteName.trim()}`] : [])])];
      const normalizedTestName = testName.replace(/\W+/g, '_').replace(/^_+|_+$/g, '') || 'test_recorded_case';
      const safeTestName = normalizedTestName.startsWith('test_') ? normalizedTestName : `test_${normalizedTestName}`;
      const savedCase = await api.saveRecorderCase(sessionId, {
        test_case: {
          project_id: projectId,
          title: caseName,
          steps: steps.map((step) => step.description || labels[step.action]),
          expected_result: '所有录制步骤及断言执行通过',
          priority,
          automation_status: 'AUTOMATED',
          tags,
        },
        file_path: normalizedPath,
        test_name: safeTestName,
      });
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
    const parameter = step.action === 'navigate' ? step.url ?? '' : step.action === 'press' ? step.key ?? '' : step.value ?? '';
    return <>
      <input className="recorder-step-field recorder-step-locator" aria-label="步骤定位器" value={locatorValue} placeholder={locatorRequired ? '定位器' : '无定位器'} disabled={!locatorRequired} onChange={(e) => updateStep(index, { locator: { ...(step.locator || {kind:'text', exact:true}), value:e.target.value } })} />
      <input className="recorder-step-field recorder-step-parameter" aria-label="步骤参数" value={parameter} placeholder={step.action==='wait'?'毫秒':step.action==='scroll'?'方向（up/down）':step.action==='assert_count'?'数量':'参数 / 断言值'} onChange={(e) => updateStep(index, step.action==='navigate' ? {url:e.target.value} : step.action==='press' ? {key:e.target.value} : {value:e.target.value})} />
    </>;
  };

  const projectName = projects.find((project) => project.id === projectId)?.name;
  const isConnected = socketState === '已连接';
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
  const locatorEngine = String(locatorDecisionMetadata.engine ?? 'Local Strategy');
  const locatorModel = locatorEngine === 'Jev' && typeof locatorDecisionMetadata.model === 'string' ? locatorDecisionMetadata.model : '';
  const locatorLatency = locatorEngine === 'Jev' && typeof locatorDecisionMetadata.latency_ms === 'number' ? `${locatorDecisionMetadata.latency_ms.toFixed(1)} ms` : '';

  useEffect(() => {
    const pending = pendingAgentGoal;
    if (!pending || pending.sessionId !== sessionId || pending.waitingForNavigation || !isNavigationFrameFresh(frameRevisionRef.current, pending.minimumFrameRevision) || socketState !== '已连接' || !projectId || aiTask.busy || frame?.type !== 'frame') return;
    if (!/^https?:\/\//i.test(frame.url || '')) {
      setPendingAgentGoal(null);
      setError(`浏览器已连接，但没有加载出可操作的网页（${frame.url || '空白页面'}）。请检查目标网址和 API 主机的网络/代理后重试。`);
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
  }, [pendingAgentGoal, sessionId, socketState, projectId, aiTask.busy, aiTask.start, frame]);

  return (
    <div className={`recorder-page${embedded ? ' is-embedded' : ''}`}>
      <header className="recorder-page-header">
        <div className="recorder-page-heading">
          <h2><MousePointer2 size={20} aria-hidden="true" /> 浏览器录制器</h2>
          {projectName && <span className="recorder-project-label">{projectName}</span>}
          <span className={`status-pill ${isConnected ? 'status-pill-online' : 'status-pill-draft'}`}>
            会话：{socketState}
          </span>
          {recording && <span className="status-pill status-pill-warning">正在录制</span>}
        </div>

        <div className="recorder-actions" role="group" aria-label="录制器操作">
          <button
            type="button"
            className={`btn ${recording ? 'btn-secondary' : 'btn-primary'}`}
            disabled={busy || agentTaskRunning || !sessionId}
            onClick={() => { const next = !recording; setRecording(next); send(recording ? 'pause' : 'start'); }}
          >
            {recording ? <CirclePause size={16} /> : <CirclePlay size={16} />}
            {recording ? '暂停录制' : '开始录制'}
          </button>
          <button type="button" className="btn btn-secondary" disabled={!sessionId || agentTaskRunning} onClick={() => { send('stop'); setRecording(false); }}>
            <Square size={15} /> 停止
          </button>
          <button type="button" className="btn btn-secondary" disabled={!sessionId || busy || agentTaskRunning} onClick={generate}>
            <Code2 size={16} /> {busy ? '正在处理…' : code ? '重新生成脚本' : '生成脚本'}
          </button>
          <button className="btn btn-primary" disabled={!sessionId || !steps.length || busy || aiTask.busy || agentTaskRunning} onClick={() => startAiTask('CREATE_TEST')}>
            <Code2 size={16} /> 录制步骤生成并验证测试
          </button>
          <button className="btn btn-secondary" disabled={!sessionId || busy || aiTask.busy || agentTaskRunning} onClick={() => startAiTask('EXPLORE_PAGE')}>
            AI 探索当前页
          </button>
          <button type="button" className="btn btn-secondary" disabled={!sessionId || busy || aiTask.busy || agentTaskRunning || !code} onClick={saveAndRun}>
            <Save size={16} /> 保存为 Case 并运行
          </button>
        </div>
      </header>

      {error && (
        <section className="alert alert-error recorder-error" role="alert">
          <div className="alert-content">
            <AlertTriangle size={17} aria-hidden="true" />
            <div className="alert-copy">
              <strong>浏览器连接或操作未完成</strong>
              <p>{error}</p>
              <details className="alert-details">
                <summary>查看错误详情</summary>
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
              重试
            </button>
          </div>
        </section>
      )}

      <section className="recorder-natural-flow" aria-labelledby="recorder-natural-flow-title">
        <div className="recorder-natural-flow-prompt">
          <label id="recorder-natural-flow-title" htmlFor="recorder-natural-flow-input">自然语言操作流程</label>
          <textarea
            id="recorder-natural-flow-input"
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
            placeholder="例如：打开浏览器并访问 uniqlo.com，选择裤子分类，进入第一个商品详情页，然后加入购物车。"
            rows={3}
          />
          <details className="recorder-trusted-domains">
            <summary>官网验证域名（可选）</summary>
            <input
              aria-label="官网验证域名"
              value={trustedDomainsText}
              onChange={(event) => setTrustedDomainsText(event.target.value)}
              placeholder="例如 selenium.dev；多个域名用逗号分隔"
            />
            <small>用于确认“官网”目标。留空时 Agent 不会把搜索结果中的品牌词当作官网证明。</small>
          </details>
        </div>
        <div className="recorder-natural-flow-actions">
          <p>{browserStrategy === 'agent'
            ? 'Agent 由 AI 根据实时页面提出候选，Jev 在多种安全动作之间选择；所有动作都会重新验证并检查页面结果。'
            : 'Fast 由 AI 提出候选并优先按 AI 排序选择；除非平台策略要求，否则跳过 Jev。所有动作仍会重新验证目标并检查页面结果。'} 脚本只收录已执行且可复用的操作，并附加页面证据断言。</p>
          <div>
            <label className="recorder-strategy-control">
              <span>策略</span>
              <select aria-label="浏览执行策略" value={browserStrategy} disabled={Boolean(pendingAgentGoal || aiTask.busy || agentTaskRunning)} onChange={(event) => setBrowserStrategy(event.target.value as 'fast' | 'agent')}>
                <option value="agent">Agent · AI + Jev</option>
                <option value="fast">Fast · AI 优先</option>
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
                ? `${browserStrategy === 'agent' ? 'Agent' : 'Fast'} 正在执行…`
                : browserStrategy === 'agent' ? 'AI + Jev 执行流程' : 'Fast 快速执行'}
            </button>
            {canGenerateAgentScript && (
              <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void generateFromAgent()}>
                <Code2 size={15} aria-hidden="true" /> {busy ? '正在生成脚本…' : '从已验证过程生成脚本'}
              </button>
            )}
          </div>
          {agentScriptSource && (
            <small role="status">
              脚本来源：{agentScriptSource.actionCount} 个成功操作 · {agentScriptSource.jevCount} 次 Jev 决策 · {agentScriptSource.assertionCount} 条页面断言。保存后仍需运行验证。
            </small>
          )}
        </div>
      </section>

      <ContextTaskProgress task={aiTask.task} error={aiTask.error} />

      <div className="recorder-urlbar">
        <input
          ref={urlInputRef}
          className="recorder-url-input"
          aria-label="浏览器地址"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && navigateBrowser(url)}
          placeholder="输入网址"
        />
        <button type="button" className="btn btn-secondary btn-icon" aria-label="后退" title="后退" disabled={!sessionId} onClick={() => send('back')}>←</button>
        <button type="button" className="btn btn-secondary btn-icon" aria-label="前进" title="前进" disabled={!sessionId} onClick={() => send('forward')}>→</button>
        <button type="button" className="btn btn-secondary btn-icon" aria-label="刷新" title="刷新" disabled={!sessionId} onClick={() => send('reload')}><RotateCw size={16} /></button>
        {!sessionId ? (
          <button type="button" className="btn btn-primary" disabled={busy || restoreCheckedProjectId !== projectId} onClick={createSession}>启动浏览器</button>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={closeSession}>关闭浏览器</button>
        )}
      </div>

      <div className="recorder-workspace">
        <section className="recorder-panel recorder-browser-panel">
          <div className="recorder-panel-heading">
            <strong>浏览器视图</strong>
            <span className="recorder-keyboard-hint" id="recorder-keyboard-help">Shift + Esc 返回页面控件</span>
            <span className="recorder-browser-meta" title={`${frame?.title || '远程浏览器画面'} · ${frame?.url || url}`}>
              {frame?.title || '远程浏览器画面'} · {frame?.url || url}
            </span>
          </div>
          <div
            ref={browserRef}
            className="recorder-browser-viewport"
            role="region"
            tabIndex={0}
            aria-label="远程浏览器交互视图"
            aria-describedby="recorder-keyboard-help"
            onClick={browserClick}
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
              <img className="recorder-browser-image" draggable={false} src={`data:image/jpeg;base64,${frame.image}`} alt="远程浏览器实时画面" />
            ) : (
              <div className="recorder-browser-empty">
                <MousePointer2 size={22} aria-hidden="true" />
                <strong>浏览器画面将在这里显示</strong>
                <span>启动浏览器后即可开始录制与拾取定位器</span>
              </div>
            )}
          </div>
          {frame?.tabs && frame.tabs.length > 1 && (
            <div className="recorder-browser-tabs" role="group" aria-label="浏览器标签页">
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

        <section className={`recorder-panel recorder-inspector-panel${locatorTraceEvents.length ? ' has-locator-trace' : ''}`}>
          <div className="recorder-steps-heading">
            <div>
              <strong>执行步骤</strong>
              <span className="recorder-step-count">{steps.length}</span>
            </div>
            <select aria-label="添加断言" defaultValue="" onChange={(e) => { if (e.target.value) addAssertion(e.target.value as StepAction); e.target.value = ''; }}>
              <option value="">+ 添加断言</option>
              <option value="assert_visible">元素可见</option>
              <option value="assert_text">包含文本</option>
              <option value="assert_url">URL 匹配</option>
              <option value="assert_title">标题匹配</option>
              <option value="assert_count">元素数量</option>
            </select>
          </div>

          {locatorTraceEvents.length > 0 && (
            <div className="recorder-locator-trace">
              <strong>Locator Decision</strong>
              <div className={`recorder-locator-summary${locatorVerificationMetadata.verified === true ? ' is-verified' : locatorVerificationMetadata.verified === false ? ' is-unverified' : ''}`} role="status">
                <span>
                  Decision Engine: {locatorEngine}
                  {locatorModel ? ` · Model ${locatorModel}` : ''}
                  {locatorLatency ? ` · Latency ${locatorLatency}` : ''}
                  {' · Selected '}{String(locatorDecisionMetadata.candidate_id ?? 'unavailable')}
                  {' · '}{typeof locatorDecisionMetadata.candidate_count === 'number' ? locatorDecisionMetadata.candidate_count : '—'} 候选
                </span>
                <span>
                  Verification: {locatorVerificationMetadata.verified === true ? 'PASS' : locatorVerificationMetadata.verified === false ? 'FAILED' : 'UNKNOWN'}
                  {typeof locatorDecisionMetadata.selected_locator === 'string' ? ` · ${locatorDecisionMetadata.selected_locator}` : ''}
                  {verificationFacts.length > 0 ? ` · ${verificationFacts.join(' · ')}` : ''}
                </span>
              </div>
              <AIExecutionTimeline events={locatorTraceEvents} running={false} />
            </div>
          )}

          <div className="recorder-steps-list">
            {steps.map((step, index) => (
              <div key={step.id} className="recorder-step-row">
                <select className="recorder-step-field recorder-step-action" aria-label="步骤类型" value={step.action} onChange={(e) => updateStep(index, { action: e.target.value as StepAction })}>
                  {actions.map((action) => <option key={action} value={action}>{labels[action]}</option>)}
                </select>
                <input className="recorder-step-field recorder-step-description" aria-label="步骤说明" value={step.description} onChange={(e) => updateStep(index, { description: e.target.value })} />
                {actionInputs(step, index)}
                <button
                  type="button"
                  className="btn btn-secondary btn-sm recorder-step-pick"
                  title="从内置浏览器拾取此步骤定位器"
                  disabled={!sessionId}
                  onClick={() => { pickTargetStepRef.current = step.id; setPickTargetStep(step.id); send('pick_element', { step_action: step.action }); }}
                >
                  <Crosshair size={14} />{pickTargetStep === step.id ? '请在页面点击' : '拾取'}
                </button>
                <div className="recorder-step-controls">
                  <button type="button" className="btn btn-secondary btn-icon" aria-label="上移步骤" title="上移" disabled={index === 0} onClick={() => { const next = [...steps]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; setSteps(next); send('reorder', { ids: next.map((s) => s.id) }); }}><ArrowUp size={14} /></button>
                  <button type="button" className="btn btn-secondary btn-icon" aria-label="下移步骤" title="下移" disabled={index === steps.length - 1} onClick={() => { const next = [...steps]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; setSteps(next); send('reorder', { ids: next.map((s) => s.id) }); }}><ArrowDown size={14} /></button>
                  <button type="button" className="btn btn-secondary btn-icon" aria-label="删除步骤" title="删除" onClick={() => { setSteps(steps.filter((_, i) => i !== index)); send('delete_step', { id: step.id }); }}><Trash2 size={14} /></button>
                </div>
              </div>
            ))}
            {!steps.length && <div className="recorder-steps-empty">浏览器交互会自动记录为步骤，也可以通过“添加断言”补充验证条件。</div>}
          </div>

          <details className="recorder-case-settings">
            <summary>用例和文件设置</summary>
            <div className="recorder-settings-grid">
              <label>Case 名称<input aria-label="Case 名称" value={caseName} onChange={(e) => setCaseName(e.target.value)} /></label>
              <label>测试函数名<input aria-label="测试函数名" value={testName} onChange={(e) => setTestName(e.target.value)} /></label>
              <label>项目文件路径<input aria-label="项目文件路径" value={filePath} onChange={(e) => setFilePath(e.target.value)} /></label>
              <label>优先级<select value={priority} onChange={(e) => setPriority(e.target.value as TestCasePriority)}><option value="P1">高优先级</option><option value="P2">中优先级</option><option value="P3">低优先级</option></select></label>
              <label>Test Suite / Module<input aria-label="Test Suite / Module" value={suiteName} onChange={(e) => setSuiteName(e.target.value)} placeholder="Test Suite / Module" /></label>
              <label>Case tags<input aria-label="Case tags" value={tagsText} onChange={(e) => setTagsText(e.target.value)} placeholder="标签，逗号分隔" /></label>
              <label>Pytest markers<input aria-label="Pytest markers" value={markersText} onChange={(e) => setMarkersText(e.target.value)} placeholder="pytest marker，逗号分隔" /></label>
            </div>
          </details>

          <div className="recorder-editor-panel">
            <div className="recorder-panel-heading">
              <strong>生成的 Python 脚本</strong>
              <div className="recorder-editor-actions">
                <span>Playwright</span>
                <button type="button" className="btn btn-secondary btn-sm" disabled={!sessionId || !steps.length || busy} onClick={() => void optimize()}>AI 优化录制</button>
                {code && (
                  <button type="button" className="btn btn-secondary btn-sm" aria-label="重新生成 Python 脚本" title="按当前执行步骤重新生成，替换当前脚本内容" disabled={!sessionId || busy} onClick={generate}>
                    <RotateCw size={13} aria-hidden="true" /> 重新生成
                  </button>
                )}
              </div>
            </div>
            {optimization && <div className="recorder-optimization-summary"><div role="group" aria-label="录制优化对照"><button type="button" className="btn btn-secondary btn-sm" aria-pressed={previewMode === 'raw'} onClick={() => { switchPreview('raw'); }}>Raw · {optimization.raw_steps.length} 步</button> <button type="button" className="btn btn-secondary btn-sm" aria-pressed={previewMode === 'optimized'} onClick={() => { switchPreview('optimized'); }}>Optimized · {optimization.optimized_steps.length} 步</button></div><p>{optimization.provider} / {optimization.model} · {optimization.prompt_version} · 待运行验证</p><details><summary>查看优化依据</summary><ul>{optimization.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></details></div>}
            <div className="recorder-editor-surface">
              <MonacoEditorPane activeTab={tab} loadingFile={false} showDiffView={false} diffResult={blankDiff} editorRef={editorRef} stickyScroll={false} onEditorReady={() => { setEditorReady(true); setShowCodeFallback(false); }} onChange={(value) => setCode(value || '')} />
              {showCodeFallback && !editorReady && (
                <textarea aria-label="生成的 Python 脚本" value={code} onChange={(event) => setCode(event.target.value)} spellCheck={false} />
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};
