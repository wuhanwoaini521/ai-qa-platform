import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Activity,
  Bot,
  CircleAlert,
  File,
  Globe,
  GitBranch,
  ShieldCheck,
} from 'lucide-react';
import type { RuntimeEvent } from '../../types/runtime';
import { durationLabel } from './runtimeModel';
import { EVENT_ROW_HEIGHT, eventWindow, nearEventTail } from './eventWindow';
import { eventLabelKey } from './traceSummaryModel';

const icons = {
  ai: Bot,
  decision: ShieldCheck,
  browser: Globe,
  failure: CircleAlert,
  artifact: File,
  step: GitBranch,
};
export function RuntimeEventStream({
  events,
  onSelect,
  truncated,
}: {
  events: RuntimeEvent[];
  onSelect: (id: string) => void;
  truncated: boolean;
}) {
  const { t } = useTranslation('runtime');
  const viewport = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  const [open, setOpen] = useState(true);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(192);
  const recent = events.slice(-30);
  const latest = recent.at(-1)?.id;
  const range = eventWindow(recent.length, scrollTop, viewportHeight);
  useEffect(() => {
    const element = viewport.current;
    if (!open || !element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() =>
      setViewportHeight(element.clientHeight),
    );
    observer.observe(element);
    setViewportHeight(element.clientHeight);
    return () => observer.disconnect();
  }, [open]);
  useEffect(() => {
    if (follow && open && viewport.current)
      viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [latest, follow, open, viewportHeight]);
  return (
    <details
      className="rt-event-stream"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <span>
          <Activity size={13} aria-hidden="true" />
          {t('liveEventStream')}
        </span>
        <code>
          {recent.length}
          {truncated ? ` · ${t('recentRecords')}` : ''}
        </code>
      </summary>
      {!follow && (
        <button className="rt-resume" onClick={() => setFollow(true)}>
          {t('resumeLive')}
        </button>
      )}
      {!recent.length ? (
        <p className="rt-muted rt-event-empty">{t('noEvents')}</p>
      ) : (
        <div
          ref={viewport}
          className="rt-event-viewport"
          role="region"
          tabIndex={0}
          aria-label={t('liveEventStream')}
          onScroll={(event) => {
            const element = event.currentTarget;
            setScrollTop(element.scrollTop);
            setFollow(
              nearEventTail(
                element.scrollTop,
                element.clientHeight,
                element.scrollHeight,
              ),
            );
          }}
        >
          <div
            role="list"
            style={{ height: range.height, position: 'relative' }}
          >
            {recent.slice(range.start, range.end).map((event, index) => {
              const Icon =
                icons[event.category as keyof typeof icons] ?? Activity;
              const labelKey = eventLabelKey(event.type);
              const label = labelKey ? t(labelKey) : event.title || event.type;
              let summary = event.summary;
              if (event.type === 'browser.recent_steps') {
                const action = typeof event.metadata.action === 'string' ? event.metadata.action : '';
                const locator = typeof event.metadata.locator === 'string' ? event.metadata.locator : '';
                const actionLabel = action
                  ? t(`browserActions.${action.toLowerCase()}`, { defaultValue: action })
                  : '';
                const status = event.status
                  ? t(event.status === 'WAITING_FOR_APPROVAL' ? 'waitingApproval' : event.status.toLowerCase(), { defaultValue: event.status })
                  : '';
                summary = [actionLabel, locator, status].filter(Boolean).join(' · ') || summary;
              }
              const statusLabel = event.status
                ? t(event.status === 'WAITING_FOR_APPROVAL' ? 'waitingApproval' : event.status.toLowerCase(), { defaultValue: event.status })
                : '';
              const timingLabel = event.duration_ms == null ? '' : durationLabel(event.duration_ms);
              const statusAndTiming = [statusLabel, timingLabel].filter(Boolean).join(' · ') || '—';
              return (
                <div
                  role="listitem"
                  className={`rt-event-row category-${event.category}`}
                  key={event.id}
                  style={{
                    position: 'absolute',
                    top: (range.start + index) * EVENT_ROW_HEIGHT,
                    height: EVENT_ROW_HEIGHT,
                    width: '100%',
                  }}
                >
                  <time>
                    {event.timestamp
                      ? new Date(event.timestamp).toLocaleTimeString()
                      : '—'}
                  </time>
                  <Icon size={12} aria-hidden="true" />
                  <span className="rt-event-category">{t(`category_${event.category}`)}</span>
                  <button
                    disabled={!event.step_id}
                    onClick={() => event.step_id && onSelect(event.step_id)}
                    title={`${event.title}${summary ? ' · ' + summary : ''}`}
                  >
                    {label}
                    {summary && ` · ${summary}`}
                  </button>
                  <code
                    className={event.status === 'FAILED' ? 'status-failed' : ''}
                  >
                    {statusAndTiming}
                  </code>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </details>
  );
}
