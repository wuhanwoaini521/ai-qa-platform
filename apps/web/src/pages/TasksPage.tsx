import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { RuntimeDetail } from '../features/runtime/RuntimeDetail';
import { api } from '../api/client';
import { AgentTask, Project } from '../types';

const TERMINAL = new Set(['COMPLETED', 'FAILED', 'BLOCKED', 'CANCELLED']);
type TaskFilter = 'active' | 'approval' | 'failed' | 'completed' | 'all';
const needsApproval = (task: AgentTask) =>
  (task.steps ?? task.plan ?? []).some(
    (step) => step.status === 'WAITING_FOR_APPROVAL',
  );
const originPath = (task: AgentTask): string | null => {
  const id = task.inputs.origin_id;
  if (typeof id !== 'string') return null;
  switch (task.inputs.origin) {
    case 'recorder':
      return '/recorder';
    case 'failure':
      return `/failures/${encodeURIComponent(id)}`;
    case 'test_case':
      return `/test-cases/${encodeURIComponent(id)}`;
    case 'run':
      return `/runs/${encodeURIComponent(id)}`;
    case 'studio':
      return task.project_id
        ? `/projects/${encodeURIComponent(task.project_id)}/studio`
        : null;
    default:
      return null;
  }
};

export const TasksPage: React.FC<{
  projects: Project[];
  selectedProjectId: string | null;
}> = ({ projects, selectedProjectId }) => {
  const { t } = useTranslation('tasks');
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedTaskId = searchParams.get('taskId');
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [detail, setDetail] = useState<AgentTask | null>(null);
  const [projectId, setProjectId] = useState(
    selectedProjectId ?? projects[0]?.id ?? '',
  );
  const [filter, setFilter] = useState<TaskFilter>(selectedTaskId ? 'all' : 'active');
  const [error, setError] = useState('');

  const refreshTasks = useCallback(async () => {
    try {
      const rows = await api.getTasks(projectId || undefined);
      setTasks(rows);
      const selected = detail;
      if (selected && rows.some((row) => row.id === selected.id))
        setDetail(await api.getTask(selected.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : t('loadFailed'));
    }
  }, [detail?.id, projectId, t]);

  useEffect(() => {
    void refreshTasks();
  }, [refreshTasks]);
  useEffect(() => {
    const timer = window.setInterval(() => void refreshTasks(), 5000);
    return () => window.clearInterval(timer);
  }, [refreshTasks]);
  useEffect(() => {
    setProjectId(selectedProjectId ?? '');
  }, [selectedProjectId]);
  useEffect(() => {
    const taskId = selectedTaskId;
    if (taskId) {
      setFilter('all');
      void api
        .getTask(taskId)
        .then(setDetail)
        .catch((e) =>
          setError(e instanceof Error ? e.message : t('loadFailed')),
        );
    }
  }, [selectedTaskId, t]);

  const steps = detail?.steps ?? detail?.plan ?? [];
  const generatedCaseId = steps.find((step) => step.key === 'register')?.outputs
    ?.test_case_id;
  const matchesFilter = (task: AgentTask, value: TaskFilter) => {
    if (value === 'all') return true;
    if (value === 'approval') return needsApproval(task);
    if (value === 'failed') return ['FAILED', 'BLOCKED'].includes(task.status);
    if (value === 'completed')
      return ['COMPLETED', 'CANCELLED'].includes(task.status);
    return !TERMINAL.has(task.status) && task.status !== 'PAUSED' && !needsApproval(task);
  };
  const visibleTasks = tasks.filter((task) => matchesFilter(task, filter));

  return (
    <div className="page-container tasks-page">
      <div className="tasks-panels-grid">
        <section className="panel tasks-panel task-navigator" style={{ padding: 12 }}>
          <div className="task-navigator-heading">
            <h3>{t('taskList')} <span>({visibleTasks.length})</span></h3>
            <button type="button" className="btn btn-secondary btn-sm" aria-label={t('refresh')} title={t('refresh')} onClick={() => void refreshTasks()}><RefreshCw size={14} aria-hidden="true" /></button>
          </div>
          <label className="task-navigator-project">{t('project')}
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">{t('allProjects')}</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <div className="task-navigator-filters" role="group" aria-label={t('statusFilter')}>
            {(['active', 'approval', 'failed', 'completed', 'all'] as const).map((value) => (
              <button key={value} type="button" className={`btn btn-sm ${filter === value ? 'btn-primary' : 'btn-secondary'}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>
                {t(`filter_${value}`)} ({tasks.filter((task) => matchesFilter(task, value)).length})
              </button>
            ))}
          </div>
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <div
            className="task-list-scroll"
            style={{
              display: 'grid',
              gap: 6,
              maxHeight: 'min(680px, calc(100vh - 250px))',
              overflow: 'auto',
            }}
          >
            {visibleTasks.map((task) => (
              (() => {
                const plan = task.steps ?? task.plan ?? [];
                const completed = plan.filter((step) => step.status === 'COMPLETED').length;
                const failed = plan.filter((step) => step.status === 'FAILED').length;
                const current = plan.find((step) => ['RUNNING', 'WAITING_FOR_APPROVAL'].includes(step.status));
                const nodeid = typeof task.inputs.test_nodeid === 'string' ? task.inputs.test_nodeid : '';
                return (
              <button
                key={task.id}
                type="button"
                className={`task-nav-item${detail?.id === task.id ? ' is-selected' : ''}`}
                aria-pressed={detail?.id === task.id}
                onClick={() =>
                  setSearchParams((params) => {
                    params.set('taskId', task.id);
                    return params;
                  })
                }
              >
                <span className={`task-nav-status status-${task.status.toLowerCase()}`}><i aria-hidden="true" />{needsApproval(task) ? t('filter_approval') : t(`status_${task.status}`)}</span>
                <span className="task-nav-type">{t(`type_${task.type}`)}</span>
                <strong className="task-nav-title" title={task.goal}>{task.goal}</strong>
                {nodeid && <code className="task-nav-nodeid" title={nodeid}>{nodeid}</code>}
                {current && <small className="task-nav-current">{t('currentStep')}: {current.name}</small>}
                <span className="task-nav-progress">{completed} {t('stepsProgress')} · {failed} {t('filter_failed')} · {Math.max(0, plan.length - completed - failed)} {t('pendingShort')}</span>
                <time>{new Date(task.updated_at).toLocaleString()}</time>
              </button>
                );
              })()
            ))}
            {!visibleTasks.length && (
              <p style={{ color: 'var(--text-muted)' }}>{t('noTasks')}</p>
            )}
          </div>
        </section>

        <section
          className={`panel tasks-panel task-detail-panel${detail ? '' : ' is-empty'}`}
          style={{ padding: 12 }}
        >
          {!detail ? (
            <p style={{ color: 'var(--text-muted)' }}>{t('selectTask')}</p>
          ) : (
            <>
              {originPath(detail) && <Link to={originPath(detail)!}>{t('backToSource')}</Link>}
              {typeof generatedCaseId === 'string' && (
                <p>
                  <Link
                    to={`/test-cases/${encodeURIComponent(generatedCaseId)}`}
                  >
                    {t('viewGeneratedCase')}
                  </Link>
                </p>
              )}
              <RuntimeDetail
                key={detail.id}
                kind="task"
                id={detail.id}
              />
            </>
          )}
        </section>
      </div>
    </div>
  );
};
