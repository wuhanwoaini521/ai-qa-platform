import { memo, useEffect, useMemo, useState } from 'react';
import type { RuntimeSnapshot, RuntimeSpan } from '../../types/runtime';
import {
  durationLabel,
  liveSpan,
  runtimeActive,
  spanDuration,
} from './runtimeModel';
import {
  spanBounds,
  timelineDomain,
  timelineRange,
  timelineSpans,
} from './timelineModel';
const TimelineRow = memo(function TimelineRow({
  span,
  origin,
  domain,
  now,
  selected,
  onSelect,
}: {
  span: RuntimeSpan;
  origin: number;
  domain: number;
  now: number;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const bounds = spanBounds(span, now);
  return (
    <div className={`rt-timeline-row${selected ? ' is-selected' : ''}`}>
      <button
        disabled={!span.step_id}
        className="rt-timeline-name"
        onClick={() => span.step_id && onSelect(span.step_id)}
        title={span.title}
      >
        <code>{span.kind}</code>
        {span.title}
      </button>
      <div className="rt-timeline-lane">
        {bounds ? (
          <button
            aria-label={`${span.title} · ${span.status}`}
            disabled={!span.step_id}
            onClick={() => span.step_id && onSelect(span.step_id)}
            className={`rt-span status-${span.status.toLowerCase()}`}
            style={{
              left: `${((bounds.start - origin) / domain) * 100}%`,
              width: `${Math.max(0.3, ((bounds.end - bounds.start) / domain) * 100)}%`,
            }}
          />
        ) : (
          <span className="rt-muted">— 时间暂未记录</span>
        )}
      </div>
      <time title={span.timestamp_source ?? 'recorded'}>
        {durationLabel(spanDuration(span, now))}
        {span.timestamp_source === 'derived' && <small>derived</small>}
      </time>
    </div>
  );
});
export function RuntimeTimeline({
  snapshot,
  selectedStepId,
  onSelect,
}: {
  snapshot: RuntimeSnapshot;
  selectedStepId: string | null;
  onSelect: (id: string) => void;
}) {
  const [now, setNow] = useState(Date.now);
  const [zoom, setZoom] = useState(1);
  const [fitAt, setFitAt] = useState(Date.now);
  const active = runtimeActive(snapshot.status);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  const spans = useMemo(
    () => timelineSpans(snapshot),
    [
      snapshot.task,
      snapshot.steps,
      snapshot.runs,
      snapshot.executions,
      snapshot.browser_sessions,
      snapshot.ai_invocations,
    ],
  );
  const range = useMemo(() => timelineRange(spans, fitAt), [spans, fitAt]);
  const observed = timelineRange(spans, now);
  const domain = timelineDomain(
    range?.duration ?? 30000,
    observed?.duration ?? 30000,
    zoom,
  );
  return (
    <section className="rt-timeline" aria-label="执行时间线">
      <div className="rt-toolbar">
        <div>
          <button
            onClick={() => {
              setZoom(1);
              setFitAt(Date.now());
            }}
          >
            Fit
          </button>
          <button
            aria-label="缩小时间线"
            onClick={() => setZoom((value) => Math.max(0.25, value / 1.5))}
          >
            −
          </button>
          <button
            aria-label="放大时间线"
            onClick={() => setZoom((value) => Math.min(8, value * 1.5))}
          >
            +
          </button>
        </div>
        <code>
          {range ? new Date(range.start).toLocaleTimeString() : '—'} ·{' '}
          {active ? 'LIVE' : 'RECORDED'}
        </code>
      </div>
      {!spans.length ? (
        <p className="rt-empty">尚未记录 TaskStep 时间线</p>
      ) : (
        <div className="rt-timeline-scroll">
          <div className="rt-timeline-body" style={{ minWidth: 700 }}>
            <div className="rt-timeline-axis">
              <span>执行单元</span>
              <div>
                {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
                  <code key={tick} style={{ left: `${tick * 100}%` }}>
                    {((domain * tick) / 1000).toFixed(1)}s
                  </code>
                ))}
              </div>
              <span>Duration</span>
            </div>
            {active && range && (
              <div
                className="rt-time-marker"
                style={{
                  left: `calc(220px + (100% - 310px) * ${Math.min(1, Math.max(0, (now - range.start) / domain))})`,
                }}
                aria-label="当前时间"
              />
            )}
            {spans.map((span) => (
              <TimelineRow
                key={span.id}
                span={span}
                origin={range?.start ?? 0}
                domain={domain}
                now={liveSpan(span) ? now : 0}
                selected={span.step_id === selectedStepId}
                onSelect={onSelect}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
