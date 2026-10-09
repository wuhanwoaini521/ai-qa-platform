import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, ArrowUpRight, FileCode2, GitBranch, PanelLeftClose, PanelLeftOpen, PanelRightOpen, Play, Sparkles, Workflow, X } from 'lucide-react';
import { api } from '../../api/client';
import { useProjectScope, useRouteProjectScope } from '../../app/ProjectScope';
import {
  buildWorkspaceHref,
  readWorkspaceContext,
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
import { RuntimeDetail } from '../runtime/RuntimeDetail';
import { failureSourceLocation } from '../failures/failureWorkspaceModel';
import { WorkspaceRunDock, type WorkspaceRunConfig } from './WorkspaceRunDock';
import { bindingForSelectedCase, configForRerun, defaultWorkspaceGoal, workspaceGoalTarget } from './workspaceRunModel';
import type { AgentGoalPreview, AgentTask, FailureRecord, Project, Requirement, TestCase, TestRun } from '../../types';
import { runtimeActive } from '../runtime/runtimeModel';
import './workspace.css';

const AutomationStudioPage = lazy(() => import('../automation-studio/AutomationStudioPage').then((module) => ({ default: module.AutomationStudioPage })));
const RecorderPage = lazy(() => import('../../pages/RecorderPage').then((module) => ({ default: module.RecorderPage })));

const workspaceStages: { stage: WorkspaceStage; view: WorkspaceView }[] = [
  { stage: 'requirement', view: 'requirement' },
  { stage: 'cases', view: 'cases' },
  { stage: 'automation', view: 'code' },
  { stage: 'result', view: 'results' },
];
const automationViews: WorkspaceView[] = ['code', 'browser', 'debug'];
const stageForView: Record<WorkspaceView, WorkspaceStage> = {
  requirement: 'requirement',
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
  const [showInspector, setShowInspector] = useState(false);
  const [showWorkspaceContext, setShowWorkspaceContext] = useState(false);
  const [inspectorTab, setInspectorTab] = useState<'context' | 'ai' | 'run'>('context');
  const inspectorTriggerRef = useRef<HTMLButtonElement>(null);
  const inspectorDrawerRef = useRef<HTMLElement>(null);
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
    first?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowInspector(false);
        return;
      }
      if (event.key !== 'Tab') return;
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
  }, [showInspector]);

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
        file: preserveFailureDebugContext ? context.file : nextCase?.binding?.file_path,
        lineNumber: preserveFailureDebugContext ? context.lineNumber : undefined,
        nodeId: preserveFailureDebugContext ? context.nodeId : nextCase?.binding?.nodeid,
        stage: context.stage ?? 'requirement',
      }, true);
    }
    // URL remains the source of truth after the first actual data load.
  }, [projectId, contextDataLoaded, requirements, cases, context.requirementId, context.testCaseId, context.testDesignId, context.automationBindingId, context.nodeId, context.stage]);

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
  const goalTarget = workspaceGoalTarget(goalText, context);
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
    ...(goalTarget === 'failure' && context.failureId ? { failure_id: context.failureId } : {}),
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
  const currentFailure = failures.find((item) => item.run_id === activeRunId)
    ?? failures.find((item) => item.id === context.failureId)
    ?? null;
  const currentFailureSource = currentFailure ? failureSourceLocation(currentFailure) : null;
  const currentRun = runLive.run ?? runs.find((item) => item.id === activeRunId) ?? null;

  useEffect(() => {
    if (!projectId || !currentRun || !['FAILED', 'ERROR'].includes(currentRun.status)) return;
    let active = true;
    void api.getFailures(projectId, 50).then((items) => {
      if (active) setFailures(items);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [projectId, currentRun?.id, currentRun?.status]);
  const progressTaskId = context.taskId ?? (runtime.snapshot?.kind === 'task' ? runtime.snapshot.id : task?.id ?? null);
  const runtimePanelId = runtimePanelKind === 'task' ? progressTaskId : activeRunId;
  const runtimePanelTitle = runtimePanelKind === 'task' ? t('inspector.task') : t('dock.runDetails');
  const runtimePanelHeading = runtimePanelKind === 'task'
    ? task?.id === progressTaskId ? task.goal : progressTaskId
    : currentRun?.requested_by ?? activeRunId;
  const analysisFailed = !analysisRunning && ['FAILED', 'BLOCKED'].includes(latestAnalysisRecord?.status ?? '');
  const project = projects.find((item: Project) => item.id === projectId);
  const completedGoalResult = stage === 'result'
    && task?.type === 'QA_GOAL'
    && !runtimeActive(runtime.snapshot?.status ?? task.status);
  const resultFailed = Boolean(currentRun && ['FAILED', 'ERROR'].includes(currentRun.status))
    || Boolean(task && ['FAILED', 'BLOCKED'].includes(runtime.snapshot?.status ?? task.status));

  useEffect(() => {
    if (!contextDataLoaded || !['result', 'failure'].includes(stage)) return;
    const executedNodeId = currentFailure?.test_nodeid
      ?? (currentRun?.nodeids.length === 1 ? currentRun.nodeids[0] : undefined);
    if (!executedNodeId) return;
    const executedCase = cases.find((item) => item.binding?.nodeid === executedNodeId);
    if (!executedCase || executedCase.id === context.testCaseId) return;
    updateContext({
      requirementId: executedCase.requirement_id ?? context.requirementId,
      testCaseId: executedCase.id,
      testDesignId: executedCase.test_design_id ?? undefined,
      automationBindingId: executedCase.binding?.id,
      file: executedCase.binding?.file_path,
      nodeId: executedNodeId,
    }, true);
  }, [contextDataLoaded, stage, currentFailure?.test_nodeid, currentRun?.id, currentRun?.nodeids, cases, context.testCaseId, context.requirementId]);

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
    if (!projectId || !selectedCase || binding?.status !== 'ACTIVE' || !binding.nodeid || runBusy) return;
    setRunBusy(true);
    setRunError('');
    try {
      const selectedRunConfig = rerun && currentRun ? configForRerun(currentRun, runConfig) : runConfig;
      const run = await api.createTestRun({
        project_id: projectId,
        workspace_id: projectId,
        nodeids: [binding.nodeid],
        requested_by: `Workspace · ${selectedCase.title}`,
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

  const openRunDetails = (extra: Partial<WorkspaceContext> = {}) => {
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
    if (taskId || runId) setShowRunPanel(true);
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

  return (
    <main className="workspace-shell" aria-label={t('title')}>
      <header className="workspace-heading">
        <div>
          <span className="workspace-eyebrow">{t('eyebrow')} · {(project?.name ?? projectId) || t('chooseProject')}</span>
          <h1>{t('title')}</h1>
          <p>{t('subtitle')}</p>
        </div>
        <div className="workspace-heading-actions">
          {selectedRequirement && <span className="workspace-context-chip"><GitBranch size={14} aria-hidden="true" />{selectedRequirement.qa_model?.display_id ?? selectedRequirement.title}</span>}
          {projectId && <button type="button" className="btn btn-secondary btn-sm workspace-context-toggle" aria-label={t(showWorkspaceContext ? 'context.hidePanel' : 'context.showPanel')} aria-expanded={showWorkspaceContext} aria-controls="workspace-context-panel" onClick={() => setShowWorkspaceContext((visible) => !visible)} title={t(showWorkspaceContext ? 'context.hidePanel' : 'context.showPanel')}>
            {showWorkspaceContext ? <PanelLeftClose size={14} aria-hidden="true" /> : <PanelLeftOpen size={14} aria-hidden="true" />}
            <span>{t(showWorkspaceContext ? 'context.hidePanel' : 'context.showPanel')}</span>
          </button>}
          {projectId && <button ref={inspectorTriggerRef} type="button" className="btn btn-secondary btn-sm" aria-expanded={showInspector} aria-controls="workspace-inspector-drawer" onClick={() => setShowInspector(true)}><PanelRightOpen size={14} aria-hidden="true" />{t('inspector.title')}</button>}
          {completedGoalResult && <button type="button" className="btn btn-secondary btn-sm" onClick={() => updateContext({ taskId: undefined, runId: undefined, stage: 'requirement', view: 'requirement' })}>{t('goal.new')}</button>}
          {(context.taskId || context.runId) && <button type="button" className="btn btn-secondary btn-sm" onClick={() => openRunDetails()}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button>}
        </div>
      </header>

      {projectId && <nav className="workspace-stage-nav" role="tablist" aria-label={t('tabs.label')}>
        {workspaceStages.map((item) => <button
          key={item.stage}
          type="button"
          role="tab"
          aria-selected={stage === item.stage}
          className={`workspace-view-tab${stage === item.stage ? ' is-current' : ''}${item.stage === 'result' && resultFailed ? ' has-failure' : ''}`}
          onClick={() => setView(item.view)}
        >
          {t(`journey.${item.stage}`)}
          {item.stage === 'result' && activeRunId && <span className={`workspace-tab-status is-${(currentRun?.status ?? runtime.snapshot?.status ?? 'idle').toLowerCase()}`} aria-hidden="true" />}
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
        <div className={`workspace-grid${stage === 'failure' ? ' is-failure-stage' : ''}${view === 'debug' ? ' is-debug-view' : ''}${showWorkspaceContext ? '' : ' is-context-collapsed'}`}>
          <aside id="workspace-context-panel" className="workspace-context-panel" aria-label={t('context.title')}>
            <div className="workspace-panel-heading"><h2>{t('context.title')}</h2><small>{project?.name ?? projectId}</small></div>
            <section className="workspace-context-group">
              <div className="workspace-group-heading"><h3>{t('context.requirements')}</h3></div>
              <div className="workspace-context-list">
                {requirements.slice(0, 12).map((item) => <button key={item.id} type="button" className={item.id === context.requirementId ? 'is-selected' : ''} aria-pressed={item.id === context.requirementId} onClick={() => selectRequirement(item.id)}>
                  <span>{item.qa_model?.display_id ?? item.id.slice(-6)}</span><strong>{item.title}</strong>
                </button>)}
                {!contextDataLoaded ? <p className="workspace-muted">{contextLoading ? t('context.loading') : t('context.unavailable')}</p> : !requirements.length && <><p className="workspace-muted">{t('context.noRequirements')}</p>{projects.length > 1 && <Link className="btn btn-secondary btn-sm" to="/projects">{t('context.chooseProject')}</Link>}</>}
              </div>
            </section>
            <section className="workspace-context-group">
              <div className="workspace-group-heading"><h3>{t('context.cases')}</h3></div>
              <div className="workspace-context-list">
                {relatedCases.slice(0, 10).map((item) => <button key={item.id} type="button" className={item.id === context.testCaseId ? 'is-selected' : ''} aria-pressed={item.id === context.testCaseId} onClick={() => selectCase(item)}>
                  <span>{item.test_model?.display_id ?? item.id.slice(-6)}</span><strong>{item.title}</strong><small>{item.automation_status}</small>
                </button>)}
                {!contextDataLoaded ? <p className="workspace-muted">{contextLoading ? t('context.loading') : t('context.unavailable')}</p> : !relatedCases.length && <p className="workspace-muted">{t('context.noCases')}</p>}
              </div>
            </section>
            {binding && <section className="workspace-context-group workspace-binding-card">
              <div className="workspace-group-heading"><h3>{t('context.automation')}</h3><span className={`workspace-binding-status is-${binding.status.toLowerCase()}`}>{binding.status}</span></div>
              <button type="button" onClick={() => openStudio(binding.file_path)}><FileCode2 size={14} aria-hidden="true" /><span>{binding.file_path}</span></button>
            </section>}
          </aside>

          <section className="workspace-main-panel" aria-label={t('main.title')}>
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
              {view === 'cases' && <TestCasesPage
                projects={projects}
                selectedProjectId={projectId}
                initialRequirementId={context.requirementId}
                initialTestCaseId={context.testCaseId}
                onSelectTestCase={(id) => updateContext({ testCaseId: id, view: 'cases', stage: 'cases' })}
                onCaseCreated={(createdCase) => {
                  setCases((items) => [...items.filter((item) => item.id !== createdCase.id), createdCase]);
                  updateContext({ requirementId: createdCase.requirement_id ?? context.requirementId, testCaseId: createdCase.id, view: 'cases', stage: 'cases' });
                }}
                onNavigateToStudio={(filePath) => openStudio(filePath)}
                onNavigateToRuns={onRunStarted}
                onTaskStarted={onTaskStarted}
                workspaceMode
                hideRunAction
              />}
              {(view === 'code' || view === 'debug') && <Suspense fallback={<div className="workspace-surface-loading" role="status">{t('main.loadingEditor')}</div>}><AutomationStudioPage
                key={projectId}
                projects={projects}
                selectedProjectId={projectId}
                onSelectProject={selectProject}
                onNavigateToRuns={onRunStarted}
                onRunCreated={onRunStarted}
                workspaceView={view === 'debug' ? 'debug' : 'code'}
                initialOpenFilePath={automationSetup ? null : view === 'debug' || !selectedCase ? context.file ?? automationFilePath : automationFilePath}
                workspaceAutomationSetup={automationSetup}
                workspaceAutomationSetupKey={automationSetupKey}
                onStartRecording={() => setView('browser')}
                onSelectCases={() => setView('cases')}
                initialOpenLineNumber={context.lineNumber ?? null}
                initialDebugNodeId={view === 'debug' && context.failureId ? context.nodeId ?? null : null}
                embedded
              /></Suspense>}
              {view === 'browser' && <Suspense fallback={<div className="workspace-surface-loading" role="status">{t('main.loadingBrowser')}</div>}><RecorderPage
                projects={projects}
                selectedProjectId={projectId}
                embedded
                runConfig={runConfig}
                onNavigateToRuns={onRunStarted}
              /></Suspense>}
              {view === 'results' && stage !== 'failure' && <RunResultSurface
                context={context}
                run={currentRun}
                task={task}
                projectId={projectId}
                onOpenFailure={(failureId) => updateContext({ failureId, stage: 'failure', view: 'results' })}
                onOpenCode={(filePath) => openStudio(filePath)}
                onOpenDetails={() => openRunDetails()}
              />}
              {view === 'results' && stage === 'failure' && <FailuresPage
                projects={projects}
                selectedProjectId={projectId}
                initialFailureId={context.failureId}
                onSelectFailure={(failureId) => updateContext({ failureId })}
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
                workspaceMode
              />}
            </div>
          </section>

        </div>
        <div className="workspace-inspector-overlay" hidden={!showInspector} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowInspector(false); }}>
          <aside id="workspace-inspector-drawer" ref={inspectorDrawerRef} className="workspace-inspector workspace-inspector-drawer" role="dialog" aria-modal={showInspector} aria-label={t('inspector.title')}>
            <div className="workspace-panel-heading"><div><h2>{t('inspector.title')}</h2><span className="workspace-live-label"><i aria-hidden="true" />{t('inspector.liveContext')}</span></div><button type="button" className="btn btn-icon btn-sm" aria-label={t('inspector.close')} onClick={() => setShowInspector(false)}><X size={15} /></button></div>
            <div className="workspace-inspector-tabs" role="tablist" aria-label={t('inspector.title')}>
              {(['context', 'ai', 'run'] as const).map((item) => <button key={item} type="button" role="tab" aria-selected={inspectorTab === item} className={inspectorTab === item ? 'is-selected' : ''} onClick={() => setInspectorTab(item)}>{t(`inspector.tabs.${item}`)}</button>)}
            </div>
            {inspectorTab === 'context' && <div className="workspace-inspector-content">
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
            {inspectorTab === 'ai' && <div className="workspace-inspector-content">
              {task ? <section className="workspace-inspector-section">
                <span>{t('inspector.task')}</span><strong>{runtime.snapshot?.id === task.id ? runtime.snapshot.status : task.status}</strong><p>{task.goal}</p>
                {(runtime.snapshot?.steps ?? task.steps ?? task.plan).slice(0, 5).map((step) => <div className="workspace-inspector-fact" key={step.id}><span>{step.status}</span><strong>{'title' in step ? step.title : step.name}</strong></div>)}
                {!!runtime.snapshot?.decisions.length && <details className="workspace-decision-trace"><summary>{t('inspector.decisionTrace')}</summary>{runtime.snapshot.decisions.map((decision) => <p key={decision.id}><strong>{decision.selected}</strong> · {decision.name}</p>)}</details>}
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => openRunDetails({ taskId: task.id })}><Workflow size={13} aria-hidden="true" />{t('inspector.advancedTrace')}</button>
              </section> : <p className="workspace-muted">{t('inspector.aiIdle')}</p>}
              {goalError && <p className="workspace-goal-error" role="alert">{goalError}</p>}
            </div>}
            {inspectorTab === 'run' && <div className="workspace-inspector-content">
              {currentRun ? <section className="workspace-inspector-section">
                <span>{t('inspector.run')}</span><strong>{currentRun.status}</strong>
                <p>{currentRun.passed} / {currentRun.total || '—'} {t('runtime.tests')} · {currentRun.failed} {t('dock.failed')}</p>
                <div className="workspace-inspector-fact"><span>{t('inspector.browser')}</span><strong>{currentRun.browser}</strong></div>
                {currentRun.log_output && <pre className="workspace-inspector-log">{currentRun.log_output.slice(-900)}</pre>}
                {!!currentRun.external_artifacts?.length && <details><summary>{t('inspector.artifacts', { count: currentRun.external_artifacts.length })}</summary>{currentRun.external_artifacts.map((item) => <p key={item.id}>{item.name}</p>)}</details>}
                {currentFailure && <button type="button" className="btn btn-primary btn-sm" onClick={() => updateContext({ failureId: currentFailure.id, stage: 'failure', view: 'results' })}>{t('inspector.resolveFailure')}</button>}
              </section> : <p className="workspace-muted">{t('inspector.noRun')}</p>}
            </div>}
          </aside>
        </div>
        </>
      )}

      {projectId && <WorkspaceRunDock
        caseLabel={selectedCase?.test_model?.display_id ?? (selectedCase?.id ? selectedCase.id.slice(-6).toUpperCase() : '')}
        caseTitle={selectedCase?.title ?? ''}
        hasAutomation={binding?.status === 'ACTIVE' && Boolean(binding.nodeid)}
        aiRunLabel={goalTarget === 'requirement' ? t('dock.aiRunRequirement') : context.testCaseId && !binding ? t('dock.aiGenerateAutomation') : undefined}
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
            testCaseId: context.testCaseId,
            stage,
            hasAutomation: binding?.status === 'ACTIVE' && Boolean(binding.nodeid),
          }));
          setAiRunOpen(true);
        }}
        onStop={() => void stopActiveRun()}
        onOpen={openRunDetails}
        onViewResult={() => { setShowRunPanel(false); setView('results'); }}
        onViewFailure={() => void diagnoseCurrentRun()}
        onDebug={() => updateContext({ file: currentFailureSource?.filePath ?? selectedCase?.binding?.file_path ?? context.file, lineNumber: currentFailureSource?.lineNumber ?? context.lineNumber, nodeId: currentFailure?.test_nodeid ?? binding?.nodeid ?? context.nodeId, failureId: currentFailure?.id ?? context.failureId, stage: 'automation', view: 'debug' })}
        onRerun={() => void runSelectedCase(true)}
        onOpenCode={() => setView('code')}
      />}
      {showRunPanel && runtimePanelId && <div className="workspace-run-panel-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowRunPanel(false); }}>
        <section className="workspace-run-panel" role="dialog" aria-modal="true" aria-label={runtimePanelTitle}>
          <header><div><span className="workspace-eyebrow">{runtimePanelTitle}</span><strong>{runtimePanelHeading}</strong></div><button type="button" className="btn btn-icon btn-sm" aria-label={t('aiRun.close')} onClick={() => setShowRunPanel(false)}><X size={15} /></button></header>
          <div className="workspace-run-panel-body"><RuntimeDetail kind={runtimePanelKind} id={runtimePanelId} projectId={projectId} onOpenStudio={() => openStudio(binding?.file_path)} /></div>
        </section>
      </div>}
    </main>
  );
}

function RunResultSurface({
  context,
  run,
  task,
  projectId,
  onOpenFailure,
  onOpenCode,
  onOpenDetails,
}: {
  context: WorkspaceContext;
  run: TestRun | null;
  task: AgentTask | null;
  projectId: string;
  onOpenFailure: (failureId: string) => void;
  onOpenCode: (filePath: string) => void;
  onOpenDetails: () => void;
}) {
  const { t } = useTranslation('workspace');
  const [failures, setFailures] = useState<FailureRecord[]>([]);
  useEffect(() => {
    if (!run) return;
    let active = true;
    void api.getFailures(projectId, 50).then((rows) => {
      if (active) setFailures(rows.filter((item) => item.run_id === run.id));
    }).catch(() => { if (active) setFailures([]); });
    return () => { active = false; };
  }, [projectId, run?.id, run?.status]);

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
      <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${task.status.toLowerCase()}`}>{t('result.executionStatus', { status: t(`result.taskStatus.${task.status}`, { defaultValue: task.status }) })}</span><span className={`workspace-status-badge is-${(goalSummary.status ?? task.status).toLowerCase()}`}>{t(`result.status.${goalSummary.status ?? task.status}`, { defaultValue: t(`result.taskStatus.${goalSummary.status ?? task.status}`, { defaultValue: goalSummary.status ?? task.status }) })}</span><h3>{task.goal}</h3><code>{task.id}</code></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenDetails}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
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
      <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${task.status.toLowerCase()}`}>{t(`result.taskStatus.${task.status}`, { defaultValue: task.status })}</span><h3>{task.goal}</h3><code>{task.id}</code></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenDetails}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
      {task.failure_reason && <p role="status">{task.failure_reason}</p>}
      <details className="workspace-goal-activity" open><summary>{t('result.stepActivity')} · {steps.length}</summary><ol className="workspace-step-list">{steps.map((item) => <li key={item.id}><span>{item.status}</span><strong>{item.name}</strong>{item.error && <small>{item.error}</small>}</li>)}</ol></details>
    </section>;
    return <section className="workspace-result-card">
      <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${task.status.toLowerCase()}`}>{t(`result.taskStatus.${task.status}`, { defaultValue: task.status })}</span><h3>{task.goal}</h3></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenDetails}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
      <p>{t('result.taskSummary', { completed: steps.filter((item) => item.status === 'COMPLETED').length, total: steps.length })}</p>
      <ol className="workspace-step-list">{steps.map((item) => <li key={item.id} className={`is-${item.status.toLowerCase()}`}><span>{item.status}</span><strong>{item.name}</strong><small>{item.error ?? (Object.keys(item.outputs).length ? JSON.stringify(item.outputs) : '')}</small></li>)}</ol>
    </section>;
  }
  if (!run) return <section className="workspace-result-card workspace-empty"><Play size={20} aria-hidden="true" /><h3>{t('result.noRun')}</h3><p>{t('result.noRunDescription')}</p></section>;

  return <section className="workspace-result-card">
    <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${run.status.toLowerCase()}`}>{run.status}</span><h3>{run.requested_by || t('result.runTitle')}</h3><code>{run.id}</code></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenDetails}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
    <dl className="workspace-result-metrics"><div><dt>{t('result.total')}</dt><dd>{run.total || '—'}</dd></div><div><dt>{t('result.passed')}</dt><dd>{run.passed}</dd></div><div><dt>{t('result.failed')}</dt><dd>{run.failed}</dd></div><div><dt>{t('result.duration')}</dt><dd>{run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)} s` : '—'}</dd></div></dl>
    {failures.length > 0 && <section className="workspace-failure-list"><h4>{t('result.failures')}</h4>{failures.map((failure) => <button key={failure.id} type="button" onClick={() => onOpenFailure(failure.id)}><span className="workspace-status-mark is-failed" aria-hidden="true" /><span><strong>{failure.test_name || failure.test_nodeid}</strong><small>{failure.classification} · {failure.error_message}</small></span><ArrowUpRight size={14} aria-hidden="true" /></button>)}</section>}
    {run.executions.length > 0 && <ol className="workspace-execution-list">{run.executions.map((execution) => <li key={execution.id}><span className={`workspace-status-mark is-${execution.status.toLowerCase()}`} aria-hidden="true" /><strong>{execution.nodeid}</strong><span>{execution.status}</span><small>{execution.duration_ms ? `${(execution.duration_ms / 1000).toFixed(2)} s` : '—'}</small></li>)}</ol>}
    {!failures.length && ['FAILED', 'ERROR'].includes(run.status) && <p className="workspace-muted">{t('result.failureLoading')}</p>}
    {context.testCaseId && <Link className="workspace-result-back" to={buildWorkspaceHref({ ...context, projectId, stage: 'cases', view: 'cases' })}>{t('result.openCase')}</Link>}
  </section>;
}
