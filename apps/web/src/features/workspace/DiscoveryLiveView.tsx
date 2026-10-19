import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Activity, Bot, Eye, MonitorPlay, MousePointerClick, Sparkles } from 'lucide-react';
import { api } from '../../api/client';
import {
  foldLiveEvent,
  initialLiveState,
  isTerminalRunStatus,
  overlayBoxes,
  type DiscoveryElement,
  type DiscoveryLiveEvent,
  type DiscoveryLiveState,
} from './discoveryLive';

/**
 * Live workbench for one Quality Discovery run: the run's own browser on the left, what the agent
 * recognised and decided on the right, and the event trace underneath. Everything shown here comes
 * from the run's event stream — when the agent has no evidence yet, the pane says so.
 */
export function DiscoveryLiveView({
  runId,
  status,
  onOpenEvidence,
}: {
  runId: string;
  status: string;
  onOpenEvidence?: (artifactId: string) => void;
}) {
  const { t } = useTranslation('qualityDiscovery');
  const [state, setState] = useState<DiscoveryLiveState>(() => initialLiveState());
  const [selected, setSelected] = useState<number | null>(null);
  const [streamError, setStreamError] = useState('');

  useEffect(() => {
    setState(initialLiveState());
    setSelected(null);
    setStreamError('');
    if (isTerminalRunStatus(status)) {
      setState((prev) => ({ ...prev, status, streamStatus: 'ended' }));
      return;
    }
    let seen = false;
    const close = api.streamQualityDiscoveryEvents(
      runId,
      (payload: DiscoveryLiveEvent) => {
        seen = true;
        setState((prev) => {
          const next = foldLiveEvent(prev, payload);
          return { ...next, streamStatus: isTerminalRunStatus(next.status) ? 'ended' : 'live' };
        });
      },
      () => {
        setStreamError(t('liveStreamError'));
        setState((prev) => (seen ? prev : { ...prev, streamStatus: 'reconnecting' }));
      },
    );
    return () => close();
  }, [runId]);

  const boxes = useMemo(
    () => (state.elementsStale ? [] : overlayBoxes(state.elements, state.viewport)),
    [state.elements, state.elementsStale, state.viewport],
  );
  const selectedElement = useMemo(
    () => state.elements.find((element) => element.index === selected) ?? null,
    [state.elements, selected],
  );
  const evidenceId = (event: DiscoveryLiveEvent): string | null => {
    const ids = event.metadata?.evidence_ids;
    if (Array.isArray(ids) && typeof ids[0] === 'string') return ids[0];
    const single = event.metadata?.artifact_id;
    return typeof single === 'string' ? single : null;
  };

  return (
    <section className="qd-live" aria-label={t('liveView')}>
      <header className="qd-live-bar">
        <span className={`qd-live-stream is-${state.streamStatus}`} role="status">
          <i aria-hidden="true" />{t(`streamStatuses.${state.streamStatus}`)}
        </span>
        <span className="qd-live-url" title={state.url || undefined}>
          <MonitorPlay size={14} aria-hidden="true" />{state.url || t('liveWaiting')}
        </span>
        <span className="qd-live-counters">
          <span>{t('liveCounters.frames')}: {state.counts.frames}</span>
          <span>{t('liveCounters.elements')}: {state.counts.elements}</span>
          <span>{t('liveCounters.actions')}: {state.counts.actions}</span>
          <span>{t('liveCounters.findings')}: {state.counts.findings}</span>
        </span>
        <span className="qd-live-viewport">
          {state.viewport.width}×{state.viewport.height}
        </span>
      </header>

      {streamError && <p className="qd-error" role="alert">{streamError}</p>}
      {state.aiUnavailable && (
        <p className="qd-live-degraded" role="status">
          <Bot size={14} aria-hidden="true" />
          {t('liveAiDegraded', { stage: state.aiUnavailable.stage || '—' })}
        </p>
      )}

      <div className="qd-live-body">
        <div className="qd-live-browser">
          {state.frame ? (
            <div className="qd-live-stage">
              <img className="qd-live-frame" src={state.frame} alt={t('liveFrameAlt')} />
              <div className="qd-live-overlay">
                {boxes.map((box) => (
                  <button
                    type="button"
                    key={box.key}
                    className={`qd-live-box is-${box.tone}${box.index === selected ? ' is-selected' : ''}`}
                    style={{ left: `${box.left}%`, top: `${box.top}%`, width: `${box.width}%`, height: `${box.height}%` }}
                    onClick={() => setSelected(box.index)}
                    title={box.label}
                  >
                    <b>{box.label}</b>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <p className="qd-empty">
              <MonitorPlay size={15} aria-hidden="true" />{t('liveNoFrame')}
            </p>
          )}
          {state.elementsStale && state.elements.length > 0 && (
            <p className="qd-field-hint" role="status">{t('liveStaleElements')}</p>
          )}
        </div>

        <aside className="qd-live-intel" aria-label={t('liveIntelligence')}>
          <div className="qd-live-panel">
            <h4><MousePointerClick size={14} aria-hidden="true" />{t('liveCurrentActivity')}</h4>
            <p>{state.currentAction?.message || t('liveWaitingAction')}</p>
          </div>
          <div className="qd-live-panel">
            <h4><Sparkles size={14} aria-hidden="true" />{t('liveDecision')}</h4>
            {state.decision ? (
              <>
                <p>{state.decision.message || String(state.decision.metadata?.candidate_id ?? '')}</p>
                {typeof state.decision.metadata?.confidence === 'number' && (
                  <small>{t('confidence')}: {Math.round(Number(state.decision.metadata.confidence) * 100)}%</small>
                )}
              </>
            ) : (
              <p className="qd-empty">{t('liveNoDecision')}</p>
            )}
          </div>
          <div className="qd-live-panel is-network">
            <h4><Activity size={14} aria-hidden="true" />{t('liveNetwork')}<span>{state.network?.sample_count ?? 0}</span></h4>
            {state.network === null ? (
              <p className="qd-empty">{t('liveNoNetwork')}</p>
            ) : (
              <ul className="qd-live-network">
                {Object.entries(state.network.responses)
                  .sort(([a], [b]) => Number(a) - Number(b))
                  .map(([status, count]) => (
                    <li key={status}>
                      <span>{status}</span>
                      <strong>{count}</strong>
                    </li>
                  ))}
                <li className={state.network.failures > 0 ? 'is-failed' : undefined}>
                  <span>{t('liveNetworkFailures')}</span>
                  <strong>{state.network.failures}</strong>
                </li>
              </ul>
            )}
          </div>
          <div className="qd-live-panel is-elements">
            <h4><Eye size={14} aria-hidden="true" />{t('liveElements')}<span>{state.elements.length}</span></h4>
            {state.elements.length === 0 ? (
              <p className="qd-empty">{t('liveNoElements')}</p>
            ) : (
              <ul>
                {state.elements.map((element: DiscoveryElement) => (
                  <li key={String(element.index)}>
                    <button
                      type="button"
                      className={element.index === selected ? 'is-selected' : undefined}
                      onClick={() => setSelected(element.index ?? null)}
                    >
                      <span>{element.role || element.tag || '—'}</span>
                      <strong>{element.name || '—'}</strong>
                      <small>{element.bounding_box ? `${Math.round(element.bounding_box.x)},${Math.round(element.bounding_box.y)}` : t('liveNoGeometry')}</small>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>

      {selectedElement && (
        <div className="qd-live-selection" role="region" aria-label={t('liveElementDetails')}>
          <strong>{selectedElement.name || '—'}</strong>
          <span>{selectedElement.role || selectedElement.tag || '—'}</span>
          <span>{t('liveElementLocator')}: {JSON.stringify(selectedElement.locator ?? {})}</span>
        </div>
      )}

      <ol className="qd-live-timeline" aria-label={t('liveTimeline')}>
        {state.timeline.length === 0 && <li className="qd-empty">{t('liveNoEvents')}</li>}
        {state.timeline.slice(0, 40).map((event, index) => (
          <li key={`${event.type}-${event.seq ?? index}-${event.at ?? index}`} className={`is-${event.type.split('.')[0]}`}>
            <time>{event.at ? new Date(event.at).toLocaleTimeString() : ''}</time>
            <span className="qd-live-event-type">{event.type}</span>
            <span className="qd-live-event-message">{event.message || ''}</span>
            {onOpenEvidence && evidenceId(event) && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => onOpenEvidence(evidenceId(event)!)}>
                {t('openEvidence')}
              </button>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
