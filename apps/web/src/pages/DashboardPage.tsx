import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import { AgentTask, DashboardStats, TestRun } from '../types';
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

interface DashboardPageProps {
  onNavigate: (tab: NavTab) => void;
  onOpenTask?: (taskId: string) => void;
  onOpenRun?: (runId: string) => void;
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

const DASHBOARD_RECENT_TASK_LIMIT = 8;

export const DashboardPage: React.FC<DashboardPageProps> = ({
  onNavigate,
  onOpenTask,
  onOpenRun,
}) => {
  const { t } = useTranslation('dashboard');
  const { t: taskT } = useTranslation('tasks');
  const { t: commonT } = useTranslation('common');
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentTasks, setRecentTasks] = useState<AgentTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [statsUnavailable, setStatsUnavailable] = useState(false);
  const [tasksUnavailable, setTasksUnavailable] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);
  const sourcesUnavailable = statsUnavailable || tasksUnavailable;

  useEffect(() => {
    let current = true;
    setLoading(true);
    void Promise.allSettled([api.getDashboardStats(), api.getTasks()]).then(([dashboard, tasks]) => {
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
      setLoading(false);
    });
    return () => { current = false; };
  }, [reloadVersion]);

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

  const recentRuns: TestRun[] = stats?.recent_runs ?? [];
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
        onClick: () => { if (onOpenRun) onOpenRun(run.id); else onNavigate('runs'); },
      })),
    ...recentTasks
      .filter((task) => ['RUNNING', 'WAITING', 'VERIFYING', 'RETRYING', 'PAUSED', 'BLOCKED', 'FAILED'].includes(task.status))
      .slice(0, 3)
      .map((task) => ({
        key: `task:${task.id}`,
        title: taskT(`type_${task.type}`),
        detail: task.failure_reason || task.goal,
        status: task.status,
        Icon: Workflow,
        onClick: () => onOpenTask?.(task.id),
      })),
  ].slice(0, 4);
  const countValue = (value: number | undefined) => statsUnavailable ? '—' : value ?? 0;
  const visibleRecentTasks = recentTasks.slice(0, DASHBOARD_RECENT_TASK_LIMIT);

  return (
    <div className="dashboard-page">
      <section className="dashboard-attention card" aria-label={t('needsAttention')}>
        <div className="dashboard-attention-heading">
          <div><div className="card-title">{t('needsAttention')}</div><div className="card-subtitle">{t('needsAttentionSubtitle')}</div></div>
          <span className="dashboard-attention-count">{sourcesUnavailable && attentionItems.length === 0 ? '—' : attentionItems.length}</span>
        </div>
        {attentionItems.length > 0 ? <div className="dashboard-attention-list">
          {attentionItems.map(({ key, title, detail, status, Icon, onClick }) => <button type="button" className="dashboard-attention-item" key={key} onClick={onClick}>
            <span className="dashboard-attention-icon"><Icon size={15} aria-hidden="true" /></span>
            <span className="dashboard-attention-copy"><strong>{title}</strong><small>{detail}</small></span>
            <span className={`dashboard-attention-status is-${status.toLowerCase()}`}>{t(`attentionStatuses.${status}`, { defaultValue: status })}</span>
            <ArrowRight size={14} aria-hidden="true" />
          </button>)}
        </div> : <div className="dashboard-attention-empty"><span className="status-dot is-live" />{sourcesUnavailable ? t('attentionUnavailable') : t('noAttentionItems')}</div>}
        {sourcesUnavailable && <div className="dashboard-attention-warning" role="status"><span>{t('attentionPartialWarning')}</span><button type="button" className="btn btn-secondary btn-sm" disabled={loading} onClick={() => setReloadVersion((version) => version + 1)}><RotateCcw size={12} aria-hidden="true" />{loading ? t('attentionRetrying') : t('attentionRetry')}</button></div>}
      </section>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-card-body">
            <div className="stat-head">
              <span className="stat-icon is-blue"><Activity size={18} strokeWidth={1.7} /></span>
              <span className="stat-label">{t('passRateToday')}</span>
            </div>
            <span className="stat-value">
                {!statsUnavailable && stats?.pass_rate_today != null ? `${stats.pass_rate_today.toFixed(1)}%` : '—'}
              </span>
          </div>
          <div className="stat-metric">
            <span className="status-dot is-live" />
            <span>{t('testsExecutedToday')}</span>
            <span className="stat-metric-value">{countValue(stats?.tests_executed_today)}</span>
          </div>
          <button type="button" className="card-footer" onClick={() => onNavigate('runs')}>
            <span>{t('executionRecord')}</span>
            <ArrowRight size={15} strokeWidth={1.7} />
          </button>
        </div>

        <div className="stat-card">
          <div className="stat-card-body">
            <div className="stat-head">
              <span className="stat-icon is-green"><ListChecks size={18} strokeWidth={1.7} /></span>
              <span className="stat-label">{t('runsToday')}</span>
            </div>
            <span className="stat-value">{countValue(stats?.runs_today)}</span>
          </div>
          <div className="stat-metric">
            <span>{t('totalExecutions')}</span>
            <span className="stat-metric-value">{countValue(stats?.total_runs)}</span>
          </div>
          <button type="button" className="card-footer" onClick={() => onNavigate('runs')}>
            <span>{t('viewAll')}</span>
            <ArrowRight size={15} strokeWidth={1.7} />
          </button>
        </div>

        <div className="stat-card">
          <div className="stat-card-body">
            <div className="stat-head">
              <span className="stat-icon is-red"><AlertTriangle size={18} strokeWidth={1.7} /></span>
              <span className="stat-label">{t('totalFailures')}</span>
            </div>
            <span className="stat-value">{countValue(stats?.total_failures)}</span>
          </div>
          <div className="stat-metric">
            <span>{t('likelyFlakyTests')}</span>
            <span className="stat-metric-value">{countValue(stats?.flaky_tests_count)}</span>
          </div>
          <button type="button" className="card-footer" onClick={() => onNavigate('failures')}>
            <span>{t('failureStepShort')}</span>
            <ArrowRight size={15} strokeWidth={1.7} />
          </button>
        </div>

        <div className="stat-card">
          <div className="stat-card-body">
            <div className="stat-head">
              <span className="stat-icon is-violet"><Clock size={18} strokeWidth={1.7} /></span>
              <span className="stat-label">{t('avgExecutionTime')}</span>
            </div>
            <span className="stat-value">
                {!statsUnavailable && stats?.average_test_duration_ms
                  ? stats.average_test_duration_ms > 1000
                    ? `${(stats.average_test_duration_ms / 1000).toFixed(1)}s`
                    : `${stats.average_test_duration_ms}ms`
                  : '—'}
              </span>
          </div>
          <div className="stat-metric">
            <RotateCcw size={13} strokeWidth={1.7} />
            <span>{t('rerunRecoveries')}</span>
            <span className="stat-metric-value">{countValue(stats?.rerun_recovery_count)}</span>
          </div>
          <button type="button" className="card-footer" onClick={() => onNavigate('flaky')}>
            <span>{t('likelyFlakyTests')}</span>
            <ArrowRight size={15} strokeWidth={1.7} />
          </button>
        </div>
      </div>

      <section className="overview-strip" aria-label={t('projectOverview')}>
        <span className="overview-strip-title">{t('projectOverview')}</span>
        <dl className="overview-metrics">
          {[
            { key: 'qaProjects', Icon: FolderGit2, value: countValue(stats?.total_projects) },
            { key: 'requirements', Icon: FileText, value: countValue(stats?.total_requirements) },
            { key: 'testCases', Icon: CheckSquare, value: countValue(stats?.total_test_cases) },
            { key: 'totalExecutions', Icon: PlayCircle, value: countValue(stats?.total_runs) },
          ].map(({ key, Icon, value }) => (
            <div className="overview-metric" key={key}>
              <dt>
                <Icon size={15} strokeWidth={1.6} />
                {t(key)}
              </dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <div className="dashboard-split">
        <section className="card">
          <div className="card-header">
            <div>
              <div className="card-title">{t('executionTrend')}</div>
              <div className="card-subtitle">{t('executionTrendSubtitle')}</div>
            </div>
          </div>
          <div className="card-body">
            {trendPoints.length > 1 ? (
              <TrendChart
                points={trendPoints}
                ariaLabel={t('executionTrend')}
                format={(value) => `${value}%`}
              />
            ) : (
              <div className="chart-insufficient">
                <Activity size={16} strokeWidth={1.6} />
                <span>{t('trendInsufficient')}</span>
              </div>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-header">
            <div>
              <div className="card-title">{t('aiAssistance')}</div>
              <div className="card-subtitle">{taskT('dashboardDescription')}</div>
            </div>
          </div>
          <div className="link-rows link-rows--air">
            {quickEntries.map(({ tab, label, Icon }) => (
              <button key={tab} type="button" className="link-row" onClick={() => onNavigate(tab)}>
                <span className="link-row-icon"><Icon size={15} strokeWidth={1.6} /></span>
                <span className="link-row-copy">
                  <span className="link-row-title">{label}</span>
                </span>
                <ArrowRight size={15} strokeWidth={1.6} />
              </button>
            ))}
          </div>
        </section>
      </div>

      <div className="dashboard-split is-wide">
        <section className="card">
          <div className="card-header">
            <div className="card-title">{t('recentRuns')}</div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onNavigate('runs')}>
              {t('viewAll')} <ArrowRight size={14} strokeWidth={1.7} />
            </button>
          </div>
          {recentRuns.length > 0 ? (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{commonT('status')}</th>
                    <th>{t('runId')}</th>
                    <th>{t('runner')}</th>
                    <th>{commonT('total')}</th>
                    <th>{commonT('duration')}</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.map((run) => (
                    <tr
                      key={run.id}
                      className="clickable-row"
                      onClick={() => onNavigate('runs')}
                    >
                      <td>
                        <span className="status-pill status-pill-plain">
                          <span className={`status-dot ${RUN_STATUS_TONE[run.status] ?? ''}`} />
                          {run.status}
                        </span>
                      </td>
                      <td className="mono">#{run.id.slice(0, 8)}</td>
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
              message={t(statsUnavailable ? 'recentRunsUnavailable' : 'noRecentRuns')}
            />
          )}
        </section>

        <section className="card">
          <div className="card-header">
            <div>
              <div className="card-title">{t('lifecycleFlow')}</div>
              <div className="card-subtitle">{t('lifecycleFlowSubtitle')}</div>
            </div>
          </div>
          <div className="link-rows link-rows--air">
            {lifecycle.map(({ tab, label, meta, Icon }) => (
              <button key={tab} type="button" className="link-row" onClick={() => onNavigate(tab)}>
                <span className="link-row-icon"><Icon size={15} strokeWidth={1.6} /></span>
                <span className="link-row-copy">
                  <span className="link-row-title">{label}</span>
                  <span className="link-row-meta">{meta}</span>
                </span>
                <ArrowRight size={15} strokeWidth={1.6} />
              </button>
            ))}
          </div>
        </section>
      </div>

      <section className="card dashboard-recent-tasks">
        <div className="card-header">
          <div>
            <div className="card-title">{taskT('recentTasks')}</div>
            <div className="card-subtitle">{taskT('dashboardDescription')}</div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onNavigate('tasks')}>
            <Workflow size={14} strokeWidth={1.7} /> {taskT('allTasks')}
          </button>
        </div>
        {tasksUnavailable ? (
          <EmptyState
            icon={<Workflow size={18} strokeWidth={1.7} />}
            title={t('recentTasksUnavailableTitle')}
            message={t('recentTasksUnavailableMessage')}
          />
        ) : visibleRecentTasks.length > 0 ? (
          <div className="link-rows">
            {visibleRecentTasks.map((task) => {
              const steps = task.plan ?? [];
              const completed = steps.filter(
                (step) => step.status === 'COMPLETED' || step.status === 'SKIPPED',
              ).length;
              const current = steps.find((step) => step.status === 'RUNNING')?.name;
              return (
                <button
                  key={task.id}
                  type="button"
                  className="link-row"
                  onClick={() => onOpenTask?.(task.id)}
                >
                  <span className="link-row-icon">
                    <ClipboardCheck size={15} strokeWidth={1.7} />
                  </span>
                  <span className="link-row-copy">
                    <span className="link-row-title" title={task.goal}>
                      {taskT(`type_${task.type}`)} · {task.goal}
                    </span>
                    {current && (
                      <span className="link-row-meta">
                        {taskT('currentStep')}: {current}
                      </span>
                    )}
                  </span>
                  <span className="status-pill status-pill-draft">
                    {completed}/{steps.length}
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <EmptyState
            icon={<Workflow size={18} strokeWidth={1.7} />}
            title={taskT('noTasks')}
            message={taskT('dashboardDescription')}
          />
        )}
      </section>
    </div>
  );
};
