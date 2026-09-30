import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Check, Circle, Clock3, Play, ShieldAlert } from 'lucide-react';
import { api } from '../api/client';
import { AgentTask, AgentTaskType } from '../types';

type TaskRequest = {
  type: AgentTaskType;
  goal: string;
  project_id: string;
  workspace_id?: string;
  inputs: Record<string, unknown>;
};

/** Keeps the latest task attached to its business object, including after a page reload. */
export function useContextTask(projectId: string | null, origin: string, originId: string | null) {
  const [task, setTask] = useState<AgentTask | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const loadVersion = useRef(0);

  useEffect(() => {
    const version = ++loadVersion.current;
    setTask(null);
    setError('');
    if (!projectId || !originId) return;
    let active = true;
    void api.getTasks(projectId).then((rows) => {
      if (!active || version !== loadVersion.current) return;
      setTask(rows.find((row) => row.inputs.origin === origin && row.inputs.origin_id === originId) ?? null);
    }).catch((cause) => { if (active && version === loadVersion.current) setError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { active = false; };
  }, [projectId, origin, originId]);

  useEffect(() => {
    if (!task || ['COMPLETED', 'FAILED', 'BLOCKED', 'CANCELLED'].includes(task.status)) return;
    let active = true;
    const refresh = () => void api.getTask(task.id).then((updated) => { if (active) setTask(updated); }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : String(cause));
    });
    refresh();
    const close = api.streamTaskEvents(task.id, refresh, () => undefined);
    return () => { active = false; close(); };
  }, [task?.id, task?.status]);

  const start = useCallback(async (request: TaskRequest) => {
    if (!originId) return;
    const version = ++loadVersion.current;
    setBusy(true);
    setError('');
    try {
      const created = await api.createTask({ ...request, inputs: { ...request.inputs, origin, origin_id: originId } });
      if (version === loadVersion.current) setTask(created);
    } catch (cause) {
      if (version === loadVersion.current) setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }, [origin, originId]);

  return { task, busy, error, start };
}

export const ContextTaskProgress: React.FC<{ task: AgentTask | null; error?: string }> = ({ task, error }) => {
  const { t } = useTranslation('tasks');
  if (!task && !error) return null;
  const steps = task?.steps ?? task?.plan ?? [];
  const completed = steps.filter((step) => ['COMPLETED', 'SKIPPED'].includes(step.status)).length;
  const current = steps.find((step) => ['RUNNING', 'WAITING_FOR_APPROVAL', 'FAILED'].includes(step.status));
  const registeredCaseId = steps.find((step) => step.key === 'register')?.outputs?.test_case_id;
  return <section className="card" aria-live="polite" style={{ marginTop: 12 }}>
    <div className="card-body" style={{ display: 'grid', gap: 8 }}>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {task && <>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <strong>{t('progress')} · {t(`status_${task.status}`)} · {completed}/{steps.length}</strong>
          <Link className="btn btn-secondary btn-sm" to={`/tasks?taskId=${encodeURIComponent(task.id)}`}>{t('openCenter')}</Link>
        </div>
        <div>{task.goal}</div>
        {current && <div style={{ color: 'var(--text-muted)' }}>{current.status === 'WAITING_FOR_APPROVAL' ? t('approvalRequired') : t('currentStep')}: {current.name}</div>}
        <ol style={{ display: 'grid', gap: 4, maxHeight: 170, overflowY: 'auto', margin: 0, paddingLeft: 22 }}>
          {steps.map((step) => <li key={step.id} style={{ color: 'var(--text-muted)' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              {step.status === 'COMPLETED' ? <Check size={14} /> : step.status === 'RUNNING' ? <Play size={14} /> : step.status === 'FAILED' ? <ShieldAlert size={14} /> : step.status === 'WAITING_FOR_APPROVAL' ? <Clock3 size={14} /> : <Circle size={14} />}
              <span>{step.name} · {t(`step_${step.status}`)}</span>
            </span>
          </li>)}
        </ol>
        {task.failure_reason && <div className="alert alert-error" role="alert">{task.failure_reason}</div>}
        {typeof registeredCaseId === 'string' && <Link to={`/test-cases/${encodeURIComponent(registeredCaseId)}`}>{t('viewGeneratedCase')}</Link>}
      </>}
    </div>
  </section>;
};
