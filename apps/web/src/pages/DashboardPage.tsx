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

export const DashboardPage: React.FC<DashboardPageProps> = ({
  onNavigate,
  onOpenTask,
}) => {
  const { t } = useTranslation('dashboard');
  const { t: taskT } = useTranslation('tasks');
  const { t: commonT } = useTranslation('common');
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentTasks, setRecentTasks] = useState<AgentTask[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [dashboard, tasks] = await Promise.allSettled([
          api.getDashboardStats(),
          api.getTasks(),
        ]);
        if (dashboard.status === 'fulfilled') setStats(dashboard.value);
        if (tasks.status === 'fulfilled') setRecentTasks(tasks.value);
      } catch (err) {
        console.error('Failed to load dashboard', err);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (loading && !stats) {
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

  return (
    <div className="dashboard-page">
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-card-body">
            <div className="stat-head">
              <span className="stat-icon"><Activity size={18} strokeWidth={1.7} /></span>
              <span className="stat-label">{t('passRateToday')}</span>
            </div>
            <span className="stat-value">
                {stats?.pass_rate_today != null ? `${stats.pass_rate_today.toFixed(1)}%` : '—'}
              </span>
          </div>
          <div className="stat-metric">
            <span className="status-dot is-live" />
            <span>{t('testsExecutedToday')}</span>
            <span className="stat-metric-value">{stats?.tests_executed_today ?? 0}</span>
          </div>
          <button type="button" className="card-footer" onClick={() => onNavigate('runs')}>
            <span>{t('executionRecord')}</span>
            <ArrowRight size={15} strokeWidth={1.7} />
          </button>
        </div>

        <div className="stat-card">
          <div className="stat-card-body">
            <div className="stat-head">
              <span className="stat-icon"><ListChecks size={18} strokeWidth={1.7} /></span>
              <span className="stat-label">{t('runsToday')}</span>
            </div>
            <span className="stat-value">{stats?.runs_today ?? 0}</span>
          </div>
          <div className="stat-metric">
            <span>{t('totalExecutions')}</span>
            <span className="stat-metric-value">{stats?.total_runs ?? 0}</span>
          </div>
          <button type="button" className="card-footer" onClick={() => onNavigate('runs')}>
            <span>{t('viewAll')}</span>
            <ArrowRight size={15} strokeWidth={1.7} />
          </button>
        </div>

        <div className="stat-card">
          <div className="stat-card-body">
            <div className="stat-head">
              <span className="stat-icon"><AlertTriangle size={18} strokeWidth={1.7} /></span>
              <span className="stat-label">{t('totalFailures')}</span>
            </div>
            <span className="stat-value">{stats?.total_failures ?? 0}</span>
          </div>
          <div className="stat-metric">
            <span>{t('likelyFlakyTests')}</span>
            <span className="stat-metric-value">{stats?.flaky_tests_count ?? 0}</span>
          </div>
          <button type="button" className="card-footer" onClick={() => onNavigate('failures')}>
            <span>{t('failureStepShort')}</span>
            <ArrowRight size={15} strokeWidth={1.7} />
          </button>
        </div>

        <div className="stat-card">
          <div className="stat-card-body">
            <div className="stat-head">
              <span className="stat-icon"><Clock size={18} strokeWidth={1.7} /></span>
              <span className="stat-label">{t('avgExecutionTime')}</span>
            </div>
            <span className="stat-value">
                {stats?.average_test_duration_ms
                  ? stats.average_test_duration_ms > 1000
                    ? `${(stats.average_test_duration_ms / 1000).toFixed(1)}s`
                    : `${stats.average_test_duration_ms}ms`
                  : '—'}
              </span>
          </div>
          <div className="stat-metric">
            <RotateCcw size={13} strokeWidth={1.7} />
            <span>{t('rerunRecoveries')}</span>
            <span className="stat-metric-value">{stats?.rerun_recovery_count ?? 0}</span>
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
            { key: 'qaProjects', Icon: FolderGit2, value: stats?.total_projects ?? 0 },
            { key: 'requirements', Icon: FileText, value: stats?.total_requirements ?? 0 },
            { key: 'testCases', Icon: CheckSquare, value: stats?.total_test_cases ?? 0 },
            { key: 'totalExecutions', Icon: PlayCircle, value: stats?.total_runs ?? 0 },
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
              message={t('noRecentRuns')}
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

      <section className="card">
        <div className="card-header">
          <div>
            <div className="card-title">{taskT('recentTasks')}</div>
            <div className="card-subtitle">{taskT('dashboardDescription')}</div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onNavigate('tasks')}>
            <Workflow size={14} strokeWidth={1.7} /> {taskT('allTasks')}
          </button>
        </div>
        {recentTasks.length > 0 ? (
          <div className="link-rows">
            {recentTasks.map((task) => {
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
                    <span className="link-row-title">
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
