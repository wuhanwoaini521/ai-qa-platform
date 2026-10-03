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
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [detail, setDetail] = useState<AgentTask | null>(null);
  const [projectId, setProjectId] = useState(
    selectedProjectId ?? projects[0]?.id ?? '',
  );
  const [filter, setFilter] = useState<TaskFilter>(searchParams.get('taskId') ? 'all' : 'active');
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
    const taskId = searchParams.get('taskId');
    if (taskId) {
      setFilter('all');
      void api
        .getTask(taskId)
        .then(setDetail)
        .catch((e) =>
          setError(e instanceof Error ? e.message : t('loadFailed')),
        );
    }
  }, [searchParams, t]);

  const steps = detail?.steps ?? detail?.plan ?? [];
  const generatedCaseId = steps.find((step) => step.key === 'register')?.outputs
    ?.test_case_id;
  const visibleTasks = tasks.filter((task) => {
    if (filter === 'all') return true;
    if (filter === 'approval') return needsApproval(task);
    if (filter === 'failed') return ['FAILED', 'BLOCKED'].includes(task.status);
    if (filter === 'completed')
      return ['COMPLETED', 'CANCELLED'].includes(task.status);
    return !TERMINAL.has(task.status) && !needsApproval(task);
  });

  return (
    <div className="page-container tasks-page">
      <section className="panel tasks-panel" style={{ padding: 12 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            marginBottom: 10,
          }}
        >
          <div>
            <h2 style={{ margin: 0 }}>{t('centerTitle')}</h2>
            <p style={{ color: 'var(--text-muted)', margin: '6px 0 0' }}>
              {t('centerDescription')}
            </p>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void refreshTasks()}
          >
            <RefreshCw size={16} /> {t('refresh')}
          </button>
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <label>
            {t('project')}{' '}
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
            >
              <option value="">{t('allProjects')}</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <div
            role="group"
            aria-label={t('statusFilter')}
            style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}
          >
            {(
              ['active', 'approval', 'failed', 'completed', 'all'] as const
            ).map((value) => (
              <button
                key={value}
                type="button"
                className={`btn ${filter === value ? 'btn-primary' : 'btn-secondary'}`}
                aria-pressed={filter === value}
                onClick={() => setFilter(value)}
              >
                {t(`filter_${value}`)} (
                {
                  tasks.filter(
                    (task) =>
                      value === 'all' ||
                      (value === 'approval'
                        ? needsApproval(task)
                        : value === 'failed'
                          ? ['FAILED', 'BLOCKED'].includes(task.status)
                          : value === 'completed'
                            ? ['COMPLETED', 'CANCELLED'].includes(task.status)
                            : !TERMINAL.has(task.status) &&
                              !needsApproval(task)),
                  ).length
                }
                )
              </button>
            ))}
          </div>
        </div>
        {error && (
          <div
            className="alert alert-error"
            role="alert"
            style={{ marginTop: 12 }}
          >
            {error}
          </div>
        )}
      </section>

      <div className="tasks-panels-grid">
        <section className="panel tasks-panel" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>
            {t('taskList')}{' '}
            <span style={{ color: 'var(--text-muted)' }}>
              ({visibleTasks.length})
            </span>
          </h3>
          <div
            className="task-list-scroll"
            style={{
              display: 'grid',
              gap: 8,
              maxHeight: 'min(680px, calc(100vh - 360px))',
              overflow: 'auto',
            }}
          >
            {visibleTasks.map((task) => (
              <button
                key={task.id}
                type="button"
                className="btn btn-secondary"
                aria-pressed={detail?.id === task.id}
                onClick={() =>
                  setSearchParams((params) => {
                    params.set('taskId', task.id);
                    return params;
                  })
                }
                style={{
                  textAlign: 'left',
                  display: 'grid',
                  gap: 4,
                  whiteSpace: 'normal',
                }}
              >
                <strong>{task.goal}</strong>
                <span>
                  {t(`type_${task.type}`)} ·{' '}
                  {needsApproval(task)
                    ? t('filter_approval')
                    : t(`status_${task.status}`)}
                </span>
                {(task.plan ?? []).find(
                  (step) => step.status === 'RUNNING',
                ) && (
                  <small>
                    {t('currentStep')}:{' '}
                    {
                      (task.plan ?? []).find(
                        (step) => step.status === 'RUNNING',
                      )?.name
                    }
                  </small>
                )}
                <small>{new Date(task.updated_at).toLocaleString()}</small>
              </button>
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
