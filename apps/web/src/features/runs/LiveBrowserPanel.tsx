import React, { useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { Maximize2, Minimize2, PanelTopClose, PanelTopOpen, MonitorPlay } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { TestBrowserSession } from '../../types';
import { api } from '../../api/client';

interface LiveBrowserPanelProps {
  sessions: TestBrowserSession[];
  frames: Record<string, string>;
  runStatus: string;
  streamStatus: 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'failed';
  streamError?: string | null;
  onSelectedSessionChange?: (sessionId: string | null) => void;
  failureWorkspace?: React.ReactNode;
}

const statusColor = (status: string) => {
  if (status === 'running') return 'var(--accent-blue)';
  if (status === 'passed') return 'var(--accent-green)';
  if (status === 'failed') return 'var(--accent-red)';
  return 'var(--ink-muted)';
};

export const LiveBrowserPanel: React.FC<LiveBrowserPanelProps> = ({ sessions, frames, runStatus, streamStatus, streamError, onSelectedSessionChange, failureWorkspace }) => {
  const { t } = useTranslation('runs');
  const ordered = useMemo(
    () => [...sessions].sort((a, b) => a.started_at.localeCompare(b.started_at)),
    [sessions],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [minimized, setMinimized] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [storedFrame, setStoredFrame] = useState<{ artifactId: string; url: string } | null>(null);
  const [snapshotFailed, setSnapshotFailed] = useState(false);
  const [, refreshElapsed] = useState(0);
  const latest = ordered[ordered.length - 1];
  const selected = ordered.find((session) => session.browser_session_id === selectedId)
    ?? [...ordered].reverse().find((session) => session.status === 'running') ?? latest;
  const snapshotId = typeof selected?.page_evidence?.last_frame_artifact_id === 'string'
    ? selected.page_evidence.last_frame_artifact_id : null;

  useLayoutEffect(() => {
    onSelectedSessionChange?.(selected?.browser_session_id ?? null);
  }, [onSelectedSessionChange, selected?.browser_session_id]);

  useEffect(() => {
    if (selectedId && !ordered.some((session) => session.browser_session_id === selectedId)) {
      setSelectedId(null);
    }
  }, [ordered, selectedId]);

  useEffect(() => {
    setStoredFrame(null);
    setSnapshotFailed(false);
    if (!snapshotId) return;
    let disposed = false;
    let objectUrl: string | null = null;
    api.downloadArtifact(snapshotId).then((blob) => {
      objectUrl = URL.createObjectURL(blob);
      if (disposed) URL.revokeObjectURL(objectUrl);
      else setStoredFrame({ artifactId: snapshotId, url: objectUrl });
    }).catch(() => { if (!disposed) setSnapshotFailed(true); });
    return () => {
      disposed = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [snapshotId]);

  useEffect(() => {
    if (selected?.status !== 'running') return;
    const timer = window.setInterval(() => refreshElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [selected?.browser_session_id, selected?.status]);

  if (!ordered.length) {
    const waiting = runStatus === 'RUNNING' || runStatus === 'QUEUED';
    return (
      <section className="card" aria-label={t('liveBrowsers')}>
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <span className="card-title">{t('liveBrowsers')}</span>
          {streamStatus === 'reconnecting' && <span role="status" className="badge badge-draft">{t('streamReconnecting')}</span>}
        </div>
        <div className="card-body" role={streamError ? 'alert' : 'status'} style={{ padding: 20, color: streamError ? 'var(--accent-red)' : 'var(--text-muted)', textAlign: 'center' }}>
          {streamError || (waiting ? t('waitingBrowserSession') : t('noBrowserSessions'))}
        </div>
      </section>
    );
  }
  const liveFrame = selected ? frames[selected.browser_session_id] : undefined;
  const frame = liveFrame || (storedFrame?.artifactId === snapshotId ? storedFrame?.url : undefined);

  return (
    <section className="card" aria-label={t('liveBrowsers')} style={{ overflow: 'hidden' }}>
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <MonitorPlay size={16} color="var(--accent-blue)" />
          <span className="card-title">{t('liveBrowsers')}</span>
          <span className="badge badge-draft">{ordered.length}</span>
          {selected?.status !== 'running' && frame && <span className="badge badge-draft">{t('lastCapturedFrame')}</span>}
          {streamStatus === 'reconnecting' && <span role="status" className="badge badge-draft">{t('streamReconnecting')}</span>}
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          <button className="btn btn-icon btn-sm" aria-label={minimized ? t('expandBrowserPanel') : t('minimizeBrowserPanel')} onClick={() => setMinimized((value) => !value)}>
            {minimized ? <PanelTopOpen size={14} /> : <PanelTopClose size={14} />}
          </button>
          <button className="btn btn-icon btn-sm" aria-label={expanded ? t('restoreBrowserPanel') : t('maximizeBrowserPanel')} onClick={() => setExpanded((value) => !value)}>
            {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>
      {!minimized && (
        <div className="card-body" style={{ padding: 12 }}>
          {streamError && <div role="alert" style={{ color: 'var(--accent-red)', marginBottom: 10 }}>{streamError}</div>}
          <div role="tablist" aria-label={t('browserWorkers')} style={{ display: 'flex', gap: 8, overflowX: 'auto', marginBottom: 10 }}>
            {ordered.map((session) => (
              <button
                key={session.browser_session_id}
                type="button"
                role="tab"
                aria-selected={selected?.browser_session_id === session.browser_session_id}
                onClick={() => {
                  setSelectedId(session.browser_session_id);
                  onSelectedSessionChange?.(session.browser_session_id);
                }}
                style={{
                  flex: '0 0 auto', padding: '7px 10px', borderRadius: 'var(--r-xs)',
                  border: selected?.browser_session_id === session.browser_session_id ? '1px solid var(--accent-blue)' : '1px solid var(--border-color)',
                  background: selected?.browser_session_id === session.browser_session_id ? 'var(--accent-blue-soft)' : 'var(--surface-raised)',
                  color: 'var(--ink)', textAlign: 'left', cursor: 'pointer',
                }}
                >
                <strong>{session.worker_id}</strong> · {session.case_name || session.nodeid.split('::').pop()}
                {session.case_execution_id && (
                  <span style={{ color: 'var(--text-muted)', marginLeft: 7 }}>· {session.case_execution_id.slice(0, 8)}</span>
                )}
                <span aria-label={session.status} style={{ color: statusColor(session.status), marginLeft: 4 }}>{session.status}</span>
              </button>
            ))}
          </div>
          {selected && (
            <div className="rt-browser-preview-layout" style={{ display: 'grid', gap: 12 }}>
              <div style={{ minWidth: 0, background: 'var(--surface-inverse)', borderRadius: 'var(--r-sm)', minHeight: expanded ? 540 : 260, display: 'grid', placeItems: 'center', overflow: 'hidden' }}>
                {frame ? (
                  <img src={frame} alt={`${selected.case_name} ${selected.status === 'running' ? 'live browser' : 'last captured browser frame'}`} style={{ display: 'block', width: '100%', maxHeight: expanded ? 540 : 380, objectFit: 'contain' }} />
                ) : (
                  <div style={{ color: 'var(--ink-faint)', textAlign: 'center', padding: 20, fontSize: 13 }}>
                    {snapshotFailed ? t('browserSnapshotLoadFailed') : snapshotId ? t('loadingBrowserSnapshot') : selected.status === 'running' ? t('waitingBrowserFrame') : t('browserFrameUnavailable')}
                  </div>
                )}
              </div>
              <dl style={{ margin: 0, display: 'grid', alignContent: 'start', gap: 9, fontSize: 12, minWidth: 0 }}>
                <div><dt style={{ color: 'var(--text-muted)' }}>{t('browserCase')}</dt><dd style={{ margin: '2px 0', overflowWrap: 'anywhere' }}>{selected.case_name || selected.nodeid}</dd></div>
                <div><dt style={{ color: 'var(--text-muted)' }}>{t('browserWorkerCaseId')}</dt><dd style={{ margin: '2px 0', fontFamily: 'var(--font-mono)', overflowWrap: 'anywhere' }}>{selected.worker_id} / {selected.case_execution_id?.slice(0, 8) ?? selected.nodeid}</dd></div>
                <div><dt style={{ color: 'var(--text-muted)' }}>{t('browserUrl')}</dt><dd style={{ margin: '2px 0', overflowWrap: 'anywhere' }}>{selected.current_url || 'about:blank'}</dd></div>
                <div><dt style={{ color: 'var(--text-muted)' }}>{t('browserStatusElapsed')}</dt><dd style={{ margin: '2px 0', color: statusColor(selected.status) }}>{selected.status} · {((selected.status === 'running' ? Math.max(0, Date.now() - new Date(selected.started_at).getTime()) : selected.elapsed_ms) / 1000).toFixed(1)}s</dd></div>
                {!frame && selected.status === 'running' && <div style={{ color: 'var(--text-muted)' }}>{t('chromiumFrameNote')}</div>}
              </dl>
            </div>
          )}
          {failureWorkspace}
        </div>
      )}
    </section>
  );
};
