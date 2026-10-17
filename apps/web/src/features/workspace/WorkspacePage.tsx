import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, FileCode2, GitBranch, PanelLeftClose, PanelLeftOpen, PanelRightOpen, Play, Search, Sparkles, Workflow, X } from 'lucide-react';
import { api } from '../../api/client';
import { useProjectScope, useRouteProjectScope } from '../../app/ProjectScope';
import { buildProjectDisplayNames } from '../../app/projectSelectionModel';
import {
  buildWorkspaceHref,
  readWorkspaceContext,
  resolveCanonicalFile,
  writeWorkspaceContext,
  type WorkspaceContext,
  type WorkspaceStage,
  type WorkspaceView,
} from '../../app/workspaceContext';
import { RequirementsPage } from '../requirements/RequirementsPage';
import { TestCasesPage } from '../test-cases/TestCasesPage';
import { FailuresPage } from '../../pages/FailuresPage';
import { useRunStore } from '../runs/useRunStore';
import { useRuntimeSnapshot } from '../runtime/useRuntimeSnapshot';
import { RuntimeDetail, type RuntimeTab } from '../runtime/RuntimeDetail';
import { WorkspaceRunResult } from './WorkspaceRunResult';
import { QualityDiscoveryPanel } from './QualityDiscoveryPanel';
import { failureSourceLocation } from '../failures/failureWorkspaceModel';
import { WorkspaceRunDock, type WorkspaceRunConfig } from './WorkspaceRunDock';
import { bindingForSelectedCase, configForRerun, defaultWorkspaceGoal, workspaceGoalTarget, workspaceRunCaseLabel } from './workspaceRunModel';
import { workspacePanelMode } from './workspaceLayoutModel';
import type { AgentGoalPreview, AgentTask, AutomationBinding, FailureRecord, Project, Requirement, TestCase, TestRun } from '../../types';
import type { RuntimeSnapshot } from '../../types/runtime';
import { runtimeActive } from '../runtime/runtimeModel';
import './workspace.css';

const AutomationStudioPage = lazy(() => import('../automation-studio/AutomationStudioPage').then((module) => ({ default: module.AutomationStudioPage })));
const RecorderPage = lazy(() => import('../../pages/RecorderPage').then((module) => ({ default: module.RecorderPage })));

type MainWorkspaceStage = Exclude<WorkspaceStage, 'failure'>;
type InspectorTab = 'context' | 'ai' | 'run';

interface WorkspaceLayoutPreference {
  contextOpen: boolean;
  contextWidth: number;
  inspectorWidth: number;
  inspectorTab: InspectorTab;
}

const WORKSPACE_LAYOUT_KEY = 'ai-qa.workspace-layout';
const DEFAULT_WORKSPACE_LAYOUT: WorkspaceLayoutPreference = {
  contextOpen: true,
  contextWidth: 230,
  inspectorWidth: 380,
  inspectorTab: 'context',
};

function readWorkspaceLayout(): WorkspaceLayoutPreference {
  const narrowScreen = window.matchMedia('(max-width: 600px)').matches;
  const defaultContextOpen = narrowScreen ? false : DEFAULT_WORKSPACE_LAYOUT.contextOpen;
  try {
    const stored = window.sessionStorage.getItem(WORKSPACE_LAYOUT_KEY);
    if (!stored) return { ...DEFAULT_WORKSPACE_LAYOUT, contextOpen: defaultContextOpen };
    const value = JSON.parse(stored) as Partial<WorkspaceLayoutPreference>;
    return {
      contextOpen: typeof value.contextOpen === 'boolean' ? value.contextOpen : defaultContextOpen,
      contextWidth: typeof value.contextWidth === 'number' && Number.isFinite(value.contextWidth)
        ? Math.min(340, Math.max(180, value.contextWidth))
        : DEFAULT_WORKSPACE_LAYOUT.contextWidth,
      inspectorWidth: typeof value.inspectorWidth === 'number' && Number.isFinite(value.inspectorWidth)
        ? Math.min(640, Math.max(300, value.inspectorWidth))
        : DEFAULT_WORKSPACE_LAYOUT.inspectorWidth,
      inspectorTab: value.inspectorTab === 'ai' || value.inspectorTab === 'run' ? value.inspectorTab : 'context',
    };
  } catch {
    return { ...DEFAULT_WORKSPACE_LAYOUT, contextOpen: defaultContextOpen };
  }
}

const workspaceStages: { stage: MainWorkspaceStage; view: WorkspaceView }[] = [
  { stage: 'requirement', view: 'requirement' },
  { stage: 'discover', view: 'discover' },
  { stage: 'cases', view: 'cases' },
  { stage: 'automation', view: 'code' },
  { stage: 'result', view: 'results' },
];
const automationViews: WorkspaceView[] = ['code', 'browser', 'debug'];
const stageForView: Record<WorkspaceView, WorkspaceStage> = {
  requirement: 'requirement',
  discover: 'discover',
  cases: 'cases',
  code: 'automation',
  browser: 'automation',
  debug: 'automation',
  results: 'result',
};

export function WorkspacePage() {
  const { t } = useTranslation('workspace');
  const { projectId: routeProjectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { projects, selectedProjectId, selectProject } = useProjectScope();
  useRouteProjectScope(routeProjectId);
  const projectId = routeProjectId ?? searchParams.get('projectId') ?? selectedProjectId ?? '';
  const context = readWorkspaceContext(searchParams, projectId);
  const fallbackStage = context.stage ?? 'requirement';
  const view = context.view ?? (fallbackStage === 'automation' ? 'code' : fallbackStage === 'result' || fallbackStage === 'failure' ? 'results' : fallbackStage);
  const stage = context.stage ?? stageForView[view];
  const runtimeKind = context.taskId ? 'task' : 'run';
  const runtimeId = context.taskId ?? context.runId ?? '';
  const runtime = useRuntimeSnapshot(runtimeKind, runtimeId);
  const taskRunId = runtime.snapshot?.kind === 'task'
    ? [...runtime.snapshot.runs].reverse().find((item) => item.task_id === context.taskId)?.id ?? null
    : null;
  const activeRunId = context.runId ?? taskRunId;
  const runLive = useRunStore(activeRunId);
  const [runConfig, setRunConfig] = useState<WorkspaceRunConfig>({
    environment: 'staging',
    region: 'JP',
    browser: 'chromium',
    workers: 1,
  });
  const [runBusy, setRunBusy] = useState(false);
  const [runError, setRunError] = useState('');
  const [aiRunOpen, setAiRunOpen] = useState(false);
  const [showRunPanel, setShowRunPanel] = useState(false);
  const [runtimePanelKind, setRuntimePanelKind] = useState<'task' | 'run'>('run');
  const [runtimePanelInitialTab, setRuntimePanelInitialTab] = useState<RuntimeTab>('Flow');
  const [showInspector, setShowInspector] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const [workspaceWidth, setWorkspaceWidth] = useState(0);
  const [compactContextOpen, setCompactContextOpen] = useState<boolean | null>(null);
  const [layoutPreference, setLayoutPreference] = useState(() => {
    const preference = readWorkspaceLayout();
    return stage === 'automation' ? { ...preference, contextOpen: false } : preference;
  });
  const { contextOpen: storedContextOpen, contextWidth, inspectorWidth, inspectorTab } = layoutPreference;
  const workspaceGridRef = useRef<HTMLDivElement>(null);
  const previousCompactWorkspace = useRef<boolean | null>(null);
  const panelModeInput = {
    viewportWidth,
    workspaceWidth,
    contextWidth,
    inspectorWidth,
    isStudioView: view === 'code' || view === 'debug',
    isResultView: stage === 'result',
  };
  const isCompactWorkspace = workspacePanelMode({ ...panelModeInput, contextOpen: storedContextOpen }).contextCompact;
  const showWorkspaceContext = isCompactWorkspace ? compactContextOpen ?? false : storedContextOpen;
  const { stackContext: isContextStacked, inspectorModal: isInspectorModal } = workspacePanelMode({
    ...panelModeInput,
    contextOpen: showWorkspaceContext,
  });
  const inspectorMaxWidth = Math.floor(isInspectorModal
    ? Math.min(640, viewportWidth * 0.92, 420)
    : Math.min(640, viewportWidth * 0.32));
  const inspectorMinWidth = Math.min(300, inspectorMaxWidth);
  const visibleInspectorWidth = Math.min(inspectorWidth, inspectorMaxWidth);
  const setShowWorkspaceContext = (update: (open: boolean) => boolean) => {
    if (isCompactWorkspace) {
      setCompactContextOpen((current) => update(current ?? false));
      return;
    }
    setLayoutPreference((current) => ({ ...current, contextOpen: update(current.contextOpen) }));
  };
  const setInspectorTab = (tab: InspectorTab) => setLayoutPreference((current) => ({ ...current, inspectorTab: tab }));
  const inspectorTriggerRef = useRef<HTMLButtonElement>(null);
  const inspectorDrawerRef = useRef<HTMLDivElement>(null);
  const inspectorCloseRef = useRef<HTMLButtonElement>(null);
  const [analysisStarting, setAnalysisStarting] = useState(false);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [cases, setCases] = useState<TestCase[]>([]);
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [failures, setFailures] = useState<FailureRecord[]>([]);
  const [bindingRecord, setBindingRecord] = useState<{
    caseId: string;
    binding: Awaited<ReturnType<typeof api.getAutomationBinding>>;
  } | null>(null);
  const [task, setTask] = useState<AgentTask | null>(null);
  const [loadError, setLoadError] = useState('');
  const [contextDataLoaded, setContextDataLoaded] = useState(false);
  const [contextLoading, setContextLoading] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [goalText, setGoalText] = useState('帮我把这个需求测试完整。可以自动完成低风险步骤；需要修改代码时让我确认。');
  const [goalPreview, setGoalPreview] = useState<AgentGoalPreview | null>(null);
  const [goalPreviewKey, setGoalPreviewKey] = useState('');
  const [goalBusy, setGoalBusy] = useState(false);
  const [goalError, setGoalError] = useState('');
  const goalKey = useRef('');
  const binding = bindingForSelectedCase(bindingRecord, context.testCaseId);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(WORKSPACE_LAYOUT_KEY, JSON.stringify(layoutPreference));
    } catch {
      // A blocked session store should not prevent the workspace from working.
    }
  }, [layoutPreference]);

  useEffect(() => {
    if (stage === 'automation') {
      setLayoutPreference((current) => current.contextOpen ? { ...current, contextOpen: false } : current);
      setCompactContextOpen(null);
    }
  }, [stage]);

  useLayoutEffect(() => {
    if (previousCompactWorkspace.current !== null && previousCompactWorkspace.current !== isCompactWorkspace) {
      setCompactContextOpen(null);
    }
    previousCompactWorkspace.current = isCompactWorkspace;
  }, [isCompactWorkspace]);

  useLayoutEffect(() => {
    const grid = workspaceGridRef.current;
    if (!grid) {
      setWorkspaceWidth(0);
      return;
    }
    const update = () => {
      const nextWidth = Math.round(grid.getBoundingClientRect().width);
      setWorkspaceWidth((current) => current === nextWidth ? current : nextWidth);
    };
    update();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', update);
      return () => window.removeEventListener('resize', update);
    }
    const observer = new ResizeObserver(update);
    observer.observe(grid);
    return () => observer.disconnect();
  }, [projectId]);

  useEffect(() => {
    const update = () => setViewportWidth(window.innerWidth);
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  const resizeContext = (nextWidth: number) => setLayoutPreference((current) => ({
    ...current,
    contextWidth: Math.min(340, Math.max(180, nextWidth)),
  }));
  const resizeInspector = (nextWidth: number) => setLayoutPreference((current) => ({
    ...current,
    inspectorWidth: Math.min(inspectorMaxWidth, Math.max(inspectorMinWidth, nextWidth)),
  }));

  const isAnalysisTask = runtime.snapshot?.task?.type === 'ANALYZE_REQUIREMENT';
  const analysisRunning = analysisStarting || Boolean(
    isAnalysisTask && runtime.snapshot && runtimeActive(runtime.snapshot.status),
  );

  useEffect(() => {
    if (!showInspector) return;
    const drawer = inspectorDrawerRef.current;
    const focusable = () => drawer?.querySelectorAll<HTMLElement>(
      'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    ) ?? [];
    const first = focusable()[0];
    if (isInspectorModal) (inspectorCloseRef.current ?? first)?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowInspector(false);
        return;
      }
      if (!isInspectorModal || event.key !== 'Tab') return;
      const items = focusable();
      if (!items.length) {
        event.preventDefault();
        return;
      }
      const active = document.activeElement;
      if (event.shiftKey && (active === items[0] || !drawer?.contains(active))) {
        event.preventDefault();
        items[items.length - 1].focus();
      } else if (!event.shiftKey && (active === items[items.length - 1] || !drawer?.contains(active))) {
        event.preventDefault();
        items[0].focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      inspectorTriggerRef.current?.focus();
    };
  }, [showInspector, isInspectorModal]);

  useEffect(() => {
    if (searchParams.get('panel') !== 'runtime' || (!context.taskId && !context.runId)) return;
    setRuntimePanelKind(context.taskId ? 'task' : 'run');
    setShowRunPanel(true);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete('panel');
      return next;
    }, { replace: true });
  }, [context.taskId, context.runId, searchParams, setSearchParams]);

  useEffect(() => {
    if (projectId && selectedProjectId !== projectId) selectProject(projectId);
  }, [projectId, selectedProjectId, selectProject]);

  useEffect(() => {
    if (!projectId) {
      setContextLoading(false);
      setContextDataLoaded(false);
      return;
    }
    let active = true;
    setContextDataLoaded(false);
    setContextLoading(true);
    setLoadError('');
    void Promise.all([
      api.getRequirements(projectId),
      api.getTestCases(projectId),
      api.getTestRuns(projectId, 8),
      api.getFailures(projectId, 8),
    ]).then(([nextRequirements, nextCases, nextRuns, nextFailures]) => {
      if (!active) return;
      setRequirements(nextRequirements);
      setCases(nextCases);
      setRuns(nextRuns);
      setFailures(nextFailures);
      setContextDataLoaded(true);
    }).catch((reason: unknown) => {
      if (active) setLoadError(reason instanceof Error ? reason.message : String(reason));
    }).finally(() => {
      if (active) setContextLoading(false);
    });
    return () => { active = false; };
  }, [projectId, loadAttempt]);

  useEffect(() => {
    if (analysisStarting && context.taskId && runtime.snapshot?.id === context.taskId) {
      setAnalysisStarting(false);
    }
  }, [analysisStarting, context.taskId, runtime.snapshot?.id]);

  useEffect(() => {
    const selectedCase = context.testCaseId;
    if (!selectedCase) {
      setBindingRecord(null);
      return;
    }
    let active = true;
    void api.getAutomationBinding(selectedCase).then((value) => {
      if (active) setBindingRecord({ caseId: selectedCase, binding: value });
    }).catch(() => { if (active) setBindingRecord({ caseId: selectedCase, binding: null }); });
    return () => { active = false; };
  }, [context.testCaseId]);

  useEffect(() => {
    if (!context.taskId) {
      setTask(null);
      return;
    }
    let active = true;
    let fetching = false;
    const refresh = async () => {
      if (fetching || !active) return;
      fetching = true;
      try {
        const value = await api.getTask(context.taskId!);
        if (active) setTask(value);
      } catch {
        if (active) setTask(null);
      } finally { fetching = false; }
    };
    void refresh();
    return () => { active = false; };
  }, [context.taskId, runtime.snapshot?.status, runtime.snapshot?.task?.current_step_id]);

  useEffect(() => {
    if (!projectId || !contextDataLoaded) return;
    // Discovery has its own optional requirement selector. Do not silently turn a
    // newly opened Explore workspace into a selected requirement/case context.
    if (view === 'discover' && !context.requirementId && !context.testCaseId) return;
    const selectedCase = cases.find((item) => item.id === context.testCaseId);
    const selectedCaseRequirementId = selectedCase?.requirement_id;
    const requirementId = selectedCaseRequirementId && requirements.some((item) => item.id === selectedCaseRequirementId)
      ? selectedCaseRequirementId
      : requirements.some((item) => item.id === context.requirementId)
        ? context.requirementId
        : requirements[0]?.id;
    const relatedCase = selectedCase
      ? undefined
      : cases.find((item) => item.requirement_id === requirementId);
    const nextCase = selectedCase ?? relatedCase;
    const preserveFailureDebugContext = Boolean(context.failureId && context.view === 'debug');
    if (
      requirementId !== context.requirementId ||
      relatedCase ||
      context.testCaseId !== nextCase?.id ||
      context.testDesignId !== (nextCase?.test_design_id ?? undefined) ||
      context.automationBindingId !== (nextCase?.binding?.id ?? undefined) ||
      context.nodeId !== (nextCase?.binding?.nodeid ?? undefined)
    ) {
      updateContext({
        requirementId,
        testCaseId: nextCase?.id,
        testDesignId: nextCase?.test_design_id ?? undefined,
        automationBindingId: nextCase?.binding?.id,
        file: resolveCanonicalFile(context, nextCase?.binding?.file_path),
        lineNumber: preserveFailureDebugContext ? context.lineNumber : undefined,
        nodeId: preserveFailureDebugContext ? context.nodeId : nextCase?.binding?.nodeid,
        stage: context.stage ?? 'requirement',
      }, true);
    }
    // URL remains the source of truth after the first actual data load.
  }, [projectId, contextDataLoaded, requirements, cases, context.requirementId, context.testCaseId, context.testDesignId, context.automationBindingId, context.nodeId, context.stage, view]);

  function updateContext(patch: Partial<WorkspaceContext>, replace = false) {
    setSearchParams((current) => writeWorkspaceContext(current, {
      ...readWorkspaceContext(current, projectId),
      projectId: projectId || undefined,
      ...patch,
    }), { replace });
  }

  const setView = (next: WorkspaceView) => {
    setSearchParams((current) => {
      const params = writeWorkspaceContext(current, {
        ...readWorkspaceContext(current, projectId),
        projectId: projectId || undefined,
        view: next,
        stage: stageForView[next],
      });
      if (next === 'code' || next === 'debug') params.delete('preset');
      return params;
    });
  };

  const selectedRequirement = requirements.find((item) => item.id === context.requirementId) ?? null;
  const relatedCases = useMemo(
    () => cases.filter((item) => !context.requirementId || item.requirement_id === context.requirementId),
    [cases, context.requirementId],
  );
  const selectedCase = cases.find((item) => item.id === context.testCaseId) ?? null;
  const automationFilePath = binding?.file_path ?? selectedCase?.binding?.file_path ?? null;
  const automationSetup = view === 'code' && stage === 'automation'
    ? selectedCase ? automationFilePath ? null : 'unbound' : context.requirementId ? 'no-case' : null
    : null;
  const automationSetupKey = automationSetup === 'unbound' ? selectedCase?.id
    : automationSetup === 'no-case' ? context.requirementId
      : undefined;
  const goalFailureId = context.failureId ?? (goalText === t('result.manualAnalysisGoal')
    ? failures.find((item) => item.run_id === activeRunId)?.id
    : undefined);
  const goalTarget = workspaceGoalTarget(goalText, { ...context, failureId: goalFailureId });
  const goalInputs: Record<string, unknown> = aiRunOpen && goalTarget === 'case' && selectedCase && binding?.status === 'ACTIVE' && binding.nodeid
    ? {
      test_case_id: selectedCase.id,
      nodeids: [binding.nodeid],
      browser: runConfig.browser,
      region: runConfig.region,
      environment: { QA_ENVIRONMENT: runConfig.environment, QA_REGION: runConfig.region },
      parallel_workers: runConfig.workers,
      file_path: binding.file_path,
    }
    : {
    ...(goalTarget === 'failure' && goalFailureId ? { failure_id: goalFailureId } : {}),
    ...(goalTarget === 'requirement' && context.requirementId ? { requirement_id: context.requirementId } : {}),
    ...(goalTarget === 'case' && context.testCaseId ? { test_case_id: context.testCaseId } : {}),
    ...(goalTarget === 'case' && context.nodeId ? { nodeids: [context.nodeId] } : goalTarget === 'case' && selectedCase?.binding?.nodeid ? { nodeids: [selectedCase.binding.nodeid] } : {}),
    ...(goalTarget !== 'project' && context.runId ? { run_id: context.runId } : {}),
    ...(goalTarget === 'case' || goalTarget === 'failure' ? (context.file ?? binding?.file_path ? { file_path: context.file ?? binding?.file_path } : {}) : {}),
    ...(goalTarget !== 'failure' ? {
      browser: runConfig.browser,
      region: runConfig.region,
      environment: { QA_ENVIRONMENT: runConfig.environment, QA_REGION: runConfig.region },
      parallel_workers: runConfig.workers,
    } : {}),
  };
  const goalRequest = {
    type: 'QA_GOAL' as const,
    goal: goalText,
    project_id: projectId,
    workspace_id: projectId,
    inputs: goalInputs,
  };
  const goalRequestKey = JSON.stringify(goalRequest);
  const goalRequestKeyRef = useRef(goalRequestKey);
  useEffect(() => {
    goalRequestKeyRef.current = goalRequestKey;
  }, [goalRequestKey]);

  useEffect(() => {
    setGoalPreview(null);
    setGoalPreviewKey('');
    setGoalError('');
    goalKey.current = '';
    setGoalText(defaultWorkspaceGoal({
      failureId: context.failureId,
      requirementId: context.requirementId,
      testCaseId: context.testCaseId,
      stage,
      hasAutomation: binding?.status === 'ACTIVE' && Boolean(binding.nodeid),
    }));
  }, [projectId, context.failureId, context.requirementId, context.testCaseId, context.nodeId, context.runId, context.file, binding?.file_path, binding?.nodeid, binding?.status, selectedCase?.binding?.nodeid, stage]);
  const requirementAnalysis = analysisRunning ? null : selectedRequirement?.qa_model?.analysis;
  const latestAnalysisRecord = selectedRequirement?.qa_model?.history.at(-1);
  const currentFailure = stage === 'failure'
    ? context.failureId
      ? failures.find((item) => item.id === context.failureId) ?? null
      : failures.find((item) => item.run_id === activeRunId) ?? null
    : failures.find((item) => item.run_id === activeRunId)
      ?? failures.find((item) => item.id === context.failureId)
      ?? null;
  const currentFailureSource = currentFailure ? failureSourceLocation(currentFailure) : null;
  const failureRun = stage === 'failure' && currentFailure
    ? runs.find((item) => item.id === currentFailure.run_id) ?? null
    : null;
  const currentRun = stage === 'failure'
    ? currentFailure
      ? runLive.run?.id === currentFailure.run_id
        ? runLive.run
        : failureRun
      : null
    : runLive.run ?? runs.find((item) => item.id === activeRunId) ?? null;
  const dockCase = stage === 'failure'
    ? currentFailure?.test_nodeid
      ? cases.find((item) => item.binding?.nodeid === currentFailure.test_nodeid)
        ?? (selectedCase?.binding?.nodeid === currentFailure.test_nodeid ? selectedCase : null)
      : null
    : selectedCase;
  const dockBinding = stage === 'failure'
    ? dockCase?.binding ?? (dockCase && dockCase.id === selectedCase?.id ? binding : null)
    : binding;
  const failureDockName = currentFailure?.test_name
    || currentFailure?.test_nodeid.split('::').at(-1)
    || '';
  const resultRuntime = useRuntimeSnapshot('run', currentRun?.id ?? '');

  useEffect(() => {
    if (stage !== 'failure' || !currentFailure) return;
    if (context.runId !== currentFailure.run_id) {
      updateContext({ runId: currentFailure.run_id, parentRunId: undefined }, true);
    }
    if (failureRun || runLive.run?.id === currentFailure.run_id) return;
    let active = true;
    void api.getTestRun(currentFailure.run_id).then((run) => {
      if (!active) return;
      setRuns((items) => [run, ...items.filter((item) => item.id !== run.id)]);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [stage, currentFailure?.id, currentFailure?.run_id, context.runId, failureRun?.id, runLive.run?.id]);

  useEffect(() => {
    if (!projectId || !currentRun || !['FAILED', 'ERROR'].includes(currentRun.status)) return;
    let active = true;
    void api.getFailures(projectId, 50).then((items) => {
      if (active) setFailures(items);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [projectId, currentRun?.id, currentRun?.status]);

  useEffect(() => {
    if (stage !== 'failure' || context.failureId || !contextDataLoaded || !failures[0]) return;
    updateContext({ failureId: failures[0].id, runId: failures[0].run_id, stage: 'failure', view: 'results' }, true);
  }, [stage, context.failureId, contextDataLoaded, failures]);
  const progressTaskId = context.taskId ?? (runtime.snapshot?.kind === 'task' ? runtime.snapshot.id : task?.id ?? null);
  const runtimePanelId = runtimePanelKind === 'task'
    ? progressTaskId
    : stage === 'failure' ? currentRun?.id : activeRunId;
  const runtimePanelTitle = runtimePanelKind === 'task' ? t('inspector.task') : t('dock.runDetails');
  const runtimePanelHeading = runtimePanelKind === 'task'
    ? task?.id === progressTaskId ? task.goal : progressTaskId
    : currentRun?.requested_by ?? (stage === 'failure' ? currentRun?.id : activeRunId);
  const analysisFailed = !analysisRunning && ['FAILED', 'BLOCKED'].includes(latestAnalysisRecord?.status ?? '');
  const project = projects.find((item: Project) => item.id === projectId);
  const projectDisplayNames = buildProjectDisplayNames(projects);
  const completedGoalResult = stage === 'result'
    && task?.type === 'QA_GOAL'
    && !runtimeActive(runtime.snapshot?.status ?? task.status);
  const resultFailed = Boolean(currentRun && ['FAILED', 'ERROR'].includes(currentRun.status))
    || Boolean(task && ['FAILED', 'BLOCKED'].includes(runtime.snapshot?.status ?? task.status));
  const activeBoundCases = relatedCases.filter((item) => item.binding?.status === 'ACTIVE' && Boolean(item.binding.nodeid)).length;
  const latestAnalysisStatus = selectedRequirement?.qa_model?.history.at(-1)?.status;
  const latestAnalysisStatusLabel = latestAnalysisStatus
    ? t(`journeyFacts.analysisStatus.${latestAnalysisStatus}`, { defaultValue: latestAnalysisStatus })
    : '';
  const taskContext = Boolean(context.taskId || runtime.snapshot?.kind === 'task');
  const taskContextStatus = runtime.snapshot?.kind === 'task' ? runtime.snapshot.status : task?.status;
  const journeyRun = currentRun ?? (!taskContext ? runs[0] : null);
  const activeStage = stage === 'failure' ? 'result' : stage;
  const journeyFacts: Record<MainWorkspaceStage, string> = {
    requirement: !contextDataLoaded
      ? t('journeyFacts.loading')
      : requirements.length === 0
        ? t('journeyFacts.noRequirements')
        : `${t('journeyFacts.requirementCount', { count: requirements.length })}${analysisRunning ? ` · ${t('journeyFacts.analyzing')}` : latestAnalysisStatus ? ` · ${t('journeyFacts.latestAnalysis', { status: latestAnalysisStatusLabel })}` : ''}`,
    discover: t('journeyFacts.discover'),
    cases: !contextDataLoaded
      ? t('journeyFacts.loading')
      : relatedCases.length === 0
        ? t('journeyFacts.noCases')
        : t('journeyFacts.caseCount', { count: relatedCases.length }),
    automation: !contextDataLoaded
      ? t('journeyFacts.loading')
      : relatedCases.length === 0
        ? t('journeyFacts.noCases')
        : t('journeyFacts.bindingCount', { bound: activeBoundCases, total: relatedCases.length }),
    result: taskContext
      ? taskContextStatus
        ? t(`result.workflowStatus.${taskContextStatus}`, { defaultValue: taskContextStatus })
        : t('journeyFacts.noRun')
      : journeyRun
        ? t('journeyFacts.runStatus', { status: journeyRun.status, saved: journeyRun.executions.length, total: journeyRun.total || journeyRun.nodeids.length })
        : t('journeyFacts.noRun'),
  };

  useEffect(() => {
    if (!contextDataLoaded || !['result', 'failure'].includes(stage)) return;
    const selectedRunNodeId = context.nodeId && currentRun?.executions.some((item) => item.nodeid === context.nodeId)
      ? context.nodeId
      : undefined;
    const executedNodeId = selectedRunNodeId
      ?? currentFailure?.test_nodeid
      ?? (currentRun?.nodeids.length === 1 ? currentRun.nodeids[0] : undefined);
    if (!executedNodeId) return;
    const executedCase = cases.find((item) => item.binding?.nodeid === executedNodeId);
    if (!executedCase || (executedCase.id === context.testCaseId && context.nodeId === executedNodeId)) return;
    updateContext({
      requirementId: executedCase.requirement_id ?? context.requirementId,
      testCaseId: executedCase.id,
      testDesignId: executedCase.test_design_id ?? undefined,
      automationBindingId: executedCase.binding?.id,
      file: executedCase.binding?.file_path,
      nodeId: executedNodeId,
    }, true);
  }, [contextDataLoaded, stage, currentFailure?.test_nodeid, currentRun?.id, currentRun?.nodeids, currentRun?.executions, cases, context.nodeId, context.testCaseId, context.requirementId]);

  const openStudio = (filePath?: string, lineNumber?: number) => updateContext({
    testCaseId: selectedCase?.id ?? context.testCaseId,
    automationBindingId: binding?.id ?? context.automationBindingId,
    file: filePath ?? context.file ?? binding?.file_path,
    lineNumber,
    nodeId: binding?.nodeid ?? context.nodeId,
    returnTo: 'workspace',
    stage: 'automation',
    view: 'code',
  });

  const openRecordedCase = (saved: Awaited<ReturnType<typeof api.saveRecorderCase>>, filePath: string) => {
    setCases((current) => [
      ...current.filter((item) => item.id !== saved.test_case.id),
      { ...saved.test_case, binding: saved.binding },
    ]);
    updateContext({
      requirementId: saved.test_case.requirement_id ?? context.requirementId,
      testCaseId: saved.test_case.id,
      automationBindingId: saved.binding.id,
      taskId: undefined,
      runId: undefined,
      parentRunId: undefined,
      failureId: undefined,
      file: filePath,
      lineNumber: undefined,
      nodeId: saved.nodeid,
      stepId: undefined,
      returnTo: 'workspace',
      stage: 'automation',
      view: 'code',
    }, true);
  };

  const selectRequirement = (id: string) => {
    const relatedCase = cases.find((item) => item.requirement_id === id);
    updateContext({
      requirementId: id,
      testCaseId: relatedCase?.id,
      testDesignId: relatedCase?.test_design_id ?? undefined,
      automationBindingId: relatedCase?.binding?.id,
      taskId: undefined,
      failureId: undefined,
      runId: undefined,
      parentRunId: undefined,
      browserSessionId: undefined,
      file: relatedCase?.binding?.file_path,
      lineNumber: undefined,
      nodeId: undefined,
      stepId: undefined,
    });
  };

  const selectCase = (item: TestCase, nextStage: WorkspaceStage = 'cases') => {
    updateContext({
      requirementId: item.requirement_id ?? context.requirementId,
      testCaseId: item.id,
      testDesignId: item.test_design_id ?? undefined,
      automationBindingId: item.binding?.id,
      taskId: undefined,
      runId: undefined,
      parentRunId: undefined,
      failureId: undefined,
      browserSessionId: undefined,
      file: item.binding?.file_path,
      lineNumber: undefined,
      nodeId: item.binding?.nodeid,
      stepId: undefined,
      stage: nextStage,
      view: nextStage === 'automation' ? 'code' : nextStage === 'result' || nextStage === 'failure' ? 'results' : nextStage,
    });
  };

  const onRunStarted = (runId?: string, preserveFailureContext = false) => {
    if (!runId) return;
    updateContext({
      runId,
      taskId: undefined,
      failureId: preserveFailureContext ? context.failureId : undefined,
      parentRunId: preserveFailureContext ? currentRun?.id ?? context.parentRunId : undefined,
    });
    setRuntimePanelKind('run');
    setShowRunPanel(true);
    void api.getTestCases(projectId).then(setCases).catch(() => undefined);
    setAiRunOpen(false);
    setRunError('');
  };

  const onTaskStarted = (taskId: string, preserveFailureContext = false) => {
    updateContext({
      taskId,
      runId: undefined,
      parentRunId: preserveFailureContext ? context.parentRunId : undefined,
      failureId: preserveFailureContext ? context.failureId : undefined,
    });
    setRuntimePanelKind('task');
    setShowRunPanel(true);
  };

  const runSelectedCase = async (rerun = false) => {
    const runBinding = stage === 'failure' ? dockBinding : binding;
    const activeNodeId = runBinding?.status === 'ACTIVE' ? runBinding.nodeid : undefined;
    const nodeId = activeNodeId ?? (rerun
      ? stage === 'failure' ? currentFailure?.test_nodeid : currentRun?.nodeids[0]
      : undefined);
    if (!projectId || !nodeId || (!selectedCase && !rerun) || runBusy) return;
    setRunBusy(true);
    setRunError('');
    try {
      const selectedRunConfig = rerun && currentRun ? configForRerun(currentRun, runConfig) : runConfig;
      const run = await api.createTestRun({
        project_id: projectId,
        workspace_id: projectId,
        nodeids: [nodeId],
        requested_by: `Workspace · ${selectedCase?.title ?? nodeId}`,
        browser: selectedRunConfig.browser,
        environment: {
          QA_ENVIRONMENT: selectedRunConfig.environment,
          QA_REGION: selectedRunConfig.region,
        },
        parallel_workers: selectedRunConfig.workers,
        ...(rerun && currentRun ? { parent_run_id: currentRun.id } : {}),
        ...(rerun && (currentFailure?.id ?? context.failureId) ? { origin_failure_id: currentFailure?.id ?? context.failureId } : {}),
      });
      setRuns((items) => [run, ...items.filter((item) => item.id !== run.id)]);
      onRunStarted(run.id, rerun);
    } catch (reason) {
      setRunError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunBusy(false);
    }
  };

  const stopActiveRun = async () => {
    try {
      const taskId = context.taskId;
      if (taskId && runtimeActive(runtime.snapshot?.status ?? '')) {
        await api.cancelTask(taskId);
        await runtime.refresh();
      } else if (activeRunId) {
        const updated = await api.cancelTestRun(activeRunId);
        setRuns((items) => items.map((item) => item.id === updated.id ? updated : item));
        await runLive.refresh();
      }
    } catch (reason) {
      setRunError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const diagnoseCurrentRun = async () => {
    let failureId = currentFailure?.id ?? context.failureId;
    if (!failureId && activeRunId) {
      try {
        const latestFailures = await api.getFailures(projectId, 50);
        setFailures(latestFailures);
        failureId = latestFailures.find((item) => item.run_id === activeRunId)?.id;
      } catch {
        // The failure view can still show the project's recent records if this refresh fails.
      }
    }
    updateContext({ failureId, stage: 'failure', view: 'results' });
  };

  const openRunDetails = (extra: Partial<WorkspaceContext> = {}, initialTab?: RuntimeTab) => {
    const taskId = extra.taskId ?? (!extra.runId ? progressTaskId : undefined);
    const runId = extra.runId ?? activeRunId;
    if (taskId) {
      setRuntimePanelKind('task');
      if (extra.taskId && extra.taskId !== context.taskId) {
        updateContext({ taskId: extra.taskId, runId: undefined });
      }
    } else if (runId) {
      setRuntimePanelKind('run');
      if (extra.runId && extra.runId !== context.runId) {
        updateContext({ runId: extra.runId, taskId: undefined });
      }
    }
    if (taskId || runId) {
      setRuntimePanelInitialTab(initialTab ?? (!taskId && context.view === 'code' ? 'Browser' : 'Flow'));
      setShowRunPanel(true);
    }
  };

  const startRequirementAnalysis = async (requirement: Requirement) => {
    if (!projectId) return;
    setAnalysisStarting(true);
    try {
      const created = await api.createTask({
        type: 'ANALYZE_REQUIREMENT',
        project_id: projectId,
        goal: `Analyze requirement: ${requirement.title}`,
        inputs: { requirement_id: requirement.id },
      });
      onTaskStarted(created.id);
    } catch (reason) {
      setAnalysisStarting(false);
      throw reason;
    }
  };

  const handleRequirementChanged = useCallback((requirement: Requirement) => {
    setRequirements((items) => items.some((item) => item.id === requirement.id)
      ? items.map((item) => item.id === requirement.id ? requirement : item)
      : [...items, requirement]);
  }, []);

  const handleBindingChanged = (testCaseId: string, nextBinding: AutomationBinding | null) => {
    const automationStatus = nextBinding?.status === 'ACTIVE' ? 'AUTOMATED' : nextBinding ? 'DRAFT' : 'MANUAL';
    setCases((items) => items.map((item) => item.id === testCaseId
      ? { ...item, binding: nextBinding, automation_status: automationStatus }
      : item));
    setBindingRecord({ caseId: testCaseId, binding: nextBinding });
    if (context.testCaseId === testCaseId) {
      updateContext({
        automationBindingId: nextBinding?.id,
        nodeId: nextBinding?.nodeid,
        file: nextBinding?.file_path,
      });
    }
  };

  const editGoal = (value: string) => {
    setGoalText(value);
    setGoalPreview(null);
    setGoalPreviewKey('');
    setGoalError('');
    goalKey.current = '';
  };
  const previewGoal = async () => {
    if (!projectId || !goalText.trim() || goalBusy) return;
    setGoalBusy(true);
    setGoalError('');
    const requestKey = goalRequestKey;
    try {
      const preview = await api.previewTaskGoal(goalRequest);
      if (goalRequestKeyRef.current === requestKey) {
        setGoalPreview(preview);
        setGoalPreviewKey(requestKey);
      }
    } catch (reason) {
      setGoalError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setGoalBusy(false);
    }
  };
  const startGoal = async () => {
    if (!projectId || !goalPreview || goalPreviewKey !== goalRequestKey || goalPreview.goal !== goalText || goalBusy) return;
    setGoalBusy(true);
    setGoalError('');
    try {
      const storageKey = `ai-qa.goal-start:${goalPreview.plan_token}`;
      goalKey.current ||= window.sessionStorage.getItem(storageKey)
        ?? window.crypto?.randomUUID?.()
        ?? `qa-goal-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      window.sessionStorage.setItem(storageKey, goalKey.current);
      const created = await api.createTask({ ...goalRequest, plan_token: goalPreview.plan_token, idempotency_key: goalKey.current });
      window.sessionStorage.removeItem(storageKey);
      goalKey.current = '';
      setGoalPreview(null);
      setGoalPreviewKey('');
      setTask(created);
      setAiRunOpen(false);
      onTaskStarted(created.id, Boolean(context.failureId || context.runId || context.parentRunId));
    } catch (reason) {
      setGoalError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setGoalBusy(false);
    }
  };
  const workspaceHeading = !projectId
    ? t('title')
    : view === 'results'
      ? t('result.analysisTitle')
      : t(`pageHeadings.${view}`);
  const workspaceEyebrow = projectId
    ? `${t('projectWorkspace')} · ${projectDisplayNames.get(projectId) ?? project?.name ?? projectId}`
    : t('projectWorkspace');

  return (
    <div className={`workspace-shell${stage === 'result' ? ' is-result-stage' : ''}`}>
      <header className="workspace-heading">
        <div>
          <span className="workspace-eyebrow">{workspaceEyebrow}</span>
          <h1 title={workspaceHeading}>{workspaceHeading}</h1>
          <p>{t('subtitle')}</p>
        </div>
        <div className="workspace-heading-actions">
          {selectedRequirement && <span className="workspace-context-chip"><GitBranch size={14} aria-hidden="true" />{selectedRequirement.qa_model?.display_id ?? selectedRequirement.title}</span>}
          {projectId && stage !== 'result' && <button type="button" className="btn btn-secondary btn-sm workspace-context-toggle" aria-label={t(showWorkspaceContext ? 'context.hidePanel' : 'context.showPanel')} aria-expanded={showWorkspaceContext} aria-controls="workspace-context-panel" onClick={() => setShowWorkspaceContext((visible) => !visible)} title={t(showWorkspaceContext ? 'context.hidePanel' : 'context.showPanel')}>
            {showWorkspaceContext ? <PanelLeftClose size={14} aria-hidden="true" /> : <PanelLeftOpen size={14} aria-hidden="true" />}
            <span>{t(showWorkspaceContext ? 'context.hidePanel' : 'context.showPanel')}</span>
          </button>}
          {projectId && <button ref={inspectorTriggerRef} type="button" className="btn btn-secondary btn-sm" aria-expanded={showInspector} aria-controls="workspace-inspector-drawer" onClick={() => setShowInspector(true)}><PanelRightOpen size={14} aria-hidden="true" />{t('inspector.title')}</button>}
          {projectId && view !== 'discover' && (!currentRun || stage !== 'result') && <WorkspaceRunDock
            caseLabel={workspaceRunCaseLabel(dockCase?.test_model?.display_id, dockCase?.id, stage === 'failure' ? failureDockName : undefined)}
            caseTitle={dockCase?.title ?? (stage === 'failure' ? failureDockName : '')}
            hasAutomation={dockBinding?.status === 'ACTIVE' && Boolean(dockBinding.nodeid)}
            aiRunLabel={goalTarget === 'requirement' ? t('dock.aiRunRequirement') : dockCase && !dockBinding ? t('dock.aiGenerateAutomation') : undefined}
            run={currentRun}
            taskStatus={runtime.snapshot?.kind === 'task' ? runtime.snapshot.status : task?.status ?? null}
            taskStep={runtime.snapshot?.steps.find((item) => item.status === 'RUNNING')?.title ?? null}
            busy={runBusy}
            error={runError}
            config={runConfig}
            onConfigChange={setRunConfig}
            onRun={() => void runSelectedCase()}
            onAiRun={() => {
              editGoal(defaultWorkspaceGoal({
                failureId: context.failureId,
                requirementId: context.requirementId,
                testCaseId: dockCase?.id,
                stage,
                hasAutomation: dockBinding?.status === 'ACTIVE' && Boolean(dockBinding.nodeid),
              }));
              setAiRunOpen(true);
            }}
            onStop={() => void stopActiveRun()}
            onOpen={openRunDetails}
            onViewResult={() => { setShowRunPanel(false); setView('results'); }}
            onViewFailure={() => void diagnoseCurrentRun()}
            onDebug={() => updateContext({ file: currentFailureSource?.filePath ?? dockCase?.binding?.file_path ?? context.file, lineNumber: currentFailureSource?.lineNumber ?? context.lineNumber, nodeId: currentFailure?.test_nodeid ?? dockCase?.binding?.nodeid, failureId: currentFailure?.id ?? context.failureId, stage: 'automation', view: 'debug' })}
            onRerun={() => void runSelectedCase(true)}
            onOpenCode={() => setView('code')}
          />}
          {completedGoalResult && <button type="button" className="btn btn-secondary btn-sm" onClick={() => updateContext({ taskId: undefined, runId: undefined, stage: 'requirement', view: 'requirement' })}>{t('goal.new')}</button>}
          {(context.taskId || context.runId) && <button type="button" className="btn btn-secondary btn-sm" onClick={() => openRunDetails()}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button>}
        </div>
      </header>

      {projectId && <nav className="workspace-stage-nav" aria-label={t('stages')}>
        {workspaceStages.map((item, index) => <button
          key={item.stage}
          type="button"
          aria-current={activeStage === item.stage ? 'step' : undefined}
          aria-label={`${t(`journey.${item.stage}`)} · ${journeyFacts[item.stage]}`}
          title={journeyFacts[item.stage]}
          className={`workspace-view-tab${activeStage === item.stage ? ' is-current' : ''}${item.stage === 'result' && resultFailed ? ' has-failure' : ''}`}
          onClick={() => {
            if (item.stage === 'result' && !activeRunId && runs[0]) {
              updateContext({ runId: runs[0].id, stage: 'result', view: 'results' });
            } else {
              setView(item.view);
            }
          }}
        >
          <span className="workspace-flow-number" aria-hidden="true">{index + 1}</span>
          <span className="workspace-flow-label">
            <strong>{t(`journey.${item.stage}`)}</strong>
            <small>{journeyFacts[item.stage]}</small>
          </span>
          {item.stage === 'result' && journeyRun && <span className={`workspace-tab-status is-${journeyRun.status.toLowerCase()}`} aria-hidden="true" />}
        </button>)}
      </nav>}

      {loadError && <div className="workspace-error" role="alert"><span>{loadError}</span><button type="button" className="btn btn-secondary btn-sm" onClick={() => setLoadAttempt((value) => value + 1)}>{t('retry')}</button></div>}
      {!projectId ? (
        <section className="workspace-empty">
          <h2>{t('noProjectTitle')}</h2>
          <p>{t('noProjectDescription')}</p>
          <Link className="btn btn-primary" to="/projects">{t('openProjects')}</Link>
        </section>
      ) : (
        <>
        <div ref={workspaceGridRef} style={{ '--workspace-context-width': `${contextWidth}px`, '--workspace-inspector-width': `${visibleInspectorWidth}px` } as CSSProperties} className={`workspace-grid${stage === 'failure' ? ' is-failure-stage' : ''}${stage === 'result' ? ' is-result-view' : ''}${view === 'debug' ? ' is-debug-view' : ''}${showWorkspaceContext ? '' : ' is-context-collapsed'}${isContextStacked ? ' is-context-stacked' : ''}${showInspector ? ' has-inspector' : ''}${isInspectorModal ? ' is-inspector-modal' : ''}`}>
          <aside id="workspace-context-panel" className="workspace-context-panel" aria-label={t('context.title')}>
            <div className="workspace-panel-heading"><h2>{t('context.title')}</h2><small>{projectDisplayNames.get(projectId) ?? project?.name ?? projectId}</small></div>
            {['requirement', 'discover'].includes(stage) && <section className="workspace-context-group">
              <div className="workspace-group-heading"><h3>{t('context.requirements')}</h3></div>
              {!contextDataLoaded
                ? <div className="workspace-context-list"><p className="workspace-muted">{contextLoading ? t('context.loading') : t('context.unavailable')}</p></div>
                : <WorkspaceContextList
                  items={requirements}
                  limit={12}
                  filterText={(item) => `${item.qa_model?.display_id ?? ''} ${item.title}`}
                  renderItem={(item) => <button key={item.id} type="button" className={item.id === context.requirementId ? 'is-selected' : ''} aria-pressed={item.id === context.requirementId} onClick={() => selectRequirement(item.id)}>
                    <span>{item.qa_model?.display_id ?? item.id.slice(-6)}</span><strong>{item.title}</strong>
                  </button>}
                  emptyState={<><p className="workspace-muted">{t('context.noRequirements')}</p>{projects.length > 1 && <Link className="btn btn-secondary btn-sm" to="/projects">{t('context.chooseProject')}</Link>}</>}
                />}
            </section>}
            {['cases', 'automation'].includes(stage) && <section className="workspace-context-group">
              <div className="workspace-group-heading"><h3>{t('context.cases')}</h3></div>
              {!contextDataLoaded
                ? <div className="workspace-context-list"><p className="workspace-muted">{contextLoading ? t('context.loading') : t('context.unavailable')}</p></div>
                : <WorkspaceContextList
                  items={relatedCases}
                  limit={10}
                  filterText={(item) => `${item.test_model?.display_id ?? ''} ${item.title}`}
                  renderItem={(item) => <button key={item.id} type="button" className={item.id === context.testCaseId ? 'is-selected' : ''} aria-pressed={item.id === context.testCaseId} onClick={() => selectCase(item)}>
                    <span>{item.test_model?.display_id ?? item.id.slice(-6)}</span><strong>{item.title}</strong><small>{item.automation_status}</small>
                  </button>}
                  emptyState={<p className="workspace-muted">{t('context.noCases')}</p>}
                />}
            </section>}
            {stage === 'failure' && <section className="workspace-context-group workspace-failure-queue" aria-label={t('context.failures')}>
              <div className="workspace-group-heading"><h3>{t('context.failures')}</h3><span>{failures.length}</span></div>
              {!contextDataLoaded
                ? <div className="workspace-context-list"><p className="workspace-muted">{contextLoading ? t('context.loading') : t('context.unavailable')}</p></div>
                : <WorkspaceContextList
                  items={failures}
                  limit={5}
                  filterText={(item) => `${item.test_name ?? ''} ${item.test_nodeid} ${item.classification}`}
                  renderItem={(item) => <Link
                    key={item.id}
                    to={buildWorkspaceHref({ projectId, runId: item.run_id, failureId: item.id, stage: 'failure', view: 'results' })}
                    aria-current={item.id === context.failureId ? 'page' : undefined}
                    className={item.id === context.failureId ? 'is-selected' : ''}
                    title={item.error_message}
                  >
                    <strong>{item.test_name || item.test_nodeid.split('::').at(-1) || item.test_nodeid}</strong>
                    <small>{item.classification}</small>
                  </Link>}
                  emptyState={<p className="workspace-muted">{t('context.noFailures')}</p>}
                />}
            </section>}
            {stage === 'automation' && binding && <section className="workspace-context-group workspace-binding-card">
              <div className="workspace-group-heading"><h3>{t('context.automation')}</h3><span className={`workspace-binding-status is-${binding.status.toLowerCase()}`}>{binding.status}</span></div>
              <button type="button" onClick={() => openStudio(binding.file_path)}><FileCode2 size={14} aria-hidden="true" /><span>{binding.file_path}</span></button>
            </section>}
          </aside>
          {showWorkspaceContext && stage !== 'result' && <div
            className="workspace-context-resizer"
            role="separator"
            tabIndex={0}
            aria-orientation="vertical"
            aria-label={t('context.resizePanel')}
            aria-valuemin={180}
            aria-valuemax={340}
            aria-valuenow={contextWidth}
            onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)}
            onPointerMove={(event) => {
              if (event.buttons !== 1 || !workspaceGridRef.current) return;
              resizeContext(event.clientX - workspaceGridRef.current.getBoundingClientRect().left);
            }}
            onKeyDown={(event) => {
              if (event.key === 'ArrowLeft') { event.preventDefault(); resizeContext(contextWidth - 16); }
              if (event.key === 'ArrowRight') { event.preventDefault(); resizeContext(contextWidth + 16); }
            }}
          />}

          <section className={`workspace-main-panel is-${view}-panel`} aria-label={t('main.title')}>
            <div className="workspace-main-heading">
              <div><span className="workspace-eyebrow">{t('main.currentStage')}</span><h2>{t(`tabs.${view}`)}</h2></div>
              {stage === 'automation' && <nav className="workspace-tool-nav" role="tablist" aria-label={t('automationViews.label')}>
                {automationViews.map((item) => <button key={item} type="button" role="tab" aria-selected={view === item} className={`workspace-view-tab${view === item ? ' is-current' : ''}`} onClick={() => setView(item)}>{t(`automationViews.${item}`)}</button>)}
              </nav>}
            </div>
            <div className="workspace-main-scroll">
              {aiRunOpen && <section className="workspace-ai-run-panel" aria-label={t('aiRun.title')}>
                <div className="workspace-ai-run-heading">
                  <div><Sparkles size={16} aria-hidden="true" /><div><strong>{t('aiRun.title')}</strong><small>{goalTarget === 'requirement' ? selectedRequirement?.title ?? t('dock.chooseRequirement') : selectedCase?.test_model?.display_id ?? selectedCase?.title ?? t('dock.chooseCase')}</small></div></div>
                  <button type="button" className="btn btn-icon btn-sm" aria-label={t('aiRun.close')} onClick={() => setAiRunOpen(false)}><X size={14} /></button>
                </div>
                <p>{t('aiRun.description')}</p>
                <ul className="workspace-ai-capabilities">
                  <li>{t('aiRun.capabilities.context')}</li>
                  <li>{t('aiRun.capabilities.plan')}</li>
                  <li>{t('aiRun.capabilities.execute')}</li>
                  <li>{t('aiRun.capabilities.diagnose')}</li>
                </ul>
                {goalPreview && goalPreviewKey === goalRequestKey ? <div className="workspace-goal-preview">
                  <div className="workspace-goal-preview-heading"><strong>{t('goal.planTitle')}</strong><span>{goalPreview.context}</span></div>
                  <ol>{goalPreview.steps.map((step, index) => <li key={`${step.title}-${index}`}>
                    <span>{index + 1}</span><strong>{step.title}</strong>
                    {step.conditional && <small>{t('goal.conditional')}</small>}
                    <em className={`is-${step.risk.toLowerCase()}`}>{t(`goal.risk.${step.risk.toLowerCase()}`)}</em>
                  </li>)}</ol>
                  {goalPreview.effects.length > 0 && <p><b>{t('goal.effects')}</b> {goalPreview.effects.join(' · ')}</p>}
                  {goalPreview.constraints.length > 0 && <p><b>{t('goal.constraints')}</b> {goalPreview.constraints.join(' · ')}</p>}
                  <button type="button" className="btn btn-primary btn-sm" disabled={goalBusy} onClick={() => void startGoal()}>
                    {goalBusy ? t('goal.starting') : t('goal.start')} <ArrowRight size={14} aria-hidden="true" />
                  </button>
                </div> : <button type="button" className="btn btn-secondary btn-sm" disabled={!contextDataLoaded || goalBusy} onClick={() => void previewGoal()}>
                  {goalBusy ? t('goal.planning') : t('aiRun.reviewPlan')} <ArrowRight size={14} aria-hidden="true" />
                </button>}
                {goalError && <p className="workspace-goal-error" role="alert">{goalError}</p>}
                <small className="workspace-ai-run-note">{t('aiRun.sharedExecutor')}</small>
              </section>}

              {view === 'requirement' && <RequirementsPage
                projects={projects}
                selectedProjectId={projectId}
                initialRequirementId={context.requirementId}
                onSelectRequirement={selectRequirement}
                onStartAnalysis={startRequirementAnalysis}
                analysisRunning={analysisRunning}
                analysisRefreshVersion={isAnalysisTask ? runtime.snapshot?.event_cursor : null}
                onRequirementChanged={handleRequirementChanged}
                onCaseCreated={(id, testDesignId) => {
                  updateContext({ testCaseId: id, testDesignId, automationBindingId: undefined, taskId: undefined, runId: undefined, parentRunId: undefined, failureId: undefined, browserSessionId: undefined, file: undefined, lineNumber: undefined, nodeId: undefined, stepId: undefined, stage: 'cases', view: 'cases' });
                  void api.getTestCases(projectId).then(setCases).catch(() => undefined);
                }}
                workspaceMode
              />}
              {view === 'discover' && <QualityDiscoveryPanel
                projectId={projectId}
                initialRequirementId={context.requirementId}
                onOpenRequirement={(requirementId) => updateContext({ requirementId, testCaseId: undefined, runId: undefined, stage: 'requirement', view: 'requirement' })}
                onOpenCase={async (testCaseId, requirementId) => {
                  const nextCases = await api.getTestCases(projectId);
                  if (!nextCases.some((item) => item.id === testCaseId)) return;
                  setCases(nextCases);
                  updateContext({ testCaseId, requirementId: requirementId?.split(':REQ-')[0], stage: 'cases', view: 'cases' });
                }}
                onOpenAutomation={(testCaseId, filePath) => updateContext({ testCaseId, file: filePath, nodeId: undefined, stage: 'automation', view: 'code', returnTo: 'workspace' })}
                onOpenRun={(runId, testCaseId) => updateContext({ runId, testCaseId, taskId: undefined, failureId: undefined, stage: 'result', view: 'results' })}
                onOpenTask={(taskId) => openRunDetails({ taskId })}
              />}
              {view === 'cases' && <TestCasesPage
                projects={projects}
                selectedProjectId={projectId}
                initialRequirementId={context.requirementId}
                initialTestCaseId={context.testCaseId}
                onSelectTestCase={selectCase}
                onCaseCreated={(createdCase) => {
                  setCases((items) => [...items.filter((item) => item.id !== createdCase.id), createdCase]);
                  updateContext({ requirementId: createdCase.requirement_id ?? context.requirementId, testCaseId: createdCase.id, view: 'cases', stage: 'cases' });
                }}
                onAutomationBindingChanged={handleBindingChanged}
                onNavigateToStudio={(filePath) => openStudio(filePath)}
                onNavigateToRuns={onRunStarted}
                onTaskStarted={onTaskStarted}
                workspaceMode
                hideRunAction
              />}
              {(view === 'code' || view === 'debug' || view === 'browser') && <div hidden={view === 'browser'}><Suspense fallback={<div className="workspace-surface-loading" role="status">{t('main.loadingEditor')}</div>}><AutomationStudioPage
                key={projectId}
                projects={projects}
                selectedProjectId={projectId}
                onSelectProject={selectProject}
                onNavigateToRuns={onRunStarted}
                onRunCreated={onRunStarted}
                runConfig={runConfig}
                workspaceView={view === 'debug' ? 'debug' : 'code'}
                initialOpenFilePath={automationSetup ? null : context.file ?? automationFilePath}
                workspaceAutomationSetup={automationSetup}
                workspaceAutomationSetupKey={automationSetupKey}
                onStartRecording={() => setView('browser')}
                onSelectCases={() => setView('cases')}
                initialOpenLineNumber={context.lineNumber ?? null}
                initialDebugNodeId={view === 'debug' && context.failureId ? context.nodeId ?? null : null}
                initialDebugFailureId={view === 'debug' ? context.failureId ?? null : null}
                embedded
              /></Suspense></div>}
              {view === 'browser' && <Suspense fallback={<div className="workspace-surface-loading" role="status">{t('main.loadingBrowser')}</div>}><RecorderPage
                projects={projects}
                selectedProjectId={projectId}
                embedded
                runConfig={runConfig}
                onNavigateToRuns={onRunStarted}
                onOpenRecordedCase={openRecordedCase}
              /></Suspense>}
              {view === 'results' && stage !== 'failure' && <RunResultSurface
                context={context}
                run={currentRun}
                testCases={cases}
                task={task}
                runtime={currentRun ? resultRuntime.snapshot : runtime.snapshot}
                runtimeConnection={currentRun ? resultRuntime.connection : runtime.connection}
                runtimeError={currentRun ? resultRuntime.error : runtime.error}
                onRefreshRuntime={() => void (currentRun ? resultRuntime : runtime).refresh()}
                projectId={projectId}
                onOpenCode={(filePath, lineNumber) => openStudio(filePath, lineNumber)}
                onOpenDetails={() => openRunDetails({}, 'Results')}
                onOpenStep={(stepId) => {
                  setSearchParams((current) => { const next = new URLSearchParams(current); next.set('step', stepId); return next; }, { replace: true });
                  openRunDetails({}, 'Flow');
                }}
                onStop={() => void stopActiveRun()}
                onRerun={() => void runSelectedCase(Boolean(currentRun))}
                canStartRun={Boolean(selectedCase && binding?.status === 'ACTIVE' && binding.nodeid)}
                onManualAnalysis={() => { editGoal(t('result.manualAnalysisGoal')); setAiRunOpen(true); }}
                onSelectExecution={(nodeId, caseId) => {
                  const selected = cases.find((item) => item.id === caseId);
                  updateContext({
                    nodeId,
                    testCaseId: selected?.id,
                    testDesignId: selected?.test_design_id ?? undefined,
                    automationBindingId: selected?.binding?.id,
                    file: selected?.binding?.file_path ?? nodeId.split('::')[0],
                    lineNumber: undefined,
                  });
                }}
              />}
              {view === 'results' && stage === 'failure' && <FailuresPage
                projects={projects}
                selectedProjectId={projectId}
                initialFailureId={context.failureId}
                onOpenInStudio={(filePath, lineNumber, nodeId, failureContext) => updateContext({
                  file: filePath,
                  lineNumber,
                  nodeId,
                  failureId: failureContext?.failureId ?? context.failureId,
                  runId: failureContext?.runId ?? context.runId,
                  parentRunId: failureContext?.runId ?? context.parentRunId,
                  stage: 'automation',
                  view: 'debug',
                })}
                onNavigateToRuns={(runId) => updateContext({ runId, parentRunId: currentFailure?.run_id, stage: 'failure', view: 'results' })}
                onTaskStarted={onTaskStarted}
              />}
            </div>
          </section>

        <div className={`workspace-inspector-overlay${isInspectorModal ? ' is-modal' : ''}`} hidden={!showInspector} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowInspector(false); }}>
          <div id="workspace-inspector-drawer" ref={inspectorDrawerRef} className="workspace-inspector workspace-inspector-drawer" role={isInspectorModal ? 'dialog' : 'region'} aria-modal={isInspectorModal ? true : undefined} aria-label={t('inspector.title')}>
            <div
              className="workspace-inspector-resizer"
              role="separator"
              tabIndex={0}
              aria-orientation="vertical"
              aria-label={t('inspector.resizePanel')}
              aria-valuemin={inspectorMinWidth}
              aria-valuemax={inspectorMaxWidth}
              aria-valuenow={visibleInspectorWidth}
              onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)}
              onPointerMove={(event) => {
                if (event.buttons !== 1) return;
                const gridRight = isInspectorModal ? viewportWidth : workspaceGridRef.current?.getBoundingClientRect().right ?? viewportWidth;
                resizeInspector(gridRight - event.clientX);
              }}
              onKeyDown={(event) => {
                if (event.key === 'ArrowLeft') { event.preventDefault(); resizeInspector(visibleInspectorWidth + 16); }
                if (event.key === 'ArrowRight') { event.preventDefault(); resizeInspector(visibleInspectorWidth - 16); }
              }}
            />
            <div className="workspace-panel-heading"><div><h2>{t('inspector.title')}</h2><span className="workspace-live-label"><i aria-hidden="true" />{t('inspector.liveContext')}</span></div><button ref={inspectorCloseRef} type="button" className="btn btn-icon btn-sm" aria-label={t('inspector.close')} onClick={() => setShowInspector(false)}><X size={15} /></button></div>
            <div className="workspace-inspector-tabs" role="tablist" aria-label={t('inspector.title')}>
              {(['context', 'ai', 'run'] as const).map((item, index, items) => <button
              key={item}
              type="button"
              role="tab"
              id={`workspace-inspector-tab-${item}`}
              aria-controls="workspace-inspector-tabpanel"
              aria-selected={inspectorTab === item}
                tabIndex={inspectorTab === item ? 0 : -1}
                className={inspectorTab === item ? 'is-selected' : ''}
                onClick={() => setInspectorTab(item)}
                onKeyDown={(event) => {
                  const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
                  const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + offset + items.length) % items.length;
                  if (!offset && event.key !== 'Home' && event.key !== 'End') return;
                  event.preventDefault();
                  const next = items[nextIndex];
                  setInspectorTab(next);
                  event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex]?.focus();
                }}
              >{t(`inspector.tabs.${item}`)}</button>)}
            </div>
            {inspectorTab === 'context' && <div className="workspace-inspector-content" role="tabpanel" id="workspace-inspector-tabpanel" aria-labelledby={`workspace-inspector-tab-${inspectorTab}`} tabIndex={0}>
              {selectedRequirement ? <section className="workspace-inspector-section">
                <span>{t('inspector.requirement')}</span><strong>{selectedRequirement.qa_model?.display_id ?? selectedRequirement.title}</strong>
                <p>{requirementAnalysis?.summary ?? (analysisFailed ? t('inspector.analysisFailed') : t('inspector.pending'))}</p>
                {requirementAnalysis?.risks.slice(0, 2).map((risk) => <div className="workspace-risk" key={risk.id}><b>{risk.severity}</b><span>{risk.title}</span></div>)}
              </section> : <p className="workspace-muted">{t('inspector.chooseRequirement')}</p>}
              {selectedCase && <section className="workspace-inspector-section">
                <span>{t('inspector.case')}</span><strong>{selectedCase.test_model?.display_id ?? selectedCase.title}</strong>
                <p>{selectedCase.expected_result || t('inspector.noExpectedResult')}</p>
                <div className="workspace-inspector-fact"><span>{t('inspector.automation')}</span><strong>{binding?.status ?? t('inspector.unbound')}</strong></div>
                {binding && <button type="button" className="btn btn-secondary btn-sm" onClick={() => openStudio(binding.file_path)}><FileCode2 size={13} aria-hidden="true" />{t('inspector.openStudio')}</button>}
              </section>}
              <section className="workspace-inspector-section">
                <span>{t('inspector.runConfig')}</span>
                <div className="workspace-inspector-fact"><span>{t('dock.environment')}</span><strong>{runConfig.environment}</strong></div>
                <div className="workspace-inspector-fact"><span>{t('dock.region')}</span><strong>{runConfig.region}</strong></div>
                <div className="workspace-inspector-fact"><span>{t('dock.browser')}</span><strong>{runConfig.browser}</strong></div>
              </section>
              {!selectedCase && <p className="workspace-inspector-hint">{t('inspector.nextActionHint')}</p>}
            </div>}
            {inspectorTab === 'ai' && <div className="workspace-inspector-content" role="tabpanel" id="workspace-inspector-tabpanel" aria-labelledby={`workspace-inspector-tab-${inspectorTab}`} tabIndex={0}>
              {task ? <section className="workspace-inspector-section">
                <span>{t('inspector.task')}</span><strong>{runtime.snapshot?.id === task.id ? runtime.snapshot.status : task.status}</strong><p>{task.goal}</p>
                {(runtime.snapshot?.steps ?? task.steps ?? task.plan).slice(0, 5).map((step) => <div className="workspace-inspector-fact" key={step.id}><span>{step.status}</span><strong>{'title' in step ? step.title : step.name}</strong></div>)}
                {!!runtime.snapshot?.decisions.length && <details className="workspace-decision-trace"><summary>{t('inspector.decisionTrace')}</summary>{runtime.snapshot.decisions.map((decision) => <p key={decision.id}><strong>{decision.selected}</strong> · {decision.name}</p>)}</details>}
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => openRunDetails({ taskId: task.id })}><Workflow size={13} aria-hidden="true" />{t('inspector.advancedTrace')}</button>
              </section> : <p className="workspace-muted">{t('inspector.aiIdle')}</p>}
              {goalError && <p className="workspace-goal-error" role="alert">{goalError}</p>}
            </div>}
            {inspectorTab === 'run' && <div className="workspace-inspector-content" role="tabpanel" id="workspace-inspector-tabpanel" aria-labelledby={`workspace-inspector-tab-${inspectorTab}`} tabIndex={0}>
              {currentRun ? <section className="workspace-inspector-section">
                <span>{t('inspector.run')}</span><strong>{currentRun.status}</strong>
                <p>{currentRun.passed} / {currentRun.total || '—'} {t('runtime.tests')} · {currentRun.failed} {t('dock.failed')}</p>
                <div className="workspace-inspector-fact"><span>{t('inspector.browser')}</span><strong>{currentRun.browser}</strong></div>
                {currentRun.log_output && <pre className="workspace-inspector-log">{currentRun.log_output.slice(-900)}</pre>}
                {!!currentRun.external_artifacts?.length && <details><summary>{t('inspector.artifacts', { count: currentRun.external_artifacts.length })}</summary>{currentRun.external_artifacts.map((item) => <p key={item.id}>{item.name}</p>)}</details>}
                {currentFailure && <button type="button" className="btn btn-primary btn-sm" onClick={() => updateContext({ failureId: currentFailure.id, stage: 'failure', view: 'results' })}>{t('inspector.resolveFailure')}</button>}
              </section> : <p className="workspace-muted">{t('inspector.noRun')}</p>}
            </div>}
          </div>
        </div>
        </div>
        </>
      )}

      {showRunPanel && runtimePanelId && <div className="workspace-run-panel-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowRunPanel(false); }}>
        <section className="workspace-run-panel" role="dialog" aria-modal="true" aria-label={runtimePanelTitle}>
          <header><div><span className="workspace-eyebrow">{runtimePanelTitle}</span><strong>{runtimePanelHeading}</strong></div><button type="button" className="btn btn-icon btn-sm" aria-label={t('main.closeRunDetails')} onClick={() => setShowRunPanel(false)}><X size={15} /></button></header>
          <div className="workspace-run-panel-body"><RuntimeDetail kind={runtimePanelKind} id={runtimePanelId} initialTab={runtimePanelInitialTab} projectId={projectId} onOpenStudio={() => openStudio(binding?.file_path)} /></div>
        </section>
      </div>}
    </div>
  );
}

function WorkspaceContextList<T>({
  items,
  limit,
  filterText,
  renderItem,
  emptyState,
}: {
  items: T[];
  limit: number;
  filterText: (item: T) => string;
  renderItem: (item: T) => ReactNode;
  emptyState: ReactNode;
}) {
  const { t } = useTranslation('workspace');
  const [query, setQuery] = useState('');
  const [showAll, setShowAll] = useState(false);
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = normalizedQuery
    ? items.filter((item) => filterText(item).toLowerCase().includes(normalizedQuery))
    : items;
  const visible = showAll ? filtered : filtered.slice(0, limit);
  const hiddenCount = filtered.length - visible.length;
  return (
    <>
      <div className="workspace-context-filter">
        <Search size={13} aria-hidden="true" />
        <input
          type="search"
          value={query}
          aria-label={t('context.filterPlaceholder')}
          placeholder={t('context.filterPlaceholder')}
          onChange={(event) => { setQuery(event.target.value); setShowAll(false); }}
        />
      </div>
      <div className="workspace-context-list">
        {visible.map(renderItem)}
        {!filtered.length && (normalizedQuery
          ? <p className="workspace-muted">{t('context.noMatches')}</p>
          : emptyState)}
      </div>
      {hiddenCount > 0 && <button type="button" className="workspace-context-more" onClick={() => setShowAll(true)}>{t('context.showMore', { count: hiddenCount })}</button>}
      {showAll && filtered.length > limit && <button type="button" className="workspace-context-more" onClick={() => setShowAll(false)}>{t('context.showLess')}</button>}
    </>
  );
}

function RunResultSurface({
  context,
  run,
  testCases,
  task,
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
  canStartRun,
  onManualAnalysis,
  onSelectExecution,
}: {
  context: WorkspaceContext;
  run: TestRun | null;
  testCases: TestCase[];
  task: AgentTask | null;
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
  canStartRun: boolean;
  onManualAnalysis: () => void;
  onSelectExecution: (nodeId: string, caseId: string | null) => void;
}) {
  const { t } = useTranslation('workspace');
  if (task && !run) {
    const steps = task.steps ?? task.plan ?? [];
    const goalSummary = task.type === 'QA_GOAL' && task.verification.summary && typeof task.verification.summary === 'object'
      ? task.verification.summary as {
        status?: string;
        work_completed?: string[];
        findings?: Array<Record<string, unknown> | string>;
        changes?: Array<{ file_path?: string; kind?: string }>;
        tests?: { total?: number; passed?: number; failed?: number; skipped?: number };
        runs?: string[];
        cases?: string[];
        artifacts?: Array<{ id: string; name: string; kind: string }>;
        unresolved?: Array<Record<string, unknown> | string>;
        constraints?: string[];
        recommended_next_action?: string;
        verified?: boolean;
      }
      : null;
    const downloadArtifact = async (artifactId: string, name: string) => {
      const blob = await api.downloadArtifact(artifactId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = name;
      anchor.click();
      URL.revokeObjectURL(url);
    };
    const summaryText = (value: Record<string, unknown> | string) => typeof value === 'string'
      ? value
      : String(value.description ?? value.root_cause ?? value.message ?? value.reason ?? JSON.stringify(value));
    if (goalSummary) return <section className="workspace-result-card">
      <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${task.status.toLowerCase()}`}>{t('result.executionStatus', { status: t(`result.workflowStatus.${task.status}`, { defaultValue: task.status }) })}</span><span className={`workspace-status-badge is-${(goalSummary.status ?? task.status).toLowerCase()}`}>{t(`result.status.${goalSummary.status ?? task.status}`, { defaultValue: t(`result.workflowStatus.${goalSummary.status ?? task.status}`, { defaultValue: goalSummary.status ?? task.status }) })}</span><h3>{task.goal}</h3><code>{task.id}</code></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenDetails}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
      <div className="workspace-goal-result">
        {goalSummary.tests && goalSummary.runs?.length ? <dl className="workspace-result-metrics"><div><dt>{t('result.total')}</dt><dd>{goalSummary.tests.total ?? 0}</dd></div><div><dt>{t('result.passed')}</dt><dd>{goalSummary.tests.passed ?? 0}</dd></div><div><dt>{t('result.failed')}</dt><dd>{goalSummary.tests.failed ?? 0}</dd></div><div><dt>{t('result.skipped')}</dt><dd>{goalSummary.tests.skipped ?? 0}</dd></div></dl> : <p className="workspace-muted">{t('result.testsNotRun')}</p>}
        {goalSummary.work_completed?.length ? <section><h4>{t('result.workCompleted')}</h4><ul>{goalSummary.work_completed.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></section> : null}
        {goalSummary.findings?.length ? <section><h4>{t('result.findings')}</h4><ul>{goalSummary.findings.map((item, index) => <li key={index}>{summaryText(item)}</li>)}</ul></section> : null}
        {goalSummary.changes?.length ? <section><h4>{t('result.changes')}</h4><div className="workspace-goal-links">{goalSummary.changes.map((item, index) => item.file_path
          ? <button type="button" key={`${item.file_path}-${index}`} onClick={() => onOpenCode(item.file_path!)}>{item.file_path}</button>
          : <span key={index}>{item.kind}</span>)}</div></section> : null}
        <section><h4>{t('result.evidence')}</h4><div className="workspace-goal-links">
          {(goalSummary.runs ?? []).map((id) => <Link key={id} to={buildWorkspaceHref({ ...context, projectId, taskId: undefined, runId: id, stage: 'result', view: 'results' })}>{t('result.viewRun')} · {id.slice(0, 8)}</Link>)}
          {(goalSummary.cases ?? []).map((id) => <Link key={id} to={buildWorkspaceHref({ ...context, projectId, taskId: undefined, testCaseId: id, stage: 'cases', view: 'cases' })}>{t('result.viewCase')} · {id.slice(0, 8)}</Link>)}
          {goalSummary.findings?.flatMap((item, index) => {
            const failureId = typeof item === 'object' && item ? item.failure_id : undefined;
            return typeof failureId === 'string' ? [<Link key={`${failureId}-${index}`} to={buildWorkspaceHref({ ...context, projectId, failureId, stage: 'failure' })}>{t('result.viewFailure')} · {failureId.slice(0, 8)}</Link>] : [];
          })}
          {goalSummary.artifacts?.map((item) => <button type="button" key={item.id} onClick={() => void downloadArtifact(item.id, item.name)}>{t('result.downloadArtifact')} · {item.name}</button>)}
        </div></section>
        {goalSummary.unresolved?.length ? <section><h4>{t('result.unresolved')}</h4><ul>{goalSummary.unresolved.map((item, index) => <li key={index}>{summaryText(item)}</li>)}</ul></section> : null}
        {goalSummary.constraints?.length ? <section><h4>{t('goal.constraints')}</h4><ul>{goalSummary.constraints.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></section> : null}
        {goalSummary.recommended_next_action && <section><h4>{t('result.nextAction')}</h4><p>{goalSummary.recommended_next_action}</p></section>}
      <details className="workspace-goal-activity"><summary>{t('result.stepActivity')} · {steps.length}</summary><ol className="workspace-step-list">{steps.map((item) => <li key={item.id}><span>{t(`result.taskStatus.${item.status}`, { defaultValue: item.status })}</span><strong>{item.name}</strong>{item.error && <small>{item.error}</small>}</li>)}</ol></details>
      </div>
    </section>;
    if (task.type === 'QA_GOAL') return <section className="workspace-result-card">
      <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${task.status.toLowerCase()}`}>{t(`result.workflowStatus.${task.status}`, { defaultValue: task.status })}</span><h3>{task.goal}</h3><code>{task.id}</code></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenDetails}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
      {task.failure_reason && <p role="status">{task.failure_reason}</p>}
      <details className="workspace-goal-activity" open><summary>{t('result.stepActivity')} · {steps.length}</summary><ol className="workspace-step-list">{steps.map((item) => <li key={item.id}><span>{item.status}</span><strong>{item.name}</strong>{item.error && <small>{item.error}</small>}</li>)}</ol></details>
    </section>;
    return <section className="workspace-result-card">
      <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${task.status.toLowerCase()}`}>{t(`result.workflowStatus.${task.status}`, { defaultValue: task.status })}</span><h3>{task.goal}</h3></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenDetails}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
      <p>{t('result.taskSummary', { completed: steps.filter((item) => item.status === 'COMPLETED').length, total: steps.length })}</p>
      <ol className="workspace-step-list">{steps.map((item) => <li key={item.id} className={`is-${item.status.toLowerCase()}`}><span>{item.status}</span><strong>{item.name}</strong><small>{item.error ?? (Object.keys(item.outputs).length ? JSON.stringify(item.outputs) : '')}</small></li>)}</ol>
    </section>;
  }
  if (!run) return <section className="workspace-result-card workspace-empty"><Play size={20} aria-hidden="true" /><h3>{t('result.noRun')}</h3><p>{t('result.noRunDescription')}</p><div className="workspace-empty-actions"><button type="button" className="btn btn-primary" onClick={onRerun} disabled={!canStartRun}><Play size={14} aria-hidden="true" />{t('result.startRun')}</button><button type="button" className="btn btn-secondary" onClick={() => onOpenCode(context.file ?? '')}>{t('result.configureAutomation')}</button><button type="button" className="btn btn-secondary" onClick={onManualAnalysis}>{t('result.viewExecutionPlan')}</button></div>{!canStartRun && <p className="workspace-muted">{t('result.runRequiresBinding')}</p>}</section>;

  return <WorkspaceRunResult
    key={`${projectId}:${run.id}`}
    context={context}
    run={run}
    testCases={testCases}
    runtime={runtime}
    runtimeConnection={runtimeConnection}
    runtimeError={runtimeError}
    onRefreshRuntime={onRefreshRuntime}
    projectId={projectId}
    onOpenCode={onOpenCode}
    onOpenDetails={onOpenDetails}
    onOpenStep={onOpenStep}
    onStop={onStop}
    onRerun={onRerun}
    onManualAnalysis={onManualAnalysis}
    onSelectExecution={onSelectExecution}
  />;
}
