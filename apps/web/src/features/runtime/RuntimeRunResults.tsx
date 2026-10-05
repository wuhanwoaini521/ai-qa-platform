import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { RuntimeSnapshot } from '../../types/runtime';
import { useRunStore } from '../runs/useRunStore';
import { durationLabel } from './runtimeModel';

/** Results and bounded console output use the same live store as Browser and Studio. */
export function RuntimeRunResults({ snapshot }: { snapshot: RuntimeSnapshot }) {
  const { t } = useTranslation('runtime');
  const [selected, setSelected] = useState('');
  const [page, setPage] = useState(0);
  const [following, setFollowing] = useState(true);
  const output = useRef<HTMLPreElement>(null);
  const runId = snapshot.runs.find((run) => run.id === selected)?.id ?? snapshot.runs.at(-1)?.id ?? null;
  const live = useRunStore(runId);
  useEffect(() => { setPage(0); setFollowing(true); }, [runId]);
  useEffect(() => {
    if (following && output.current) output.current.scrollTop = output.current.scrollHeight;
  }, [following, live.run?.log_output]);
  if (!runId) return null;
  const executions = live.run?.executions ?? [];
  const lastPage = Math.max(0, Math.ceil(executions.length / 50) - 1);
  const currentPage = Math.min(page, lastPage);
  return (
    <section className="rt-block rt-run-results">
      <div className="rt-toolbar">
        <h3>{t('testResultsAndLogs')}</h3>
        {snapshot.runs.length > 1 && (
          <label>{t('testRun')} <select value={runId} onChange={(event) => setSelected(event.target.value)}>
            {snapshot.runs.map((run) => <option key={run.id} value={run.id}>{run.id} · {t(run.status.toLowerCase(), { defaultValue: run.status })}</option>)}
          </select></label>
        )}
        <Link to={`/runs/${runId}`}>{t('openFullRun')}</Link>
      </div>
      {live.error && <p className="rt-notice" role="alert">{live.error}</p>}
      {!executions.length ? <p className="rt-muted">{live.run ? t('noTestResults') : t('loadingTestResults')}</p> : (
        <div className="table-responsive">
          <table className="data-table">
            <thead><tr><th>{t('statusLabel')}</th><th>{t('test')}</th><th>{t('durationLabel')}</th><th>{t('failureEvidence')}</th></tr></thead>
            <tbody>{executions.slice(currentPage * 50, (currentPage + 1) * 50).map((item) => {
              const failure = snapshot.failures.find((value) => value.execution_id === item.id && value.test_run_id === runId);
              return <tr key={item.id}>
                <td><span className={`rt-status status-${item.status.toLowerCase()}`}>{t(item.status.toLowerCase(), { defaultValue: item.status })}</span></td>
                <td><code>{item.nodeid}</code></td><td>{durationLabel(item.duration_ms)}</td>
                <td>{failure ? <Link to={`/failures/${encodeURIComponent(failure.id)}`}>{item.error_message || failure.title}</Link> : item.error_message || '—'}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>
      )}
      {lastPage > 0 && <div className="rt-toolbar">
        <button className="btn btn-secondary btn-sm" disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>{t('previousPage')}</button>
        <span>{currentPage + 1} / {lastPage + 1} · {t('testsCount', { count: executions.length })}</span>
        <button className="btn btn-secondary btn-sm" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>{t('nextPage')}</button>
      </div>}
      <details className="rt-console">
        <summary>{t('runLogs')} · {t('recentCharacters', { count: 20000 })}</summary>
        <button className="btn btn-secondary btn-sm" aria-pressed={following} onClick={() => setFollowing((value) => !value)}>{following ? t('pauseFollowing') : t('resumeFollowing')}</button>
        <pre ref={output} onScroll={(event) => {
          const element = event.currentTarget;
          if (element.scrollHeight - element.scrollTop - element.clientHeight > 32) setFollowing(false);
        }}>{live.run?.log_output || t('noLogs')}</pre>
      </details>
    </section>
  );
}
