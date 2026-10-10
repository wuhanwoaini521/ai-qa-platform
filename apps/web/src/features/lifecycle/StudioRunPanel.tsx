import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { api } from '../../api/client';
import { RuntimeDetail } from '../runtime/RuntimeDetail';
import { useRunStore } from '../runs/useRunStore';
import { buildWorkflowHref, type WorkspaceContext } from '../../app/workspaceContext';

export function StudioRunPanel({ runId, projectId, context, onStep, onClose }: {
  runId: string | null;
  projectId: string;
  context?: WorkspaceContext;
  onStep: (path: string, line: number) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation('lifecycle');
  const live = useRunStore(runId);
  const [error, setError] = useState('');
  const workflowHref = buildWorkflowHref({
    ...context,
    projectId,
    runId: runId ?? context?.runId,
    taskId: runId ? undefined : context?.taskId,
  });
  const toolbar = <div className="lc-toolbar lc-studio-run-toolbar">
    {runId && <>
      <Link className="btn btn-secondary btn-sm" to={workflowHref}>Open Workflow</Link>
      {live.run && ['RUNNING', 'QUEUED'].includes(live.run.status) && <button
        className="btn btn-secondary btn-sm"
        onClick={() => void api.cancelTestRun(runId).catch((reason) => setError(String(reason)))}
      >取消运行</button>}
    </>}
    <button
      className="btn btn-secondary btn-sm lc-studio-run-close"
      onClick={onClose}
      aria-label={t('closeRunDrawer')}
      title={t('closeRunDrawer')}
    ><X size={16} aria-hidden="true" /></button>
  </div>;

  if (!runId) return <div className="lc-studio-run-panel">
    {toolbar}
    <div className="lc-studio-run-content">
      <section className="lc-card">
        <p className="lc-muted">{t('noRun')}</p>
        {projectId === 'proj_golden_shop_v1' && <>
          <p className="lc-caption">{t('previewNotice')}</p>
          <iframe title="Northstar Demo Shop" src="/api/demo-shop/index.html" />
        </>}
      </section>
    </div>
  </div>;

  return <div className="lc-studio-run-panel">
    {toolbar}
    {error && <p className="lc-notice lc-error" role="alert">{error}</p>}
    <div className="lc-studio-run-content">
      <RuntimeDetail
        key={runId}
        kind="run"
        id={runId}
        initialTab="Browser"
        projectId={projectId}
        onOpenSource={(path, line) => { onStep(path, line); onClose(); }}
      />
    </div>
  </div>;
}
