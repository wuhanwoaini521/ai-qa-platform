import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { RuntimeDetail } from '../features/runtime/RuntimeDetail';
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
    setBusy(false);
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
    let fetching = false;
    const refresh = async () => {
      if (fetching || !active) return;
      fetching = true;
      try { const updated = await api.getTask(task.id); if (active) setTask(updated); }
      catch (cause) { if (active) setError(cause instanceof Error ? cause.message : String(cause)); }
      finally { fetching = false; }
    };
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, [task?.id, task?.status]);

  const start = useCallback(async (request: TaskRequest): Promise<AgentTask | null> => {
    if (!originId) return null;
    const version = ++loadVersion.current;
    setBusy(true);
    setError('');
    try {
      const created = await api.createTask({ ...request, inputs: { ...request.inputs, origin, origin_id: originId } });
      if (version === loadVersion.current) setTask(created);
      return created;
    } catch (cause) {
      if (version === loadVersion.current) setError(cause instanceof Error ? cause.message : String(cause));
      return null;
    } finally {
      if (version === loadVersion.current) setBusy(false);
    }
  }, [origin, originId]);

  return { task, busy, error, start };
}

export const ContextTaskProgress: React.FC<{ task: AgentTask | null; error?: string }> = ({ task, error }) => {
  const { t } = useTranslation('tasks');
  if (!task && !error) return null;
  const steps = task?.steps ?? task?.plan ?? [];
  const registeredCaseId = steps.find((step) => step.key === 'register')?.outputs?.test_case_id;
  return <section className="card" style={{ marginTop: 12 }}>
    <div className="card-body" style={{ display: 'grid', gap: 8 }}>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {task && <>
        <Link className="btn btn-secondary btn-sm" to={`/runs/tasks?taskId=${encodeURIComponent(task.id)}`}>Open Full Runtime</Link>
        <RuntimeDetail key={task.id} kind="task" id={task.id} />
        {typeof registeredCaseId === 'string' && <Link to={`/test-cases/${encodeURIComponent(registeredCaseId)}`}>{t('viewGeneratedCase')}</Link>}
      </>}
    </div>
  </section>;
};
