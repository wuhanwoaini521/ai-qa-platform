import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { RuntimeSnapshot, RuntimeSourceOpener } from '../../types/runtime';
import { LiveBrowserPanel } from '../runs/LiveBrowserPanel';
import { useRunStore } from '../runs/useRunStore';
import { browserEntries } from './browserModel';
import { RuntimeFailureWorkspace } from './RuntimeFailureWorkspace';

export function RuntimeBrowser({ snapshot, projectId, onOpenSource }: {
  snapshot: RuntimeSnapshot;
  projectId?: string;
  onOpenSource?: RuntimeSourceOpener;
}) {
  const { t } = useTranslation('runtime');
  const [selected, setSelected] = useState('');
  const [selectedFailureId, setSelectedFailureId] = useState('');
  const [channel, setChannel] = useState<
    'recent_steps' | 'network_logs' | 'console_logs'
  >('recent_steps');
  const runId =
    snapshot.runs.find((run) => run.id === selected)?.id ??
    snapshot.runs.at(-1)?.id ??
    null;
  const live = useRunStore(runId);
  const entries = browserEntries(live.sessions, channel);
  const browserUsed = snapshot.browser_sessions.length > 0 || snapshot.events.some((event) => event.category === 'browser');
  const recorderSessionId = snapshot.task?.recorder_session_id;
  const failures = snapshot.failures.filter((failure) => !runId || failure.test_run_id === runId);
  const activeFailure = failures.find((failure) => failure.id === selectedFailureId) ?? failures[0] ?? null;
  const failureSession = activeFailure
    ? live.sessions.find((session) => session.case_execution_id === activeFailure.execution_id)
      ?? snapshot.browser_sessions.find((session) => session.case_execution_id === activeFailure.execution_id)
    : null;
  if (!browserUsed && !activeFailure && !recorderSessionId) return <div className="rt-browser"><p className="rt-empty">{t('browserUnused')}</p></div>;
  return (
    <div className="rt-browser">
      {recorderSessionId && <p className="rt-notice"><Link to={`/recorder?session_id=${encodeURIComponent(recorderSessionId)}`}>{t('takeOverBrowser')}</Link></p>}
      {snapshot.runs.length > 1 && (
        <label>
          {t('testRun')}{' '}
          <select
            value={runId ?? ''}
            onChange={(event) => setSelected(event.target.value)}
          >
            {snapshot.runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.id} · {t(run.status === 'WAITING_FOR_APPROVAL' ? 'waitingApproval' : run.status.toLowerCase(), { defaultValue: run.status })}
              </option>
            ))}
          </select>
        </label>
      )}
      {failures.length > 1 && (
        <label className="rt-failure-select">
          {t('failureWorkspace.failedCase')}{' '}
          <select value={activeFailure?.id ?? ''} onChange={(event) => setSelectedFailureId(event.target.value)}>
            {failures.map((failure) => <option key={failure.id} value={failure.id}>{failure.title}</option>)}
          </select>
        </label>
      )}
      {activeFailure && (
        <RuntimeFailureWorkspace
          key={activeFailure.id}
          failure={activeFailure}
          projectId={projectId}
          pageUrl={failureSession?.current_url}
          onOpenSource={onOpenSource}
        />
      )}
      {browserUsed && <>
      <LiveBrowserPanel
        sessions={live.sessions}
        frames={live.frames}
        runStatus={live.run?.status ?? snapshot.status}
        streamStatus={live.streamStatus}
        streamError={live.error}
      />
      {!runId && (
        <p className="rt-notice">{t('browserNoSession')}</p>
      )}
      <div className="rt-toolbar" aria-label={t('browserTelemetry')}>
        {(
          [
            ['recent_steps', t('browserSteps')],
            ['network_logs', t('network')],
            ['console_logs', t('console')],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            aria-pressed={channel === value}
            onClick={() => setChannel(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {!entries.length ? (
        <p className="rt-muted">{t('browserEventsUnrecorded')}</p>
      ) : (
        <div className="rt-browser-entries">
          {entries.map(({ session, entry }, index) => (
            <div key={`${session}:${index}`}>
              <time>
                {typeof entry.timestamp === 'string'
                  ? new Date(entry.timestamp).toLocaleTimeString()
                  : '—'}
              </time>
              <code>
                {String(entry.action ?? entry.method ?? entry.level ?? '')}
              </code>
              <span>
                {String(
                  entry.url ??
                    entry.locator ??
                    entry.message ??
                    entry.text ??
                    '',
                )}
              </span>
              <code>{String(entry.status ?? entry.status_code ?? '')}</code>
              {onOpenSource && typeof entry.file === 'string' && typeof entry.line === 'number' && (
                <button className="btn btn-secondary btn-sm" onClick={() => onOpenSource(entry.file as string, entry.line as number)}>
                  {entry.file}:{entry.line}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      </>}
    </div>
  );
}
