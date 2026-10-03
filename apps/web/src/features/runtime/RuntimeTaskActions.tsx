import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { AgentTask } from '../../types';
import type { RuntimeSnapshot } from '../../types/runtime';
import { runtimeActive } from './runtimeModel';
import { RuntimeArtifactActions } from './RuntimeArtifactActions';

/** Business commands stay outside the read-only projection. */
export function RuntimeTaskActions({ snapshot, onChanged }: { snapshot: RuntimeSnapshot; onChanged: () => void }) {
  const [detail, setDetail] = useState<AgentTask | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const taskId = snapshot.kind === 'task' ? snapshot.id : null;
  useEffect(() => {
    setDetail(null); setError(''); setComment('');
    if (!taskId || !snapshot.summary.approval) return;
    let disposed = false;
    void api.getTask(taskId).then((value) => { if (!disposed) setDetail(value); }).catch((reason) => { if (!disposed) setError(String(reason)); });
    return () => { disposed = true; };
  }, [taskId, snapshot.summary.approval]);
  if (!taskId) return null;
  const failed = ['FAILED', 'BLOCKED'].includes(snapshot.status);
  if (!runtimeActive(snapshot.status) && !failed) return null;
  const change = detail?.context?.pending_change_summary;
  const summary = change && typeof change === 'object' ? change as Record<string, unknown> : {};
  const diffArtifact = snapshot.artifacts.find((artifact) => artifact.artifact_id === summary.artifact_id);
  const reviewable = typeof summary.preview === 'string' && Boolean(diffArtifact) && typeof summary.base_exists === 'boolean';
  const command = async (action: () => Promise<unknown>) => {
    setBusy(true); setError('');
    try { await action(); onChanged(); } catch (reason) { setError(String(reason)); } finally { setBusy(false); }
  };
  return <section className="rt-task-actions" aria-label="工作流操作">
    {snapshot.summary.approval && <>
      <strong>审批待应用变更</strong>
      <p><code>{typeof summary.file_path === 'string' ? summary.file_path : '正在读取变更摘要…'}</code> · {typeof summary.change_kind === 'string' ? summary.change_kind : ''}</p>
      {typeof summary.preview === 'string' && <pre>{summary.preview.slice(0, 20000)}</pre>}
      {summary.preview_truncated === true && <p className="rt-notice">Diff 预览已截断，请下载完整变更后审批。</p>}
      {diffArtifact && <RuntimeArtifactActions artifact={diffArtifact} />}
      {detail && !reviewable && <p className="rt-notice">缺少可审阅的 Diff 或源文件基线，请拒绝变更并重新规划。</p>}
    </>}
    {(snapshot.summary.approval || failed) && <label>审批备注／重新规划说明<textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={2} /></label>}
    <div className="rt-toolbar">
      {snapshot.summary.approval && <>
        <button className="btn btn-primary btn-sm" disabled={busy || !detail || !reviewable} onClick={() => void command(() => api.decideTaskApproval(taskId, true, comment))}>批准变更</button>
        <button className="btn btn-secondary btn-sm" disabled={busy || !detail} onClick={() => void command(() => api.decideTaskApproval(taskId, false, comment))}>拒绝变更</button>
      </>}
      {failed && <button className="btn btn-secondary btn-sm" disabled={busy || !comment.trim()} onClick={() => void command(() => api.replanTask(taskId, comment))}>重新规划</button>}
      {runtimeActive(snapshot.status) && <button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => void command(() => api.cancelTask(taskId))}>取消工作流</button>}
    </div>
    {error && <p className="rt-notice" role="alert">{error}</p>}
  </section>;
}
