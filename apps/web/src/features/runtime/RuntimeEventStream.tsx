import { useEffect, useRef, useState } from 'react';
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
  const viewport = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  const [open, setOpen] = useState(true);
  const [scrollTop, setScrollTop] = useState(0);
  const latest = events.at(-1)?.id;
  const window = eventWindow(events.length, scrollTop, 192);
  useEffect(() => {
    if (follow && open && viewport.current)
      viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [latest, follow, open]);
  return (
    <details
      className="rt-event-stream"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <span>
          <Activity size={13} aria-hidden="true" />
          Live Event Stream
        </span>
        <code>
          {events.length}
          {truncated ? ' · 最近记录' : ''}
        </code>
      </summary>
      {!follow && (
        <button className="rt-resume" onClick={() => setFollow(true)}>
          Resume Live
        </button>
      )}
      {!events.length ? (
        <p className="rt-muted rt-event-empty">尚未记录执行事件</p>
      ) : (
        <div
          ref={viewport}
          className="rt-event-viewport"
          tabIndex={0}
          aria-label="实时执行事件"
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
            style={{ height: window.height, position: 'relative' }}
          >
            {events.slice(window.start, window.end).map((event, index) => {
              const Icon =
                icons[event.category as keyof typeof icons] ?? Activity;
              return (
                <div
                  role="listitem"
                  className={`rt-event-row category-${event.category}`}
                  key={event.id}
                  style={{
                    position: 'absolute',
                    top: (window.start + index) * EVENT_ROW_HEIGHT,
                    height: EVENT_ROW_HEIGHT,
                    width: '100%',
                  }}
                >
                  <time>
                    {event.timestamp
                      ? new Date(event.timestamp).toLocaleTimeString()
                      : '—'}
                  </time>
                  <span className="rt-event-source">{event.source}</span>
                  <Icon size={12} aria-hidden="true" />
                  <span className="rt-event-category">{event.category}</span>
                  <button
                    disabled={!event.step_id}
                    onClick={() => event.step_id && onSelect(event.step_id)}
                    title={`${event.title}${event.summary ? ' · ' + event.summary : ''}`}
                  >
                    {event.title}
                    {event.summary && ` · ${event.summary}`}
                  </button>
                  <code
                    className={event.status === 'FAILED' ? 'status-failed' : ''}
                  >
                    {event.duration_ms == null
                      ? (event.status ?? '—')
                      : durationLabel(event.duration_ms)}
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
