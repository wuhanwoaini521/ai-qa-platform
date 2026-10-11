import { memo, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RuntimeSnapshot, RuntimeSpan, RuntimeStep } from '../../types/runtime';
import { durationLabel, liveSpan, runtimeActive, spanDuration } from './runtimeModel';
import { isShortSpan, spanBounds, timelineDomain, timelineGroups, timelineRange } from './timelineModel';

const TimelineRow = memo(function TimelineRow({ span, origin, domain, now, selected, onSelect }: {
  span: RuntimeSpan; origin: number; domain: number; now: number; selected: boolean; onSelect: (id: string) => void;
}) {
  const { t } = useTranslation('runtime');
  const bounds = spanBounds(span, now);
  const step = 'key' in span ? span as RuntimeStep : null;
  const short = isShortSpan(span, now);
  return (
    <div className={`rt-timeline-row${selected ? ' is-selected' : ''}`}>
      <button disabled={!span.step_id} className="rt-timeline-name" onClick={() => span.step_id && onSelect(span.step_id)} title={span.title}>
        <span className={`rt-timeline-icon status-${span.status.toLowerCase()}`}>{span.status === 'COMPLETED' ? '✓' : span.status === 'FAILED' ? '✕' : span.status === 'RUNNING' ? '●' : '○'}</span>
        <span className="rt-timeline-label">{step ? <><code>{step.key}</code><small>{span.title}</small></> : <><small>{span.title}</small><code>{span.kind}</code></>}</span>
      </button>
      <div className="rt-timeline-lane">
        {bounds ? <button aria-label={t('spanLabel', { title: span.title, status: t(span.status === 'WAITING_FOR_APPROVAL' ? 'waitingApproval' : span.status.toLowerCase()) })} title={`${span.title} · ${span.status} · ${short ? '<100ms' : durationLabel(spanDuration(span, now))}`} disabled={!span.step_id} onClick={() => span.step_id && onSelect(span.step_id)} className={`rt-span status-${span.status.toLowerCase()}${short ? ' is-marker' : ''}`} style={{ left: `${((bounds.start - origin) / domain) * 100}%`, width: short ? '2px' : `${Math.max(0.4, ((bounds.end - bounds.start) / domain) * 100)}%` }} /> : <span className="rt-timeline-unknown">—</span>}
      </div>
      <time title={span.timestamp_source === 'derived' ? t('derived') : t('recorded')}>{durationLabel(spanDuration(span, now))}{span.timestamp_source === 'derived' && <small>{t('derived')}</small>}</time>
    </div>
  );
});

export function RuntimeTimeline({ snapshot, selectedStepId, onSelect }: {
  snapshot: RuntimeSnapshot; selectedStepId: string | null; onSelect: (id: string) => void;
}) {
  const { t } = useTranslation('runtime');
  const [now, setNow] = useState(Date.now);
  const [zoom, setZoom] = useState(1);
  const [fitAt, setFitAt] = useState(Date.now);
  const active = runtimeActive(snapshot.status);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  const groups = useMemo(() => timelineGroups(snapshot), [snapshot]);
  const spans = useMemo(() => groups.flatMap((group) => group.spans), [groups]);
  const range = useMemo(() => timelineRange(spans, fitAt), [spans, fitAt]);
  const observed = timelineRange(spans, now);
  const domain = timelineDomain(range?.duration ?? 30000, observed?.duration ?? 30000, zoom);
  const leftColumn = 150;
  const rightColumn = 64;

  return <section className="rt-timeline" aria-label={t('timelineLabel')}>
      <div className="rt-timeline-toolbar">
      <div className="rt-control-group">
        <button onClick={() => { setZoom(1); setFitAt(Date.now()); }}>{t('fit')}</button>
        <button aria-label={t('zoomOut')} title={t('zoomOut')} onClick={() => setZoom((value) => Math.max(0.25, value / 1.5))}>−</button>
        <code>{Math.round(zoom * 100)}%</code>
        <button aria-label={t('zoomIn')} title={t('zoomIn')} onClick={() => setZoom((value) => Math.min(8, value * 1.5))}>+</button>
      </div>
      <span className={`rt-recorded-badge${active ? ' is-live' : ''}`}>{active ? t('live') : t('recorded')}</span>
    </div>
    {!spans.length ? <p className="rt-empty">{t('noTimeline')}</p> : <div className="rt-timeline-scroll">
      <div className="rt-timeline-body">
        <div className="rt-timeline-axis" style={{ gridTemplateColumns: `${leftColumn}px minmax(0, 1fr) ${rightColumn}px` }}>
          <span>{t('step')}</span><div>{[0, 0.25, 0.5, 0.75, 1].map((tick) => <code key={tick} style={{ left: `${tick * 100}%` }}>{((domain * tick) / 1000).toFixed(0)}s</code>)}</div><span>{t('durationLabel')}</span>
        </div>
        {active && range && <div className="rt-time-marker" role="img" aria-label={t('currentTime')} style={{ left: `calc(${leftColumn}px + (100% - ${leftColumn + rightColumn}px) * ${Math.min(1, Math.max(0, (now - range.start) / domain))})` }} />}
        {groups.map((group) => <section className="rt-timeline-group" key={group.key}>
          <h3>{t(`group${group.key[0].toUpperCase()}${group.key.slice(1)}`)}<span>{group.spans.length}</span></h3>
          {group.spans.map((span) => <TimelineRow key={`${span.kind}:${span.id}`} span={span} origin={range?.start ?? 0} domain={domain} now={liveSpan(span) ? now : 0} selected={span.step_id === selectedStepId} onSelect={onSelect} />)}
        </section>)}
      </div>
    </div>}
  </section>;
}
