import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { AgentTask } from '../../types';
import type { RuntimeSnapshot } from '../../types/runtime';
import { api } from '../../api/client';
import { retryActionLabel, retryGuidance, runtimeActive } from './runtimeModel';
import { RuntimeArtifactActions } from './RuntimeArtifactActions';

export function RuntimeTaskActions({
  snapshot,
  onChanged,
  onInspect,
  onOpenStudio,
}: {
  snapshot: RuntimeSnapshot;
  onChanged: () => void;
  onInspect: (stepId: string) => void;
  onOpenStudio?: () => void;
}) {
  const { t } = useTranslation('runtime');
  const [detail, setDetail] = useState<AgentTask | null>(null);
  const [comment, setComment] = useState('');
  const [reason, setReason] = useState('');
  const [instructions, setInstructions] = useState('');
  const [replanOpen, setReplanOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const taskId = snapshot.kind === 'task' ? snapshot.id : null;
  useEffect(() => {
    setDetail(null);
    setError('');
    setComment('');
    setReason('');
    setInstructions('');
    setReplanOpen(false);
    if (!taskId || !snapshot.summary.approval) return;
    let disposed = false;
    void api.getTask(taskId)
      .then((value) => { if (!disposed) setDetail(value); })
      .catch((reasonValue) => { if (!disposed) setError(String(reasonValue)); });
    return () => { disposed = true; };
  }, [taskId, snapshot.summary.approval]);

  if (!taskId) return null;
  const failed = ['FAILED', 'BLOCKED'].includes(snapshot.status);
  const paused = snapshot.status.toUpperCase() === 'PAUSED';
  const pausing = snapshot.status.toUpperCase() === 'PAUSING';
  const pausable = ['PENDING', 'PLANNING', 'RUNNING', 'VERIFYING', 'RETRYING', 'REPLANNING'].includes(snapshot.status.toUpperCase());
  const retryLabel = retryActionLabel(snapshot.task?.type);
  const approval = snapshot.summary.approval;
  const actions = snapshot.blocking?.recovery_actions ?? [];
  if (!runtimeActive(snapshot.status) && !failed && !approval) return null;
  const change = detail?.context?.pending_change_summary;
  const summary = change && typeof change === 'object' ? change as Record<string, unknown> : {};
  const diffArtifact = snapshot.artifacts.find((artifact) => artifact.artifact_id === summary.artifact_id);
  const reviewable = typeof summary.preview === 'string' && Boolean(diffArtifact) && typeof summary.base_exists === 'boolean';

  const command = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError('');
    try { await action(); onChanged(); }
    catch (reasonValue) { setError(String(reasonValue)); }
    finally { setBusy(false); }
  };
  const retry = () => {
    void command(() => api.replanTask(taskId, retryGuidance(snapshot.task?.type)));
  };
  const submitReplan = () => {
    const text = [reason.trim() && `Reason: ${reason.trim()}`, instructions.trim()].filter(Boolean).join('\n\n');
    if (text) void command(() => api.replanTask(taskId, text));
  };

  return (
    <section className={`rt-task-actions${approval ? ' is-approval' : ''}`} aria-label={t('runtimeActions')}>
      {approval && (
        <div className="rt-approval-panel">
          <div className="rt-action-heading"><strong>{t('approvalRequired')}</strong><span className="rt-status status-waiting">{t('waitingApproval')}</span></div>
          <p><code>{typeof summary.file_path === 'string' ? summary.file_path : t('unknown')}</code>{typeof summary.change_kind === 'string' ? ` · ${summary.change_kind}` : ''}</p>
          {typeof summary.preview === 'string' && <pre>{summary.preview.slice(0, 20000)}</pre>}
          {summary.preview_truncated === true && <p className="rt-notice">{t('previewTruncated')}</p>}
          {diffArtifact && <RuntimeArtifactActions artifact={diffArtifact} />}
          {detail && !reviewable && <p className="rt-notice">{t('approvalPreviewMissing')}</p>}
          <label className="rt-action-comment">{t('comment')}<input value={comment} onChange={(event) => setComment(event.target.value)} /></label>
          <div className="rt-action-buttons">
            <button className="btn btn-primary btn-sm" disabled={busy || !detail || !reviewable} onClick={() => void command(() => api.decideTaskApproval(taskId, true, comment))}>{t('approve')}</button>
            <button className="btn btn-secondary btn-sm" disabled={busy || !detail} onClick={() => void command(() => api.decideTaskApproval(taskId, false, comment))}>{t('reject')}</button>
          </div>
        </div>
      )}
      {failed && actions.length > 0 && (
        <div className="rt-action-buttons">
          {actions.includes('retry_step') && (
            <button className="btn btn-primary btn-sm" disabled={busy} onClick={retry}>{t(retryLabel)}</button>
          )}
          {actions.includes('replan') && (
            <button className="btn btn-secondary btn-sm" disabled={busy} aria-expanded={replanOpen} onClick={() => setReplanOpen((open) => !open)}>{t('replan')}</button>
          )}
          {actions.includes('inspect_ai_output') && snapshot.blocking?.step_id && (
            <button className="btn btn-secondary btn-sm" onClick={() => onInspect(snapshot.blocking!.step_id!)}>{t('inspectOutput')}</button>
          )}
          <span className="rt-recovery-state">{snapshot.blocking?.recoverable ? t('recoverable') : t('notRecoverable')}</span>
        </div>
      )}
      {failed && !actions.length && <p className="rt-recovery-state">{t('noRecovery')}</p>}
      {replanOpen && (
        <div className="rt-replan-panel">
          <label>{t('replanReason')}<input value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          <label>{t('instructions')}<textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} rows={3} /></label>
          <div className="rt-replan-preview"><strong>{t('replanPreview')}</strong><p>{t('replanPreviewText')}</p></div>
          <div className="rt-action-buttons">
            <button className="btn btn-primary btn-sm" disabled={busy || !instructions.trim()} onClick={submitReplan}>{t('confirm')}</button>
            <button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setReplanOpen(false)}>{t('cancel')}</button>
          </div>
        </div>
      )}
      {paused && (
        <div className="rt-action-buttons">
          <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => void command(() => api.resumeTask(taskId))}>{t('resumeTask')}</button>
          {onOpenStudio && <button className="btn btn-secondary btn-sm" disabled={busy} onClick={onOpenStudio}>{t('openInStudio')}</button>}
        </div>
      )}
      {pausable && <button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => void command(() => api.pauseTask(taskId))}>{t('pauseTask')}</button>}
      {pausing && <p className="rt-notice" role="status">{t('pauseAfterStep')}</p>}
      {runtimeActive(snapshot.status) && <button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => void command(() => api.cancelTask(taskId))}>{t('cancelTask')}</button>}
      {error && <p className="rt-notice" role="alert">{error}</p>}
    </section>
  );
}
