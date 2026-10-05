import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, ArrowUpRight, FileCode2, GitBranch, Play, Plus, Sparkles, Workflow } from 'lucide-react';
import { api } from '../../api/client';
import { useProjectScope, useRouteProjectScope } from '../../app/ProjectScope';
import {
  buildStudioHref,
  buildWorkspaceHref,
  buildWorkflowHref,
  readWorkspaceContext,
  writeWorkspaceContext,
  type WorkspaceContext,
  type WorkspaceStage,
} from '../../app/workspaceContext';
import { RequirementsPage } from '../requirements/RequirementsPage';
import { TestCasesPage } from '../test-cases/TestCasesPage';
import { FailuresPage } from '../../pages/FailuresPage';
import { useRunStore } from '../runs/useRunStore';
import { RuntimeMiniBar } from '../runtime/RuntimeMiniBar';
import { useRuntimeSnapshot } from '../runtime/useRuntimeSnapshot';
import type { AgentGoalPreview, AgentTask, FailureRecord, FileNode, Project, Requirement, TestCase, TestRun } from '../../types';
import type { RuntimeEvent } from '../../types/runtime';
import { runtimeActive } from '../runtime/runtimeModel';
import { RuntimeTaskActions } from '../runtime/RuntimeTaskActions';
import './workspace.css';

const stages: WorkspaceStage[] = ['requirement', 'cases', 'automation', 'result', 'failure'];

function flattenFiles(nodes: FileNode[], output: FileNode[] = []): FileNode[] {
  for (const node of nodes) {
    if (node.type === 'file') output.push(node);
    if (node.children?.length) flattenFiles(node.children, output);
  }
  return output;
}

export function WorkspacePage() {
  const { t } = useTranslation('workspace');
  const { projectId: routeProjectId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { projects, selectedProjectId, selectProject } = useProjectScope();
  useRouteProjectScope(routeProjectId);
  const projectId = routeProjectId ?? searchParams.get('projectId') ?? selectedProjectId ?? '';
  const context = readWorkspaceContext(searchParams, projectId);
  const stage = context.stage ?? 'requirement';
  const runLive = useRunStore(context.runId ?? null);
  const runtimeKind = context.taskId ? 'task' : 'run';
  const runtimeId = context.taskId ?? context.runId ?? '';
  const runtime = useRuntimeSnapshot(runtimeKind, runtimeId);
  const [analysisStarting, setAnalysisStarting] = useState(false);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [cases, setCases] = useState<TestCase[]>([]);
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [failures, setFailures] = useState<FailureRecord[]>([]);
  const [files, setFiles] = useState<FileNode[]>([]);
  const [binding, setBinding] = useState<Awaited<ReturnType<typeof api.getAutomationBinding>>>(null);
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

  const isAnalysisTask = runtime.snapshot?.task?.type === 'ANALYZE_REQUIREMENT';
  const analysisProgressEvent: RuntimeEvent | null = isAnalysisTask
    ? runtime.snapshot?.events.filter((event) => event.type === 'workflow.step').at(-1) ?? null
    : null;
  const analysisRunning = analysisStarting || Boolean(
    isAnalysisTask && runtime.snapshot && runtimeActive(runtime.snapshot.status),
  );

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
      api.getWorkspaceFiles(projectId),
    ]).then(([nextRequirements, nextCases, nextRuns, nextFailures, nextFiles]) => {
      if (!active) return;
      setRequirements(nextRequirements);
      setCases(nextCases);
      setRuns(nextRuns);
      setFailures(nextFailures);
      setFiles(nextFiles);
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
      setBinding(null);
      return;
    }
    let active = true;
    void api.getAutomationBinding(selectedCase).then((value) => {
      if (active) setBinding(value);
    }).catch(() => { if (active) setBinding(null); });
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
    const requirementId = requirements.some((item) => item.id === context.requirementId)
      ? context.requirementId
      : requirements[0]?.id;
    const selectedCaseExists = cases.some((item) => item.id === context.testCaseId);
    const selectedCase = cases.find((item) => item.id === context.testCaseId);
    const relatedCase = selectedCaseExists
      ? undefined
      : cases.find((item) => item.requirement_id === requirementId);
    const nextCase = selectedCase ?? relatedCase;
    if (
      requirementId !== context.requirementId ||
      relatedCase ||
      (context.testCaseId && !selectedCaseExists) ||
      context.testDesignId !== (nextCase?.test_design_id ?? undefined)
    ) {
      updateContext({
        requirementId,
        testCaseId: nextCase?.id,
        testDesignId: nextCase?.test_design_id ?? undefined,
        stage: context.stage ?? 'requirement',
      }, true);
    }
    // URL remains the source of truth after the first actual data load.
  }, [projectId, contextDataLoaded, requirements, cases, context.requirementId, context.testCaseId]);

  function updateContext(patch: Partial<WorkspaceContext>, replace = false) {
    setSearchParams((current) => writeWorkspaceContext(current, {
      ...readWorkspaceContext(current, projectId),
      projectId: projectId || undefined,
      ...patch,
    }), { replace });
  }

  const selectedRequirement = requirements.find((item) => item.id === context.requirementId) ?? null;
  const relatedCases = useMemo(
    () => cases.filter((item) => !context.requirementId || item.requirement_id === context.requirementId),
    [cases, context.requirementId],
  );
  const selectedCase = cases.find((item) => item.id === context.testCaseId) ?? null;
  const selectedCaseOnly = ['cases', 'automation'].includes(stage)
    && Boolean(context.testCaseId)
    && !/(需求|requirement)/i.test(goalText);
  const goalInputs: Record<string, unknown> = {
    ...(context.failureId ? { failure_id: context.failureId } : {}),
    ...(!context.failureId && selectedCaseOnly && context.testCaseId ? { test_case_id: context.testCaseId } : {}),
    ...(!context.failureId && !selectedCaseOnly && context.requirementId ? { requirement_id: context.requirementId } : {}),
    ...(!context.failureId && !context.requirementId && context.testCaseId ? { test_case_id: context.testCaseId } : {}),
    ...(context.nodeId ? { nodeids: [context.nodeId] } : selectedCase?.binding?.nodeid ? { nodeids: [selectedCase.binding.nodeid] } : {}),
    ...(context.runId ? { run_id: context.runId } : {}),
    ...(context.file ?? binding?.file_path ? { file_path: context.file ?? binding?.file_path } : {}),
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
    if (context.failureId) setGoalText('分析并修复这个失败');
    else if (['cases', 'automation'].includes(stage) && context.testCaseId) setGoalText('生成并验证当前用例自动化');
    else if (context.requirementId) setGoalText('帮我把这个需求测试完整。可以自动完成低风险步骤；需要修改代码时让我确认。');
    else setGoalText('检查这个项目目前还有什么明显测试问题');
  }, [projectId, context.failureId, context.requirementId, context.testCaseId, context.nodeId, context.runId, context.file, binding?.file_path, selectedCase?.binding?.nodeid, stage]);
  const requirementAnalysis = analysisRunning ? null : selectedRequirement?.qa_model?.analysis;
  const latestAnalysisRecord = selectedRequirement?.qa_model?.history.at(-1);
  const latestAnalysisStage = latestAnalysisRecord?.stages.at(-1);
  const analysisEvidence = isAnalysisTask
    ? runtime.snapshot?.evidence.filter((item) => item.type === 'Analysis').at(-1) ?? null
    : null;
  const currentFailure = failures.find((item) => item.id === context.failureId)
    ?? failures.find((item) => item.run_id === context.runId)
    ?? null;
  const currentRun = runLive.run ?? runs.find((item) => item.id === context.runId) ?? null;
  const analysisFailed = !analysisRunning && ['FAILED', 'BLOCKED'].includes(latestAnalysisRecord?.status ?? '');
  const project = projects.find((item: Project) => item.id === projectId);
  const flatFiles = useMemo(() => flattenFiles(files).slice(0, 8), [files]);
  const completedGoalResult = stage === 'result'
    && task?.type === 'QA_GOAL'
    && !runtimeActive(runtime.snapshot?.status ?? task.status);
  const boundCaseCount = relatedCases.filter((item) => Boolean(item.binding)).length;
  const resultFailed = Boolean(currentRun && ['FAILED', 'ERROR'].includes(currentRun.status))
    || Boolean(task && ['FAILED', 'BLOCKED'].includes(runtime.snapshot?.status ?? task.status));
  const resultPassed = currentRun?.status === 'PASSED'
    || Boolean(task && ['COMPLETED', 'SUCCEEDED'].includes(runtime.snapshot?.status ?? task.status));
  const flowLoadState = t(loadError ? 'flow.unavailable' : 'flow.loading');
  const flowSummaries: Record<WorkspaceStage, string> = {
    requirement: !contextDataLoaded ? flowLoadState : selectedRequirement
      ? analysisFailed ? t('flow.analysisFailed') : analysisRunning ? t('flow.analysisRunning') : requirementAnalysis ? t('flow.analysisComplete') : t('flow.analysisPending')
      : t('flow.requirementCount', { count: requirements.length }),
    cases: contextDataLoaded ? t('flow.caseCount', { count: relatedCases.length }) : flowLoadState,
    automation: contextDataLoaded ? t('flow.automationCount', { ready: boundCaseCount, total: relatedCases.length }) : flowLoadState,
    result: currentRun
      ? t('flow.runSummary', { status: currentRun.status, finished: currentRun.executions.filter((item) => item.finished_at).length, total: currentRun.executions.length })
      : task ? t('flow.taskSummary', { status: runtime.snapshot?.status ?? task.status })
        : contextDataLoaded ? t('flow.noRun') : flowLoadState,
    failure: !contextDataLoaded ? flowLoadState : currentFailure
      ? t('flow.failureSelected')
      : failures.length
        ? t('flow.failureCount', { count: failures.length })
        : resultFailed ? t('flow.failurePendingEvidence') : t('flow.noFailures'),
  };
  const flowComplete: Record<WorkspaceStage, boolean> = {
    requirement: Boolean(requirementAnalysis),
    cases: relatedCases.length > 0,
    automation: boundCaseCount > 0,
    result: Boolean(currentRun && !['QUEUED', 'RUNNING'].includes(currentRun.status))
      || Boolean(task && !runtimeActive(runtime.snapshot?.status ?? task.status)),
    failure: resultPassed && failures.length === 0,
  };
  const flowState = (item: WorkspaceStage) => {
    if ((item === 'requirement' && analysisFailed)
      || (item === 'result' && resultFailed)
      || (item === 'failure' && (resultFailed || failures.length > 0))) return 'failed';
    if (item === stage) return 'current';
    return flowComplete[item] ? 'complete' : 'pending';
  };
  const flowStateLabel = (item: WorkspaceStage) => t(`flow.state.${flowState(item)}`);

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

  const openStudio = (filePath?: string, lineNumber?: number) => {
    const href = buildStudioHref({
      ...context,
      projectId,
      testCaseId: selectedCase?.id ?? context.testCaseId,
      automationBindingId: binding?.id,
      file: filePath ?? context.file ?? binding?.file_path,
      lineNumber,
      nodeId: binding?.nodeid ?? context.nodeId,
      returnTo: 'workspace',
      stage: currentFailure ? 'failure' : stage,
    });
    navigate(href);
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
      stage: 'requirement',
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
    });
  };

  const setStage = (next: WorkspaceStage) => updateContext({ stage: next });

  const onRunStarted = (runId?: string) => {
    if (!runId) return;
    updateContext({ runId, taskId: undefined, failureId: undefined, parentRunId: undefined, stage: 'result' });
  };

  const onTaskStarted = (taskId: string) => {
    updateContext({ taskId, runId: undefined, parentRunId: undefined, failureId: undefined });
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

  const openWorkflow = (extra: Partial<WorkspaceContext> = {}) =>
    navigate(buildWorkflowHref({ ...context, projectId, ...extra }));

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
      updateContext({ taskId: created.id, runId: undefined, failureId: undefined, parentRunId: undefined, stage: 'result' });
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
          {completedGoalResult && <button type="button" className="btn btn-secondary btn-sm" onClick={() => updateContext({ taskId: undefined, runId: undefined, stage: 'requirement' })}>{t('goal.new')}</button>}
          {(context.taskId || context.runId) && <Link className="btn btn-secondary btn-sm" to={buildWorkflowHref({ ...context, projectId })}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</Link>}
        </div>
      </header>

      {projectId && <nav className="workspace-stage-nav" aria-label={t('flow.board')}>
        {stages.map((item, index) => {
          const disabled = item === 'failure' && !currentFailure && !failures.length && !resultFailed && stage !== 'failure';
          const state = flowState(item);
          return <button
            key={item}
            type="button"
            className={`workspace-flow-node is-${state}${stage === item ? ' is-current' : ''}`}
            aria-current={stage === item ? 'step' : undefined}
            aria-label={`${t(`stage.${item}`)} · ${flowSummaries[item]} · ${flowStateLabel(item)}`}
            disabled={disabled}
            onClick={() => setStage(item)}
          >
            <span className="workspace-flow-number">{index + 1}</span>
            <span className="workspace-flow-label"><strong>{t(`stage.${item}`)}</strong><small>{flowSummaries[item]}</small></span>
            <small className="workspace-flow-state">{flowStateLabel(item)}</small>
          </button>;
        })}
      </nav>}

      {loadError && <div className="workspace-error" role="alert"><span>{loadError}</span><button type="button" className="btn btn-secondary btn-sm" onClick={() => setLoadAttempt((value) => value + 1)}>{t('retry')}</button></div>}
      {!projectId ? (
        <section className="workspace-empty">
          <h2>{t('noProjectTitle')}</h2>
          <p>{t('noProjectDescription')}</p>
          <Link className="btn btn-primary" to="/projects">{t('openProjects')}</Link>
        </section>
      ) : (
        <div className={`workspace-grid${stage === 'failure' ? ' is-failure-stage' : ''}`}>
          <aside className="workspace-context-panel" aria-label={t('context.title')}>
            <div className="workspace-panel-heading"><h2>{t('context.title')}</h2><small>{project?.name ?? projectId}</small></div>
            <section className="workspace-context-group">
              <div className="workspace-group-heading"><h3>{t('context.requirements')}</h3><Link to={`/projects/${projectId}/requirements`} aria-label={t('context.manageRequirements')} title={t('context.manageRequirements')}><ArrowUpRight size={14} aria-hidden="true" /></Link></div>
              <div className="workspace-context-list">
                {requirements.slice(0, 12).map((item) => <button key={item.id} type="button" className={item.id === context.requirementId ? 'is-selected' : ''} aria-pressed={item.id === context.requirementId} onClick={() => selectRequirement(item.id)}>
                  <span>{item.qa_model?.display_id ?? item.id.slice(-6)}</span><strong>{item.title}</strong>
                </button>)}
                {!contextDataLoaded ? <p className="workspace-muted">{contextLoading ? t('context.loading') : t('context.unavailable')}</p> : !requirements.length && <><p className="workspace-muted">{t('context.noRequirements')}</p>{projects.length > 1 && <Link className="btn btn-secondary btn-sm" to="/projects">{t('context.chooseProject')}</Link>}</>}
              </div>
            </section>
            <section className="workspace-context-group">
              <div className="workspace-group-heading"><h3>{t('context.cases')}</h3><Link to={`/projects/${projectId}/test-cases`} aria-label={t('context.manageCases')} title={t('context.manageCases')}><Plus size={14} aria-hidden="true" /></Link></div>
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
            <section className="workspace-context-group">
              <div className="workspace-group-heading"><h3>{t('context.recentRuns')}</h3><Link to="/runs" aria-label={t('context.runHistory')} title={t('context.runHistory')}><ArrowUpRight size={14} aria-hidden="true" /></Link></div>
              <div className="workspace-context-list workspace-run-list">
                {runs.slice(0, 5).map((item) => <button key={item.id} type="button" className={item.id === context.runId ? 'is-selected' : ''} aria-pressed={item.id === context.runId} onClick={() => updateContext({ runId: item.id, taskId: undefined, parentRunId: undefined, failureId: undefined, stage: 'result' })}>
                  <span className={`workspace-status-mark is-${item.status.toLowerCase()}`} aria-hidden="true" />
                  <strong>{item.requested_by || item.id.slice(0, 8)}</strong><small>{item.status} · {item.passed}/{item.total || '—'}</small>
                </button>)}
                {!contextDataLoaded ? <p className="workspace-muted">{contextLoading ? t('context.loading') : t('context.unavailable')}</p> : !runs.length && <p className="workspace-muted">{t('context.noRuns')}</p>}
              </div>
            </section>
            <section className="workspace-context-group">
              <div className="workspace-group-heading"><h3>{t('context.files')}</h3><Link to={`/projects/${projectId}/studio`} aria-label={t('context.openStudio')} title={t('context.openStudio')}><ArrowUpRight size={14} aria-hidden="true" /></Link></div>
              <div className="workspace-context-list workspace-file-list">
                {flatFiles.map((item) => <button key={item.path} type="button" onClick={() => openStudio(item.path)}><FileCode2 size={13} aria-hidden="true" /><span>{item.path}</span></button>)}
                {!contextDataLoaded ? <p className="workspace-muted">{contextLoading ? t('context.loading') : t('context.unavailable')}</p> : !flatFiles.length && <p className="workspace-muted">{t('context.noFiles')}</p>}
              </div>
            </section>
          </aside>

          <section className="workspace-main-panel" aria-label={t('main.title')}>
            <div className="workspace-main-heading">
              <div><span className="workspace-eyebrow">{t('main.currentStage')}</span><h2>{t(`stage.${stage}`)}</h2></div>
              {stage === 'automation' && selectedCase?.binding && <button type="button" className="btn btn-primary btn-sm" onClick={() => openStudio(selectedCase.binding!.file_path)}><FileCode2 size={14} aria-hidden="true" />{t('main.openCode')}</button>}
              {stage === 'cases' && <Link className="btn btn-secondary btn-sm" to={`/projects/${projectId}/test-cases`}><Plus size={14} aria-hidden="true" />{t('main.manageCases')}</Link>}
            </div>
            <div className="workspace-main-scroll">
              {!completedGoalResult && <section className="workspace-goal-surface" aria-label={t('goal.title')}>
                <div className="workspace-goal-heading">
                  <div><Sparkles size={16} aria-hidden="true" /><div><strong>{t('goal.title')}</strong><small>{selectedRequirement?.qa_model?.display_id ?? selectedCase?.title ?? currentFailure?.test_name ?? project?.name ?? t('goal.projectContext')}</small></div></div>
                  {task?.type === 'QA_GOAL' && <span className={`workspace-status-badge is-${(runtime.snapshot?.status ?? task.status).toLowerCase()}`}>{t(`result.taskStatus.${runtime.snapshot?.status ?? task.status}`, { defaultValue: runtime.snapshot?.status ?? task.status })}</span>}
                </div>
                {task?.type === 'QA_GOAL' && runtimeActive(runtime.snapshot?.status ?? task.status) ? (
                  <div className="workspace-goal-active">
                    <strong>{task.goal}</strong>
                    <p>{t('goal.progress', {
                      completed: (runtime.snapshot?.steps ?? task.steps ?? task.plan).filter((item) => item.status === 'COMPLETED' || item.status === 'SKIPPED').length,
                      total: (runtime.snapshot?.steps ?? task.steps ?? task.plan).length,
                      current: runtime.snapshot?.steps.find((item) => item.status === 'RUNNING')?.title
                        ?? task.steps?.find((item) => item.status === 'RUNNING' || item.status === 'WAITING_FOR_APPROVAL')?.name
                        ?? t('goal.waiting'),
                    })}</p>
                    {runtime.snapshot?.kind === 'task' && <RuntimeTaskActions
                      snapshot={runtime.snapshot}
                      onChanged={runtime.refresh}
                      onInspect={(stepId) => openWorkflow({ taskId: task.id, stepId })}
                      onOpenStudio={() => openStudio(binding?.file_path)}
                    />}
                  </div>
                ) : (
                  <>
                    <label className="workspace-goal-input-label" htmlFor="workspace-qa-goal">{t('goal.promptLabel')}</label>
                    <textarea
                      id="workspace-qa-goal"
                      value={goalText}
                      onChange={(event) => editGoal(event.target.value)}
                      rows={2}
                      maxLength={4000}
                      placeholder={t('goal.placeholder')}
                      disabled={!contextDataLoaded || goalBusy}
                    />
                    <div className="workspace-goal-actions">
                      <div className="workspace-goal-quick">
                        {context.requirementId && <button type="button" disabled={goalBusy} onClick={() => editGoal('只检查覆盖，不要生成代码')}>{t('goal.quickCoverage')}</button>}
                        {context.requirementId && <button type="button" disabled={goalBusy} onClick={() => editGoal('帮我把这个需求测试完整。可以自动完成低风险步骤；需要修改代码时让我确认。')}>{t('goal.quickComplete')}</button>}
                        {context.failureId && <button type="button" disabled={goalBusy} onClick={() => editGoal('只分析，不要修改')}>{t('goal.quickAnalyze')}</button>}
                      </div>
                      <button type="button" className="btn btn-primary btn-sm" disabled={!contextDataLoaded || goalBusy || !goalText.trim()} onClick={() => void previewGoal()}>
                        {goalBusy ? t('goal.planning') : t('goal.preview')} <ArrowRight size={14} aria-hidden="true" />
                      </button>
                    </div>
                    {goalPreview && goalPreviewKey === goalRequestKey && <div className="workspace-goal-preview">
                      <div className="workspace-goal-preview-heading"><strong>{t('goal.planTitle')}</strong><span>{goalPreview.context}</span></div>
                      <ol>{goalPreview.steps.map((step, index) => <li key={`${step.title}-${index}`}>
                        <span>{index + 1}</span><strong>{step.title}</strong>
                        {step.conditional && <small>{t('goal.conditional')}</small>}
                        <em className={`is-${step.risk.toLowerCase()}`}>{t(`goal.risk.${step.risk.toLowerCase()}`)}</em>
                      </li>)}</ol>
                      {goalPreview.effects.length > 0 && <p><b>{t('goal.effects')}</b> {goalPreview.effects.join(' · ')}</p>}
                      {goalPreview.constraints.length > 0 && <p><b>{t('goal.constraints')}</b> {goalPreview.constraints.join(' · ')}</p>}
                      {goalPreview.approval_required && <p className="workspace-goal-approval">{t('goal.approvalNotice')}</p>}
                      <button type="button" className="btn btn-primary btn-sm" disabled={goalBusy || Boolean(task?.type === 'QA_GOAL' && runtimeActive(task.status))} onClick={() => void startGoal()}>
                        {goalBusy ? t('goal.starting') : t('goal.start')} <ArrowRight size={14} aria-hidden="true" />
                      </button>
                    </div>}
                    {goalError && <p className="workspace-goal-error" role="alert">{goalError}</p>}
                  </>
                )}
              </section>}
              {stage === 'requirement' && <RequirementsPage
                projects={projects}
                selectedProjectId={projectId}
                initialRequirementId={context.requirementId}
                onSelectRequirement={selectRequirement}
                onStartAnalysis={startRequirementAnalysis}
                analysisRunning={analysisRunning}
                analysisRefreshVersion={isAnalysisTask ? runtime.snapshot?.event_cursor : null}
                onRequirementChanged={handleRequirementChanged}
                onCaseCreated={(id, testDesignId) => {
                  updateContext({
                    testCaseId: id,
                    testDesignId,
                    automationBindingId: undefined,
                    taskId: undefined,
                    runId: undefined,
                    parentRunId: undefined,
                    failureId: undefined,
                    browserSessionId: undefined,
                    file: undefined,
                    lineNumber: undefined,
                    nodeId: undefined,
                    stepId: undefined,
                    stage: 'cases',
                  });
                  void api.getTestCases(projectId).then(setCases).catch(() => undefined);
                }}
                workspaceMode
              />}
              {(stage === 'cases' || stage === 'automation') && selectedCase && <TestCasesPage
                projects={projects}
                selectedProjectId={projectId}
                initialTestCaseId={context.testCaseId}
                onSelectTestCase={(id) => updateContext({ testCaseId: id })}
                onNavigateToStudio={(filePath) => openStudio(filePath)}
                onNavigateToRuns={onRunStarted}
                onTaskStarted={onTaskStarted}
                workspaceMode
                focusAutomation={stage === 'automation'}
              />}
              {(stage === 'cases' || stage === 'automation') && !selectedCase && <section className="workspace-empty workspace-no-case">
                <h3>{t('main.noCaseTitle')}</h3>
                <p>{t('main.noCaseDescription')}</p>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setStage('requirement')}>{t('main.backToRequirement')}</button>
              </section>}
              {stage === 'result' && <RunResultSurface
                context={context}
                run={currentRun}
                task={task}
                projectId={projectId}
                onOpenFailure={(failureId) => updateContext({ failureId, stage: 'failure' })}
                onOpenCode={(filePath) => openStudio(filePath)}
                onOpenWorkflow={() => openWorkflow()}
              />}
              {stage === 'failure' && <FailuresPage
                projects={projects}
                selectedProjectId={projectId}
                initialFailureId={context.failureId}
                onSelectFailure={(failureId) => updateContext({ failureId })}
                onOpenInStudio={(filePath, lineNumber, nodeId, failureContext) => navigate(buildStudioHref({
                  ...context,
                  projectId,
                  file: filePath,
                  lineNumber,
                  nodeId,
                  failureId: failureContext?.failureId,
                  runId: failureContext?.runId,
                  parentRunId: failureContext?.runId,
                  returnTo: 'workspace',
                  stage: 'failure',
                }))}
                onNavigateToRuns={(runId) => updateContext({
                  runId,
                  parentRunId: currentFailure?.run_id,
                  stage: 'failure',
                })}
                workspaceMode
              />}
            </div>
          </section>

          <aside className="workspace-inspector" aria-label={t('inspector.title')}>
            <div className="workspace-panel-heading"><h2>{t('inspector.title')}</h2><span className="workspace-live-label"><i aria-hidden="true" />{t('inspector.liveContext')}</span></div>
            {selectedRequirement ? <section className="workspace-inspector-section">
              <span>{t('inspector.requirement')}</span><strong>{selectedRequirement.qa_model?.display_id ?? selectedRequirement.title}</strong>
              <p>{requirementAnalysis?.summary ?? t('inspector.pending')}</p>
              <div className="workspace-inspector-fact"><span>{t('inspector.businessRules')}</span><strong>{selectedRequirement.qa_model?.rules.length ?? t('inspector.pending')}</strong></div>
              <div className="workspace-inspector-fact"><span>{t('inspector.risks')}</span><strong>{requirementAnalysis?.risks.length ?? t('inspector.pending')}</strong></div>
              <div className="workspace-inspector-fact"><span>{t('inspector.ambiguities')}</span><strong>{requirementAnalysis?.ambiguities.length ?? t('inspector.pending')}</strong></div>
              <div className="workspace-inspector-fact"><span>{t('inspector.coverageGaps')}</span><strong>{requirementAnalysis?.coverage_gaps.length ?? t('inspector.pending')}</strong></div>
              <div className="workspace-inspector-fact"><span>{t('inspector.evidence')}</span><strong>{analysisEvidence ? t('inspector.evidenceAvailable') : t('inspector.pending')}</strong></div>
              {analysisEvidence && <p>{analysisEvidence.summary}</p>}
              <div className="workspace-inspector-fact"><span>{t('inspector.latestFinding')}</span><strong>{analysisProgressEvent?.title ?? latestAnalysisStage?.title ?? t('inspector.pending')}</strong></div>
              <p>{analysisRunning
                ? analysisProgressEvent?.summary ?? latestAnalysisStage?.summary ?? t('inspector.pending')
                : analysisFailed
                  ? t('inspector.analysisFailed')
                  : analysisProgressEvent?.summary ?? latestAnalysisStage?.summary ?? t('inspector.pending')}</p>
              <div className="workspace-inspector-fact"><span>{t('inspector.recommendedNextAction')}</span><strong>{analysisRunning
                ? t('inspector.analysisRunning')
                : analysisFailed
                  ? t('inspector.retryAnalysisNext')
                : !requirementAnalysis
                  ? t('inspector.analyzeNext')
                  : !selectedCase
                    ? t('inspector.designNext')
                    : !binding
                      ? t('inspector.automationNext')
                      : !currentRun
                        ? t('inspector.runNext')
                        : currentFailure
                          ? t('inspector.failureNext')
                          : t('inspector.verifyNext')}</strong></div>
              {requirementAnalysis?.risks.slice(0, 3).map((risk) => <div className="workspace-risk" key={risk.id}><b>{risk.severity}</b><span>{risk.title}</span></div>)}
            </section> : <p className="workspace-muted">{t('inspector.chooseRequirement')}</p>}
            {selectedCase && <section className="workspace-inspector-section">
              <span>{t('inspector.case')}</span><strong>{selectedCase.test_model?.display_id ?? selectedCase.title}</strong>
              <p>{selectedCase.expected_result || t('inspector.noExpectedResult')}</p>
              <div className="workspace-inspector-fact"><span>{t('inspector.automation')}</span><strong>{binding?.status ?? t('inspector.unbound')}</strong></div>
              {binding && <button type="button" className="btn btn-secondary btn-sm" onClick={() => openStudio(binding.file_path)}><FileCode2 size={13} aria-hidden="true" />{t('inspector.openStudio')}</button>}
            </section>}
            {currentRun && <section className="workspace-inspector-section">
              <span>{t('inspector.run')}</span><strong>{currentRun.status}</strong>
              <p>{currentRun.passed} / {currentRun.total || '—'} {t('runtime.tests')}</p>
              {currentFailure && <button type="button" className="btn btn-secondary btn-sm" onClick={() => updateContext({ failureId: currentFailure.id, stage: 'failure' })}>{t('inspector.resolveFailure')}</button>}
            </section>}
            {task && <section className="workspace-inspector-section">
              <span>{t('inspector.task')}</span><strong>{runtime.snapshot?.id === task.id ? runtime.snapshot.status : task.status}</strong><p>{task.goal}</p>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => openWorkflow({ taskId: task.id })}><Workflow size={13} aria-hidden="true" />{t('openWorkflow')}</button>
            </section>}
            {!selectedCase && <p className="workspace-inspector-hint">{t('inspector.nextActionHint')}</p>}
          </aside>
        </div>
      )}

      {runtimeId && runtime.snapshot && <RuntimeMiniBar context={context} projectId={projectId} snapshot={runtime.snapshot} />}
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
  onOpenWorkflow,
}: {
  context: WorkspaceContext;
  run: TestRun | null;
  task: AgentTask | null;
  projectId: string;
  onOpenFailure: (failureId: string) => void;
  onOpenCode: (filePath: string) => void;
  onOpenWorkflow: () => void;
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
      <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${task.status.toLowerCase()}`}>{t('result.executionStatus', { status: t(`result.taskStatus.${task.status}`, { defaultValue: task.status }) })}</span><span className={`workspace-status-badge is-${(goalSummary.status ?? task.status).toLowerCase()}`}>{t(`result.status.${goalSummary.status ?? task.status}`, { defaultValue: t(`result.taskStatus.${goalSummary.status ?? task.status}`, { defaultValue: goalSummary.status ?? task.status }) })}</span><h3>{task.goal}</h3><code>{task.id}</code></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenWorkflow}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
      <div className="workspace-goal-result">
        {goalSummary.tests && goalSummary.runs?.length ? <dl className="workspace-result-metrics"><div><dt>{t('result.total')}</dt><dd>{goalSummary.tests.total ?? 0}</dd></div><div><dt>{t('result.passed')}</dt><dd>{goalSummary.tests.passed ?? 0}</dd></div><div><dt>{t('result.failed')}</dt><dd>{goalSummary.tests.failed ?? 0}</dd></div><div><dt>{t('result.skipped')}</dt><dd>{goalSummary.tests.skipped ?? 0}</dd></div></dl> : <p className="workspace-muted">{t('result.testsNotRun')}</p>}
        {goalSummary.work_completed?.length ? <section><h4>{t('result.workCompleted')}</h4><ul>{goalSummary.work_completed.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></section> : null}
        {goalSummary.findings?.length ? <section><h4>{t('result.findings')}</h4><ul>{goalSummary.findings.map((item, index) => <li key={index}>{summaryText(item)}</li>)}</ul></section> : null}
        {goalSummary.changes?.length ? <section><h4>{t('result.changes')}</h4><div className="workspace-goal-links">{goalSummary.changes.map((item, index) => item.file_path
          ? <button type="button" key={`${item.file_path}-${index}`} onClick={() => onOpenCode(item.file_path!)}>{item.file_path}</button>
          : <span key={index}>{item.kind}</span>)}</div></section> : null}
        <section><h4>{t('result.evidence')}</h4><div className="workspace-goal-links">
          {(goalSummary.runs ?? []).map((id) => <Link key={id} to={`/runs/${encodeURIComponent(id)}`}>{t('result.viewRun')} · {id.slice(0, 8)}</Link>)}
          {(goalSummary.cases ?? []).map((id) => <Link key={id} to={`/projects/${encodeURIComponent(projectId)}/test-cases/${encodeURIComponent(id)}`}>{t('result.viewCase')} · {id.slice(0, 8)}</Link>)}
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
      <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${task.status.toLowerCase()}`}>{t(`result.taskStatus.${task.status}`, { defaultValue: task.status })}</span><h3>{task.goal}</h3><code>{task.id}</code></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenWorkflow}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
      {task.failure_reason && <p role="status">{task.failure_reason}</p>}
      <details className="workspace-goal-activity" open><summary>{t('result.stepActivity')} · {steps.length}</summary><ol className="workspace-step-list">{steps.map((item) => <li key={item.id}><span>{item.status}</span><strong>{item.name}</strong>{item.error && <small>{item.error}</small>}</li>)}</ol></details>
    </section>;
    return <section className="workspace-result-card">
      <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${task.status.toLowerCase()}`}>{t(`result.taskStatus.${task.status}`, { defaultValue: task.status })}</span><h3>{task.goal}</h3></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenWorkflow}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
      <p>{t('result.taskSummary', { completed: steps.filter((item) => item.status === 'COMPLETED').length, total: steps.length })}</p>
      <ol className="workspace-step-list">{steps.map((item) => <li key={item.id} className={`is-${item.status.toLowerCase()}`}><span>{item.status}</span><strong>{item.name}</strong><small>{item.error ?? (Object.keys(item.outputs).length ? JSON.stringify(item.outputs) : '')}</small></li>)}</ol>
    </section>;
  }
  if (!run) return <section className="workspace-result-card workspace-empty"><Play size={20} aria-hidden="true" /><h3>{t('result.noRun')}</h3><p>{t('result.noRunDescription')}</p></section>;

  return <section className="workspace-result-card">
    <div className="workspace-result-heading"><div><span className={`workspace-status-badge is-${run.status.toLowerCase()}`}>{run.status}</span><h3>{run.requested_by || t('result.runTitle')}</h3><code>{run.id}</code></div><button type="button" className="btn btn-secondary btn-sm" onClick={onOpenWorkflow}><Workflow size={14} aria-hidden="true" />{t('openWorkflow')}</button></div>
    <dl className="workspace-result-metrics"><div><dt>{t('result.total')}</dt><dd>{run.total || '—'}</dd></div><div><dt>{t('result.passed')}</dt><dd>{run.passed}</dd></div><div><dt>{t('result.failed')}</dt><dd>{run.failed}</dd></div><div><dt>{t('result.duration')}</dt><dd>{run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)} s` : '—'}</dd></div></dl>
    {failures.length > 0 && <section className="workspace-failure-list"><h4>{t('result.failures')}</h4>{failures.map((failure) => <button key={failure.id} type="button" onClick={() => onOpenFailure(failure.id)}><span className="workspace-status-mark is-failed" aria-hidden="true" /><span><strong>{failure.test_name || failure.test_nodeid}</strong><small>{failure.classification} · {failure.error_message}</small></span><ArrowUpRight size={14} aria-hidden="true" /></button>)}</section>}
    {run.executions.length > 0 && <ol className="workspace-execution-list">{run.executions.map((execution) => <li key={execution.id}><span className={`workspace-status-mark is-${execution.status.toLowerCase()}`} aria-hidden="true" /><strong>{execution.nodeid}</strong><span>{execution.status}</span><small>{execution.duration_ms ? `${(execution.duration_ms / 1000).toFixed(2)} s` : '—'}</small></li>)}</ol>}
    {!failures.length && ['FAILED', 'ERROR'].includes(run.status) && <p className="workspace-muted">{t('result.failureLoading')}</p>}
    {context.testCaseId && <Link className="workspace-result-back" to={`/projects/${projectId}/test-cases/${context.testCaseId}`}>{t('result.openCase')}</Link>}
  </section>;
}
