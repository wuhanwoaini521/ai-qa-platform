import { useEffect, useState } from 'react';
import { Activity, AlertTriangle, RotateCcw, Workflow } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '../../api/client';
import { buildWorkflowHref, type WorkspaceContext } from '../../app/workspaceContext';
import type { RuntimeSnapshot } from '../../types/runtime';
import { currentSteps, durationLabel, retryActionLabel, retryGuidance, runtimeActive, runtimeStatusKey, spanDuration, stepCounts } from './runtimeModel';
import './runtime.css';

export function RuntimeMiniBar({
  snapshot,
  context,
  projectId,
  onOpenDetails,
}: {
  snapshot: RuntimeSnapshot | null;
  context: WorkspaceContext;
  projectId: string;
  onOpenDetails?: () => void;
}) {
  const { t } = useTranslation('runtime');
  const [now, setNow] = useState(() => Date.now());
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState('');
  const active = snapshot ? runtimeActive(snapshot.status) : false;

  // Runtime snapshots refresh while active; this local clock only advances the
  // displayed duration and never infers a task or step state.
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active, snapshot?.id]);
  useEffect(() => {
    setError('');
    setRetrying(false);
  }, [snapshot?.id]);

  const taskStep = snapshot?.kind === 'task'
    ? snapshot.steps.find((step) => step.id === snapshot.task?.current_step_id)
      ?? currentSteps(snapshot)[0]
      ?? null
    : null;
  const activeExecution = snapshot?.kind === 'run'
    ? snapshot.executions.find((execution) => execution.status === 'RUNNING') ?? null
    : null;
  const status = snapshot?.status ?? 'IDLE';
  const statusKey = snapshot ? runtimeStatusKey(status) : 'idle';
  const duration = snapshot ? durationLabel(spanDuration(snapshot, now)) : '—';
  const counts = snapshot?.kind === 'task' ? stepCounts(snapshot) : null;
  const current = taskStep?.title ?? activeExecution?.title ?? snapshot?.blocking?.reason
    ?? (snapshot && !active ? t('miniBar.finished') : '');
  const reason = snapshot?.blocking?.reason;
  const hasRetry = snapshot?.kind === 'task'
    && snapshot.blocking?.recovery_actions.includes('retry_step') === true;
  const runtimeContext: WorkspaceContext = snapshot?.kind === 'task'
    ? { ...context, projectId, taskId: snapshot.id, stepId: snapshot.blocking?.step_id ?? taskStep?.id ?? context.stepId }
    : snapshot?.kind === 'run'
      ? { ...context, projectId, taskId: undefined, runId: snapshot.id }
      : { ...context, projectId };
  const workflowHref = buildWorkflowHref(runtimeContext);
  const inspectHref = snapshot?.kind === 'task'
    ? buildWorkflowHref({ ...runtimeContext, stepId: snapshot.blocking?.step_id ?? taskStep?.id ?? undefined })
    : workflowHref;

  const retry = async () => {
    if (!snapshot || snapshot.kind !== 'task' || !hasRetry) return;
    setRetrying(true);
    setError('');
    try {
      await api.replanTask(snapshot.id, retryGuidance(snapshot.task?.type));
    } catch (reasonValue) {
      setError(reasonValue instanceof Error ? reasonValue.message : String(reasonValue));
    } finally {
      setRetrying(false);
    }
  };

  return (
    <section className={`rt-mini-bar${active ? ' is-active' : ''}${reason ? ' has-blocker' : ''}`} aria-label={t('miniBar.status')}>
      <div className="rt-mini-indicator">
        {reason ? <AlertTriangle size={13} aria-hidden="true" /> : <Activity size={13} aria-hidden="true" />}
        <strong>{status === 'IDLE' ? t('miniBar.idle') : t(statusKey, { defaultValue: status })}</strong>
        {snapshot && <small>{duration}</small>}
      </div>
      <div className="rt-mini-copy">
        <span>{snapshot?.title ?? t('miniBar.noRuntime')}</span>
        <small>{reason ? `${t('blockedHere')}: ${reason}` : current ? `${t('miniBar.currentStep')}: ${current}` : t('miniBar.noCurrentStep')}</small>
      </div>
      <div className="rt-mini-progress">
        {counts
          ? <><span>{t('completedCount')} {counts.completed}/{counts.total} {t('miniBar.steps')}</span><small>{counts.failed ? `${t('failedCount')} ${counts.failed}` : `${t('pendingCount')} ${counts.remaining}`}</small></>
          : snapshot?.kind === 'run'
            ? <><span>{snapshot.executions.filter((item) => item.finished_at).length}/{snapshot.executions.length} {t('miniBar.tests')}</span><small>{snapshot.executions.filter((item) => item.status === 'FAILED').length} {t('failedCount')}</small></>
            : <><span>{t('miniBar.noRuntime')}</span><small>{t('miniBar.noCurrentStep')}</small></>}
      </div>
      <div className="rt-mini-actions">
        {reason && <Link className="btn btn-secondary btn-sm" to={inspectHref}>{t('miniBar.inspect')}</Link>}
        {hasRetry && <button className="btn btn-secondary btn-sm" disabled={retrying} onClick={() => void retry()}><RotateCcw size={13} aria-hidden="true" />{retrying ? t('miniBar.retrying') : t(retryActionLabel(snapshot?.task?.type))}</button>}
        {onOpenDetails && <button className="btn btn-secondary btn-sm" onClick={onOpenDetails}>{t('miniBar.viewRun')}</button>}
        {snapshot && <Link className="btn btn-secondary btn-sm" to={workflowHref}><Workflow size={13} aria-hidden="true" />{t('miniBar.openWorkflow')}</Link>}
      </div>
      {error && <p className="rt-mini-error" role="alert">{t('miniBar.retryFailed', { error })}</p>}
    </section>
  );
}
