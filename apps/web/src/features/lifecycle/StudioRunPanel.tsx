import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '../../api/client';
import { RuntimeDetail } from '../runtime/RuntimeDetail';
import { useRunStore } from '../runs/useRunStore';

export function StudioRunPanel({ runId, projectId, onStep }: {
  runId: string | null;
  projectId: string;
  onStep: (path: string, line: number) => void;
}) {
  const { t } = useTranslation('lifecycle');
  const live = useRunStore(runId);
  const [error, setError] = useState('');
  if (!runId) return <section className="lc-card">
    <p className="lc-muted">{t('noRun')}</p>
    {projectId === 'proj_golden_shop_v1' && <>
      <p className="lc-caption">{t('previewNotice')}</p>
      <iframe title="Northstar Demo Shop" src="/api/demo-shop/index.html" />
    </>}
  </section>;
  return <div className="lc-stack">
    <div className="lc-toolbar">
      <Link className="btn btn-secondary btn-sm" to={`/runs/${runId}`}>Open Full Runtime</Link>
      {live.run && ['RUNNING', 'QUEUED'].includes(live.run.status) && <button
        className="btn btn-secondary btn-sm"
        onClick={() => void api.cancelTestRun(runId).catch((reason) => setError(String(reason)))}
      >取消运行</button>}
    </div>
    {error && <p className="lc-notice lc-error" role="alert">{error}</p>}
    <RuntimeDetail key={runId} kind="run" id={runId} onOpenSource={onStep} />
  </div>;
}
