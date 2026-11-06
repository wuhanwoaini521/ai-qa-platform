import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import { AgentTask, DashboardStats, Project, TestExecution, TestRun } from '../types';
import {
  FolderGit2,
  FileText,
  CheckSquare,
  PlayCircle,
  Activity,
  AlertTriangle,
  ArrowRight,
  Flame,
  RotateCcw,
  Clock,
  Sparkles,
  Workflow,
  Wrench,
  ClipboardCheck,
  ListChecks,
  Inbox,
} from 'lucide-react';
import { NavTab } from '../components/Navigation';
import { TrendChart } from '../components/TrendChart';
import { EmptyState } from '../components/AsyncState';
import { isExecutableTestCase, isUnfinishedTask } from './dashboardModel';

interface DashboardPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  projectLoading: boolean;
  projectError: string | null;
  onNavigate: (tab: NavTab, projectId?: string | null) => void;
  onOpenTask?: (task: AgentTask) => void;
  onOpenRun?: (runId: string) => void;
  onOpenExecution?: (run: TestRun, execution: TestExecution) => void;
  onOpenRunnableTest?: (testCaseId: string) => void;
  onOpenCreateProject?: () => void;
}

const RUN_STATUS_TONE: Record<string, string> = {
  PASSED: 'is-passed',
  FAILED: 'is-failed',
  RUNNING: 'is-running',
  QUEUED: 'is-queued',
  PENDING: 'is-queued',
  CANCELLED: 'is-draft',
  ERROR: 'is-failed',
};

const DASHBOARD_RECENT_TASK_LIMIT = 3;

export const DashboardPage: React.FC<DashboardPageProps> = ({
  projects,
  selectedProjectId,
  projectLoading,
  projectError,
  onNavigate,
  onOpenTask,
  onOpenRun,
  onOpenExecution,
  onOpenRunnableTest,
  onOpenCreateProject,
}) => {
  const { t } = useTranslation('dashboard');
  const { t: taskT } = useTranslation('tasks');
  const { t: commonT } = useTranslation('common');
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentTasks, setRecentTasks] = useState<AgentTask[]>([]);
  const [recentRuns, setRecentRuns] = useState<TestRun[]>([]);
  const [runnableCaseId, setRunnableCaseId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [statsUnavailable, setStatsUnavailable] = useState(false);
  const [tasksUnavailable, setTasksUnavailable] = useState(false);
  const [runsUnavailable, setRunsUnavailable] = useState(false);
  const [testCasesUnavailable, setTestCasesUnavailable] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);
  const sourcesUnavailable = tasksUnavailable || runsUnavailable;
  const currentProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const latestRun = currentProject
    ? recentRuns.find((run) => run.project_id === currentProject.id) ?? null
    : recentRuns[0] ?? null;
  const focusProject = currentProject
    ?? projects.find((project) => project.id === latestRun?.project_id)
    ?? null;
  const journeyRun = latestRun;
  const journeyIsFixture = journeyRun?.id.toLowerCase().includes('fixture') ?? false;
  const journeyExecutions = journeyRun?.executions.slice(0, 6) ?? [];
  const canCreateFirstProject = projects.length === 0 && !projectLoading && !projectError && Boolean(onOpenCreateProject);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setRecentTasks([]);
    setRecentRuns([]);
    setRunnableCaseId(null);
    void Promise.allSettled([
      api.getDashboardStats(),
      api.getTasks(selectedProjectId ?? undefined),
      api.getTestRuns(selectedProjectId ?? undefined, 20),
      selectedProjectId ? api.getTestCases(selectedProjectId) : Promise.resolve([]),
    ]).then(([dashboard, tasks, runs, testCases]) => {
      if (!current) return;
      if (dashboard.status === 'fulfilled') {
        setStats(dashboard.value);
        setStatsUnavailable(false);
      } else {
        setStats(null);
        setStatsUnavailable(true);
      }
      if (tasks.status === 'fulfilled') {
        setRecentTasks(tasks.value);
        setTasksUnavailable(false);
      } else {
        setRecentTasks([]);
        setTasksUnavailable(true);
      }
      if (runs.status === 'fulfilled') {
        setRecentRuns(runs.value);
        setRunsUnavailable(false);
      } else {
        setRecentRuns([]);
        setRunsUnavailable(true);
      }
      if (testCases.status === 'fulfilled') {
        setRunnableCaseId(testCases.value.find(isExecutableTestCase)?.id ?? null);
        setTestCasesUnavailable(false);
      } else {
        setRunnableCaseId(null);
        setTestCasesUnavailable(true);
      }
      setLoading(false);
    });
    return () => { current = false; };
  }, [reloadVersion, selectedProjectId]);

  if (loading && !stats && !sourcesUnavailable) {
    return (
      <div className="page-container" aria-busy="true">
        <div className="stats-grid">
          {[0, 1, 2, 3].map((key) => (
            <div key={key} className="skeleton skeleton-block" />
          ))}
        </div>
        <div className="skeleton skeleton-block" />
      </div>
    );
  }

  const unfinishedTasks = recentTasks.filter(isUnfinishedTask);
  const trendPoints = [...recentRuns]
    .filter((run) => run.passed + run.failed > 0)
    .reverse()
    .slice(-16)
    .map((run) => {
      const total = run.passed + run.failed;
      return {
        label: new Date(run.created_at).toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        }),
        value: Math.round((run.passed / total) * 1000) / 10,
      };
    });

  const quickEntries = [
    { tab: 'recorder', label: taskT('entryRecorder'), Icon: Sparkles },
    { tab: 'failures', label: taskT('entryFailures'), Icon: Wrench },
    { tab: 'test_cases', label: taskT('entryTests'), Icon: ClipboardCheck },
    { tab: 'runs', label: taskT('entryRuns'), Icon: PlayCircle },
  ] as const;
  const lifecycle = [
    { tab: 'requirements', label: t('requirementStep'), meta: t('requirementStepDescription'), Icon: Sparkles },
    { tab: 'automation', label: t('automationStep'), meta: t('automationStepDescription'), Icon: PlayCircle },
    { tab: 'flaky', label: t('flakyStep'), meta: t('flakyStepDescription'), Icon: Flame },
    { tab: 'failures', label: t('failureStep'), meta: t('failureStepDescription'), Icon: AlertTriangle },
  ] as const;
  const workflowGroups = [
    {
      key: 'workflowBuild',
      title: t('workflowBuild'),
      items: [lifecycle[0], quickEntries[2], lifecycle[1], quickEntries[0]],
    },
    {
      key: 'workflowReview',
      title: t('workflowReview'),
      items: [quickEntries[3], lifecycle[2], lifecycle[3]],
    },
  ];
  const countValue = (value: number | undefined) => statsUnavailable ? '—' : value ?? 0;
  const visibleRecentTasks = unfinishedTasks.slice(0, DASHBOARD_RECENT_TASK_LIMIT);
  const attentionItems = [
    ...recentRuns
      .filter((run) => run.status === 'FAILED' || run.status === 'ERROR')
      .slice(0, 3)
      .map((run) => ({
        key: `run:${run.id}`,
        title: t('attentionRun'),
        detail: `#${run.id.slice(0, 8)} · ${run.failed} ${t('attentionFailedTests')}`,
        status: run.status,
        Icon: AlertTriangle,
        onClick: () => { if (onOpenRun) onOpenRun(run.id); else onNavigate('runs', selectedProjectId); },
      })),
    ...recentTasks
      .filter((task) => ['BLOCKED', 'FAILED'].includes(task.status))
      .slice(0, 3)
      .map((task) => ({
        key: `task:${task.id}`,
        title: taskT(`type_${task.type}`),
        detail: task.failure_reason || task.goal,
        status: task.status,
        Icon: Workflow,
        onClick: () => onOpenTask?.(task),
      })),
  ].slice(0, 4);
  // The overview drives one obvious next action instead of presenting equal-weight buttons.
  const nextStep = attentionItems[0]
    ? {
        label: t('nextResolveIssue', { count: attentionItems.length }),
        detail: attentionItems[0].detail,
        onClick: attentionItems[0].onClick,
      }
    : focusProject
      ? { label: t('openWorkspace'), detail: '', onClick: () => onNavigate('workspace', focusProject.id) }
      : null;
  const dashboardSignals = [
    {
      label: t('passRateToday'),
      value: !statsUnavailable && stats?.pass_rate_today != null ? `${stats.pass_rate_today.toFixed(1)}%` : '—',
      detailLabel: t('testsExecutedToday'),
      detailValue: countValue(stats?.tests_executed_today),
      Icon: Activity,
      tone: 'is-green',
    },
    {
      label: t('runsToday'),
      value: countValue(stats?.runs_today),
      detailLabel: t('totalExecutions'),
      detailValue: countValue(stats?.total_runs),
      Icon: ListChecks,
      tone: 'dashboard-neutral',
    },
    {
      label: t('totalFailures'),
      value: countValue(stats?.total_failures),
      detailLabel: t('likelyFlakyTests'),
      detailValue: countValue(stats?.flaky_tests_count),
      Icon: AlertTriangle,
      tone: 'is-red',
    },
    {
      label: t('avgExecutionTime'),
      value: !statsUnavailable && stats?.average_test_duration_ms
        ? stats.average_test_duration_ms > 1000
          ? `${(stats.average_test_duration_ms / 1000).toFixed(1)}s`
          : `${Math.round(stats.average_test_duration_ms)}ms`
        : '—',
      detailLabel: t('rerunRecoveries'),
      detailValue: countValue(stats?.rerun_recovery_count),
      Icon: Clock,
      tone: 'dashboard-neutral',
    },
  ];

  return (
    <div className="dashboard-page">
      <header className="ds-card dashboard-heading">
        <div className="dashboard-heading-copy">
          <h2>{t('overviewTitle')}</h2>
          <p>{t('overviewSubtitle')}</p>
        </div>
        <div className="dashboard-project-summary">
          <span className="dashboard-project-summary-scope">{t('platformScope')}</span>
          <dl className="dashboard-project-scope" aria-label={t('projectOverview')}>
            {[
              { key: 'qaProjects', Icon: FolderGit2, value: countValue(stats?.total_projects) },
              { key: 'requirements', Icon: FileText, value: countValue(stats?.total_requirements) },
              { key: 'testCases', Icon: CheckSquare, value: countValue(stats?.total_test_cases) },
            ].map(({ key, Icon, value }) => (
              <div className="dashboard-scope-metric" key={key}>
                <dt><Icon size={14} aria-hidden="true" />{t(key)}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </header>

      <section className="ds-card dashboard-context-line" aria-labelledby="dashboard-continue-title">
        <div className="dashboard-continue-project">
          <span>{currentProject ? t('currentProject') : focusProject ? t('latestRunProject') : t('currentProject')}</span>
          <h3 id="dashboard-continue-title">
            {focusProject?.name ?? (projectLoading ? t('projectContextLoading') : projectError ? t('projectContextUnavailable') : t('noCurrentProject'))}
          </h3>
          {focusProject ? <small>{t('projectWorkspaceMeta', { framework: focusProject.framework_type, branch: focusProject.default_branch })}</small>
            : <p>{projectLoading ? t('projectContextLoadingDescription') : projectError ? t('projectContextUnavailableDescription') : projects.length ? t('selectProjectDescription') : t('firstProjectDescription')}</p>}
        </div>
        {nextStep ? (
          <div className="dashboard-next-step">
            <span>{t('nextStep')}</span>
            <button type="button" className="ds-btn-primary ds-btn btn btn-primary" onClick={nextStep.onClick}>
              <ArrowRight size={15} aria-hidden="true" />{nextStep.label}
            </button>
          </div>
        ) : focusProject ? (
          <button type="button" className="ds-btn-primary ds-btn btn btn-primary" onClick={() => onNavigate('workspace', focusProject.id)}>
            <FolderGit2 size={15} aria-hidden="true" />{t('openWorkspace')}
          </button>
        ) : (
          <button type="button" className="ds-btn-primary ds-btn btn btn-primary" disabled={projectLoading} onClick={() => canCreateFirstProject ? onOpenCreateProject?.() : onNavigate('projects')}>
            <FolderGit2 size={15} aria-hidden="true" />{canCreateFirstProject ? t('createFirstProject') : t('goToProjects')}
          </button>
        )}
      </section>

      <section className="ds-card dashboard-signals card" aria-label={t('executionSignals')}>
        <div className="dashboard-signals-heading">
          <h3>{t('executionSignals')}</h3>
          <span>{t('executionSignalsSubtitle')}</span>
        </div>
        <div className="dashboard-signals-grid">
          {dashboardSignals.map(({ label, value, detailLabel, detailValue, Icon, tone }) => (
            <div key={label} className="dashboard-signal">
              <span className="dashboard-signal-top">
                <span className={`stat-icon ${tone}`}><Icon size={16} strokeWidth={1.7} aria-hidden="true" /></span>
                <span className="dashboard-signal-label">{label}</span>
              </span>
              <strong className="dashboard-signal-value">{value}</strong>
              <span className="dashboard-signal-detail"><span>{detailLabel}</span><strong>{detailValue}</strong></span>
            </div>
          ))}
        </div>
      </section>

      <div className="dashboard-primary-grid dashboard-composite">
        <section className={`ds-card dashboard-trend${!loading && !runsUnavailable && trendPoints.length <= 1 ? ' is-ready-empty' : ''}`} aria-labelledby="dashboard-trend-title">
          <div className="card-header">
            <div>
              <h3 id="dashboard-trend-title" className="card-title">{t('executionTrend')}</h3>
              <p className="card-subtitle">{t('executionTrendSubtitle')}</p>
            </div>
          </div>
          <div className="card-body dashboard-trend-body">
            {trendPoints.length > 1 ? (
              <TrendChart points={trendPoints} ariaLabel={t('executionTrend')} format={(value) => `${value}%`} height={150} />
            ) : (
              <div className="chart-insufficient">
                <Activity size={16} strokeWidth={1.6} aria-hidden="true" />
                <span>{t('trendInsufficient')}</span>
              </div>
            )}
          </div>
        </section>

        <section className={`ds-card dashboard-attention${sourcesUnavailable ? ' is-unavailable' : ''}`} aria-labelledby="dashboard-attention-title">
          <div className="dashboard-attention-heading">
            <div>
              <h3 id="dashboard-attention-title">{t('needsAttention')}</h3>
              <p className="card-subtitle">{t(currentProject ? 'needsAttentionProjectSubtitle' : 'needsAttentionPlatformSubtitle')}</p>
            </div>
            <span className="dashboard-attention-count">
              {sourcesUnavailable && attentionItems.length === 0 ? '—' : attentionItems.length}
            </span>
          </div>
          {attentionItems.length > 0 ? (
            <div className="dashboard-attention-list">
              {attentionItems.map(({ key, title, detail, status, Icon, onClick }) => (
                <button type="button" className="ds-btn dashboard-attention-item" key={key} onClick={onClick}>
                  <span className="dashboard-attention-icon"><Icon size={15} aria-hidden="true" /></span>
                  <span className="dashboard-attention-copy"><strong>{title}</strong><small>{detail}</small></span>
                  <span className={`dashboard-attention-status is-${status.toLowerCase()}`}>
                    {t(`attentionStatuses.${status}`, { defaultValue: status })}
                  </span>
                  <ArrowRight size={14} aria-hidden="true" />
                </button>
              ))}
            </div>
          ) : (
            <div className="dashboard-attention-empty">
              <span className="status-dot is-live" aria-hidden="true" />
              {sourcesUnavailable ? t('attentionUnavailable') : t(currentProject ? 'noAttentionItems' : 'noAttentionItemsPlatform')}
            </div>
          )}
          {sourcesUnavailable && (
            <div className="dashboard-attention-warning" role="status">
              <span>{t('attentionPartialWarning')}</span>
              <button type="button" className="ds-btn ds-btn-sm btn btn-secondary btn-sm" disabled={loading} onClick={() => setReloadVersion((version) => version + 1)}>
                <RotateCcw size={12} aria-hidden="true" />{loading ? t('attentionRetrying') : t('attentionRetry')}
              </button>
            </div>
          )}
        </section>
      </div>

      <div className="dashboard-secondary-grid dashboard-composite">
        <section className={`ds-card dashboard-recent-runs${!loading && !runsUnavailable && recentRuns.length === 0 ? ' is-ready-empty' : ''}`} aria-labelledby="dashboard-recent-runs-title">
          <div className="card-header">
            <div>
              <h3 id="dashboard-recent-runs-title" className="card-title">{t('recentRuns')}</h3>
              <p className="card-subtitle">{t(currentProject ? 'recentRunsProjectSubtitle' : 'recentRunsPlatformSubtitle', { project: currentProject?.name })}</p>
            </div>
            <button type="button" className="ds-btn-ghost ds-btn-sm ds-btn btn btn-ghost btn-sm" onClick={() => onNavigate('runs', selectedProjectId)}>
              {t('viewAll')} <ArrowRight size={14} strokeWidth={1.7} />
            </button>
          </div>
          {journeyRun && <section className="dashboard-journey" aria-label={t('executionTrace')}>
            <div className="dashboard-journey-heading">
              <div><span>{t('executionTrace')} · {t('latestPersistedRun')}</span><code>{journeyRun.id}</code></div>
              <div className="dashboard-journey-run-meta">
                {journeyIsFixture && <span className="dashboard-run-provenance is-fixture">{t('fixtureNotLive')}</span>}
                <span className={`dashboard-journey-status is-${journeyRun.status.toLowerCase()}`}>{journeyRun.status}</span>
                <button type="button" className="ds-btn ds-btn-ghost ds-btn-sm dashboard-run-link mono" aria-label={t('openRun', { runId: journeyRun.id.slice(0, 8) })} onClick={() => onOpenRun ? onOpenRun(journeyRun.id) : onNavigate('runs', journeyRun.project_id)}>
                  {journeyRun.passed} / {journeyRun.failed}
                </button>
              </div>
            </div>
            {journeyExecutions.length ? <ol className="dashboard-journey-steps">
              {journeyExecutions.map((execution) => {
                const stepName = execution.nodeid.split('::').pop() || execution.nodeid;
                return <li key={execution.id} className={`is-${execution.status.toLowerCase()}`}>
                  <button type="button" aria-label={t('openExecutionEvidence', { runId: journeyRun.id, nodeId: stepName })} onClick={() => onOpenExecution ? onOpenExecution(journeyRun, execution) : onOpenRun?.(journeyRun.id)} className="ds-btn ds-btn-ghost">
                    <span className="dashboard-journey-marker" aria-hidden="true" />
                    <span className="dashboard-journey-copy"><strong>{stepName}</strong><small>{execution.nodeid}</small></span>
                    <code>{Math.round(execution.duration_ms)}ms</code>
                  </button>
                </li>;
              })}
            </ol> : <p className="dashboard-journey-empty">{t('noExecutionSteps')}</p>}
          </section>}
          {loading ? (
            <div className="chart-insufficient dashboard-loading-evidence" role="status"><Activity size={16} aria-hidden="true" />{t('loadingRuns')}</div>
          ) : recentRuns.length > 0 ? (
            <div className="table-responsive">
              <table className="ds-table data-table">
                <thead>
                  <tr>
                    <th>{commonT('status')}</th>
                    <th>{t('runId')}</th>
                    <th>{t('runner')}</th>
                    <th>{t('passedFailed')}</th>
                    <th>{commonT('duration')}</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.slice(0, 5).map((run) => (
                    <tr key={run.id}>
                      <td>
                        <span className="ds-tag ds-tag--neutral status-pill status-pill-plain">
                          <span className={`status-dot ${RUN_STATUS_TONE[run.status] ?? ''}`} />
                          {run.status}
                        </span>
                      </td>
                      <td><button type="button" className="ds-btn ds-btn-ghost ds-btn-sm dashboard-run-link mono" aria-label={t('openRun', { runId: run.id.slice(0, 8) })} onClick={() => onOpenRun ? onOpenRun(run.id) : onNavigate('runs', selectedProjectId)}>#{run.id.slice(0, 8)}</button></td>
                      <td className="text-secondary">{run.runner_type || 'LOCAL'}</td>
                      <td>
                        <span className="tone-passed">{run.passed}</span>
                        <span className="text-secondary"> / </span>
                        <span className="tone-failed">{run.failed}</span>
                      </td>
                      <td className="text-secondary">{(run.duration_ms / 1000).toFixed(2)}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              icon={<Inbox size={18} strokeWidth={1.7} />}
              title={t('recentRuns')}
              message={t(runsUnavailable ? 'recentRunsUnavailable' : 'noRecentRuns')}
            />
          )}
        </section>

        <div className="ds-card dashboard-support-lists">
          <section className="dashboard-workflow" aria-labelledby="dashboard-workflow-title">
            <div className="dashboard-workflow-heading">
              <div>
                <h3 id="dashboard-workflow-title">{t('workflowHeading')}</h3>
                <p className="card-subtitle">{t('lifecycleFlowSubtitle')}</p>
              </div>
            </div>
            <div className="dashboard-workflow-groups">
              {workflowGroups.map((group) => (
                <section className="dashboard-workflow-group" key={group.key} aria-label={group.title}>
                  <h4>{group.title}</h4>
                  <div className="dashboard-workflow-links">
                    {group.items.map((item) => (
                      <button key={item.tab} type="button" className="ds-btn ds-btn-ghost dashboard-workflow-link" onClick={() => onNavigate(item.tab, selectedProjectId)}>
                        <span className="link-row-icon"><item.Icon size={14} strokeWidth={1.7} aria-hidden="true" /></span>
                        <span className="link-row-title">{item.label}</span>
                        <ArrowRight size={13} aria-hidden="true" />
                      </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </section>
          {currentProject && <>
            <div className="dashboard-quick-start" aria-label={t('quickStart')}>
              <span className="dashboard-quick-start-label">{t('quickStart')}</span>
              <button type="button" onClick={() => onNavigate('discovery', currentProject.id)} className="ds-btn"><Sparkles size={14} aria-hidden="true" />{t('quickExplore')}</button>
              {runnableCaseId && <button type="button" onClick={() => onOpenRunnableTest ? onOpenRunnableTest(runnableCaseId) : onNavigate('workspace', currentProject.id)} className="ds-btn"><PlayCircle size={14} aria-hidden="true" />{t('quickRunnableTest')}</button>}
            </div>
            <div className="dashboard-resume-tasks">
              <div className="dashboard-resume-heading">
                <strong>{t('unfinishedTasks')}</strong>
                {visibleRecentTasks.length > 0 && <span>{visibleRecentTasks.length}</span>}
              </div>
              {tasksUnavailable ? <p className="dashboard-resume-empty">{t('recentTasksUnavailableMessage')}</p>
                : loading ? <p className="dashboard-resume-empty" role="status">{t('resumeTasksLoading')}</p>
                  : visibleRecentTasks.length > 0 ? <div className="dashboard-resume-list">
                    {visibleRecentTasks.map((task) => <button key={task.id} type="button" className="ds-btn dashboard-resume-task" onClick={() => onOpenTask?.(task)}>
                      <span><strong>{taskT(`type_${task.type}`)}</strong><small>{task.goal}</small>{task.id.toLowerCase().includes('fixture') && <small className="dashboard-run-provenance is-fixture">{t('fixtureNotLive')}</small>}</span>
                      <span className={`dashboard-attention-status is-${task.status.toLowerCase()}`}>{task.status}</span>
                      <ArrowRight size={13} aria-hidden="true" />
                    </button>)}
                  </div> : <p className="dashboard-resume-empty">{t('noUnfinishedTasks')}</p>}
              {testCasesUnavailable && <p className="dashboard-runnable-note" role="status">{t('runnableTestsUnavailable')}</p>}
            </div>
          </>}
        </div>
      </div>

      <section className="ds-card card dashboard-project-registry" aria-labelledby="dashboard-project-registry-title">
        <header className="dashboard-project-registry-heading">
          <div><h3 id="dashboard-project-registry-title">{t('projectRegistry')}</h3><span>{t('projectCount', { count: projects.length })}</span></div>
          <button type="button" className="ds-btn-ghost ds-btn-sm ds-btn btn btn-ghost btn-sm" onClick={() => onNavigate('projects')}>{t('viewAll')} <ArrowRight size={14} aria-hidden="true" /></button>
        </header>
        {projects.length ? <ul className="dashboard-project-registry-list">
          {projects.slice(0, 5).map((project) => <li key={project.id} className={project.id === selectedProjectId ? 'is-current' : ''}>
            <button type="button" aria-label={t('openProjectWorkspace', { project: project.name })} onClick={() => onNavigate('workspace', project.id)} className="ds-btn ds-btn-ghost">
              <span className="dashboard-project-mark"><FolderGit2 size={16} aria-hidden="true" /></span>
              <span className="dashboard-project-copy"><strong>{project.name}</strong><small>{project.framework_type} · {project.default_branch}</small></span>
              <span className="dashboard-project-action">{project.id === selectedProjectId ? t('currentProject') : t('openWorkspace')}</span>
              <ArrowRight size={14} aria-hidden="true" />
            </button>
          </li>)}
        </ul> : <p className="dashboard-project-registry-empty">{projectLoading ? t('projectContextLoading') : projectError ? t('projectContextUnavailableDescription') : t('firstProjectDescription')}</p>}
      </section>

      <footer className="dashboard-boundary-note">{t('qualityBoundary')}</footer>
    </div>
  );
};
