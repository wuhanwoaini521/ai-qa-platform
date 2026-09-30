import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';
import { Check, Circle, Clock3, Play, RefreshCw, ShieldAlert, StopCircle } from 'lucide-react';
import { api } from '../api/client';
import { AgentTask, AITraceEvent, Project } from '../types';
import { AIExecutionTimeline } from '../components/AIExecutionTimeline';

const TERMINAL = new Set(['COMPLETED', 'FAILED', 'BLOCKED', 'CANCELLED']);
type TaskFilter = 'active' | 'approval' | 'failed' | 'completed' | 'all';
const needsApproval = (task: AgentTask) => (task.steps ?? task.plan ?? []).some((step) => step.status === 'WAITING_FOR_APPROVAL');
const originPath = (task: AgentTask): string | null => {
  const id = task.inputs.origin_id;
  if (typeof id !== 'string') return null;
  switch (task.inputs.origin) {
    case 'recorder': return '/recorder';
    case 'failure': return `/failures/${encodeURIComponent(id)}`;
    case 'test_case': return `/test-cases/${encodeURIComponent(id)}`;
    case 'run': return `/runs/${encodeURIComponent(id)}`;
    case 'studio': return task.project_id ? `/projects/${encodeURIComponent(task.project_id)}/studio` : null;
    default: return null;
  }
};

export const TasksPage: React.FC<{ projects: Project[]; selectedProjectId: string | null }> = ({ projects, selectedProjectId }) => {
  const { t } = useTranslation('tasks');
  const [searchParams] = useSearchParams();
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [detail, setDetail] = useState<AgentTask | null>(null);
  const [projectId, setProjectId] = useState(selectedProjectId ?? projects[0]?.id ?? '');
  const [filter, setFilter] = useState<TaskFilter>('active');
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refreshTasks = useCallback(async () => {
    try {
      const rows = await api.getTasks(projectId || undefined);
      setTasks(rows);
      const selected = detail;
      if (selected && rows.some((row) => row.id === selected.id)) setDetail(await api.getTask(selected.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : t('loadFailed'));
    }
  }, [detail?.id, projectId, t]);

  useEffect(() => { void refreshTasks(); }, [refreshTasks]);
  useEffect(() => {
    const timer = window.setInterval(() => void refreshTasks(), 5000);
    return () => window.clearInterval(timer);
  }, [refreshTasks]);
  useEffect(() => { setProjectId(selectedProjectId ?? ''); }, [selectedProjectId]);
  useEffect(() => {
    const taskId = searchParams.get('taskId');
    if (taskId) void api.getTask(taskId).then(setDetail).catch((e) => setError(e instanceof Error ? e.message : t('loadFailed')));
  }, [searchParams, t]);
  useEffect(() => {
    if (!detail || TERMINAL.has(detail.status)) return;
    let close: () => void = () => {};
    close = api.streamTaskEvents(detail.id, () => {
      void api.getTask(detail.id).then((updated) => {
        setDetail(updated);
        if (TERMINAL.has(updated.status)) close();
      });
      void refreshTasks();
    }, () => undefined);
    return close;
  }, [detail?.id, refreshTasks]);

  const steps = detail?.steps ?? detail?.plan ?? [];
  const generatedCaseId = steps.find((step) => step.key === 'register')?.outputs?.test_case_id;
  const waitingForApproval = steps.some((step) => step.status === 'WAITING_FOR_APPROVAL');
  const canCancel = !!detail && !TERMINAL.has(detail.status);
  const canReplan = !!detail && ['BLOCKED', 'FAILED'].includes(detail.status) && detail.replan_count < detail.max_replans;
  const visibleTasks = tasks.filter((task) => {
    if (filter === 'all') return true;
    if (filter === 'approval') return needsApproval(task);
    if (filter === 'failed') return ['FAILED', 'BLOCKED'].includes(task.status);
    if (filter === 'completed') return ['COMPLETED', 'CANCELLED'].includes(task.status);
    return !TERMINAL.has(task.status) && !needsApproval(task);
  });

  const doAction = async (action: () => Promise<AgentTask>) => {
    if (!detail) return;
    setBusy(true); setError('');
    try { setDetail(await action()); await refreshTasks(); }
    catch (e) { setError(e instanceof Error ? e.message : t('actionFailed')); }
    finally { setBusy(false); }
  };

  const decisions = useMemo(() => detail?.decisions ?? [], [detail?.decisions]);
  const aiTraceEvents = useMemo(() => (detail?.events ?? [])
    .filter((event) => event.type === 'ai.trace')
    .map((event) => event.payload as unknown as AITraceEvent), [detail?.events]);
  const aiTraceRuns = useMemo(() => {
    const runs = new Map<string, AITraceEvent[]>();
    for (const event of aiTraceEvents) runs.set(event.run_id, [...(runs.get(event.run_id) ?? []), event]);
    return [...runs.values()];
  }, [aiTraceEvents]);

  return (
    <div className="page-container tasks-page">
      <section className="panel tasks-panel" style={{ padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <div><h2 style={{ margin: 0 }}>{t('centerTitle')}</h2><p style={{ color: 'var(--text-muted)', margin: '6px 0 0' }}>{t('centerDescription')}</p></div>
          <button type="button" className="btn btn-secondary" onClick={() => void refreshTasks()}><RefreshCw size={16} /> {t('refresh')}</button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <label>{t('project')} <select value={projectId} onChange={(e) => setProjectId(e.target.value)}><option value="">{t('allProjects')}</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <div role="group" aria-label={t('statusFilter')} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {(['active', 'approval', 'failed', 'completed', 'all'] as const).map((value) => <button key={value} type="button" className={`btn ${filter === value ? 'btn-primary' : 'btn-secondary'}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>{t(`filter_${value}`)} ({tasks.filter((task) => value === 'all' || (value === 'approval' ? needsApproval(task) : value === 'failed' ? ['FAILED', 'BLOCKED'].includes(task.status) : value === 'completed' ? ['COMPLETED', 'CANCELLED'].includes(task.status) : !TERMINAL.has(task.status) && !needsApproval(task))).length})</button>)}
          </div>
        </div>
        {error && <div className="alert alert-error" role="alert" style={{ marginTop: 12 }}>{error}</div>}
      </section>

      <div className="tasks-panels-grid">
        <section className="panel tasks-panel" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>{t('taskList')} <span style={{ color: 'var(--text-muted)' }}>({visibleTasks.length})</span></h3>
          <div className="task-list-scroll" style={{ display: 'grid', gap: 8, maxHeight: 'min(680px, calc(100vh - 360px))', overflow: 'auto' }}>
            {visibleTasks.map((task) => <button key={task.id} type="button" className="btn btn-secondary" aria-pressed={detail?.id === task.id} onClick={() => { void api.getTask(task.id).then(setDetail); }} style={{ textAlign: 'left', display: 'grid', gap: 4, whiteSpace: 'normal' }}>
              <strong>{task.goal}</strong><span>{t(`type_${task.type}`)} · {needsApproval(task) ? t('filter_approval') : t(`status_${task.status}`)}</span>{(task.plan ?? []).find((step) => step.status === 'RUNNING') && <small>{t('currentStep')}: {(task.plan ?? []).find((step) => step.status === 'RUNNING')?.name}</small>}<small>{new Date(task.updated_at).toLocaleString()}</small>
            </button>)}
            {!visibleTasks.length && <p style={{ color: 'var(--text-muted)' }}>{t('noTasks')}</p>}
          </div>
        </section>

        <section className={`panel tasks-panel task-detail-panel${detail ? '' : ' is-empty'}`} style={{ padding: 20 }}>
          {!detail ? <p style={{ color: 'var(--text-muted)' }}>{t('selectTask')}</p> : <>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'start' }}>
              <div><h2 style={{ margin: 0 }}>{detail.goal}</h2><p>{t(`type_${detail.type}`)} · {waitingForApproval ? t('filter_approval') : t(`status_${detail.status}`)}</p><small>{detail.id}</small>{originPath(detail) && <p><Link to={originPath(detail)!}>{t('backToSource')}</Link></p>}</div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {canCancel && <button className="btn btn-secondary" disabled={busy} onClick={() => void doAction(() => api.cancelTask(detail.id))}><StopCircle size={16} /> {t('cancel')}</button>}
                {canReplan && <button className="btn btn-secondary" disabled={busy || !comment.trim()} onClick={() => void doAction(() => api.replanTask(detail.id, comment))}><RefreshCw size={16} /> {t('replan')}</button>}
              </div>
            </div>
            {typeof generatedCaseId === 'string' && <p><Link to={`/test-cases/${encodeURIComponent(generatedCaseId)}`}>{t('viewGeneratedCase')}</Link></p>}
            {waitingForApproval && <div style={{ padding: 14, border: '1px solid var(--warning-color, #d97706)', borderRadius: 8, margin: '16px 0' }}>
              <strong><ShieldAlert size={16} style={{ verticalAlign: 'middle' }} /> {t('approvalRequired')}</strong>
              {(() => {
                const summary = detail.context?.pending_change_summary;
                if (!summary || typeof summary !== 'object') return <p>{t('approvalDescription')}</p>;
                const change = summary as { file_path?: string; change_kind?: string; preview?: string };
                return <>
                  <p>{change.file_path || t('approvalDescription')} · {change.change_kind || ''}</p>
                  {change.preview && <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 320, overflow: 'auto', padding: 12, background: 'var(--surface-muted, #f3f4f6)' }}>{change.preview}</pre>}
                </>;
              })()}
              <button className="btn btn-primary" disabled={busy} onClick={() => void doAction(() => api.decideTaskApproval(detail.id, true, comment))}><Check size={16} /> {t('approve')}</button>{' '}
              <button className="btn btn-secondary" disabled={busy} onClick={() => void doAction(() => api.decideTaskApproval(detail.id, false, comment))}>{t('reject')}</button>
            </div>}
            {detail.failure_reason && <p role="alert" style={{ color: 'var(--danger-color, #dc2626)' }}>{detail.failure_reason}</p>}
            {(['BLOCKED', 'FAILED'].includes(detail.status)) && <label>{t('replanInstructions')}<textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} /></label>}
            <h3>{t('workflow')}</h3>
            <ol style={{ display: 'grid', gap: 8, paddingLeft: 22 }}>{steps.map((step) => <li key={step.id} style={{ padding: 8, borderBottom: '1px solid var(--border-color, #e5e7eb)' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>{step.status === 'COMPLETED' ? <Check size={16} /> : step.status === 'RUNNING' ? <Play size={16} /> : step.status === 'FAILED' ? <ShieldAlert size={16} /> : step.status === 'PENDING' ? <Clock3 size={16} /> : <Circle size={16} />}<strong>{step.name}</strong><span>{t(`step_${step.status}`)}</span></div>
              <small style={{ color: 'var(--text-muted)' }}>{step.tool}{step.duration_ms ? ` · ${Math.round(step.duration_ms)} ms` : ''}</small>
              {step.error && <div role="alert">{step.error}</div>}
              <details style={{ marginTop: 5 }}><summary>{t('stepDetails')}</summary>
                <div>{t('dependencies')}: {step.dependencies.join(', ') || '—'} · {t('retries')}: {step.retry_count}/{step.max_retries}</div>
                <strong>{t('stepInput')}</strong><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(step.inputs, null, 2)}</pre>
                <strong>{t('stepOutput')}</strong><pre style={{ whiteSpace: 'pre-wrap', maxHeight: 240, overflow: 'auto' }}>{JSON.stringify(step.outputs, null, 2)}</pre>
                <div>{t('evidence')}: {step.evidence_ids.join(', ') || '—'}</div>
              </details>
            </li>)}</ol>
            {!!aiTraceRuns.length && <><h3>{t('aiExecution')}</h3>{aiTraceRuns.map((events) => <AIExecutionTimeline key={events[0]?.run_id} events={events} running={!TERMINAL.has(detail.status)} />)}</>}
            {!!detail.evidence?.length && <><h3>{t('evidence')}</h3><ul>{detail.evidence.map((item) => <li key={item.id}><strong>{item.type}</strong> · {item.summary}<details><summary>{t('showEvidence')}</summary><pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto' }}>{item.content || JSON.stringify(item.metadata, null, 2)}</pre></details></li>)}</ul></>}
            {!!detail.artifacts?.length && <><h3>{t('artifacts')}</h3><ul>{detail.artifacts.map((item) => <li key={item.id}><button type="button" className="btn btn-secondary" onClick={() => void api.downloadArtifact(item.artifact_id).then((blob) => { const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = item.name; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 30_000); }).catch((e) => setError(e instanceof Error ? e.message : t('actionFailed')))}>{t('download')} {item.name}</button> · {item.kind}</li>)}</ul></>}
            {!!decisions.length && <><h3>{t('decisions')}</h3><ul>{decisions.map((item, index) => <li key={index}>{String(item.name)}: {String(item.choice)} ({String(item.provider)}, {String(item.confidence)})</li>)}</ul></>}
            {!!detail.events?.length && <><h3>{t('timeline')}</h3><ol>{detail.events.slice(-40).map((event) => <li key={event.id}><time>{new Date(event.created_at).toLocaleTimeString()}</time> · <strong>{event.type}</strong> <code>#{event.id}</code></li>)}</ol></>}
          </>}
        </section>
      </div>
    </div>
  );
};
