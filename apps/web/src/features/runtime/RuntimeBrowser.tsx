import { useState } from 'react';
import type { RuntimeSnapshot } from '../../types/runtime';
import { LiveBrowserPanel } from '../runs/LiveBrowserPanel';
import { useRunStore } from '../runs/useRunStore';
import { browserEntries } from './browserModel';
export function RuntimeBrowser({ snapshot, onOpenSource }: { snapshot: RuntimeSnapshot; onOpenSource?: (path: string, line: number) => void }) {
  const [selected, setSelected] = useState('');
  const [channel, setChannel] = useState<
    'recent_steps' | 'network_logs' | 'console_logs'
  >('recent_steps');
  const runId =
    snapshot.runs.find((run) => run.id === selected)?.id ??
    snapshot.runs.at(-1)?.id ??
    null;
  const live = useRunStore(runId);
  const entries = browserEntries(live.sessions, channel);
  return (
    <div className="rt-browser">
      {snapshot.runs.length > 1 && (
        <label>
          TestRun{' '}
          <select
            value={runId ?? ''}
            onChange={(event) => setSelected(event.target.value)}
          >
            {snapshot.runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.id} · {run.status}
              </option>
            ))}
          </select>
        </label>
      )}
      <LiveBrowserPanel
        sessions={live.sessions}
        frames={live.frames}
        runStatus={live.run?.status ?? snapshot.status}
        streamStatus={live.streamStatus}
        streamError={live.error}
      />
      {!runId && (
        <p className="rt-notice">
          此 Task 的浏览器工具尚未记录直播 Session；可在 Artifacts
          查看实际截图证据。
        </p>
      )}
      <div className="rt-toolbar" aria-label="Browser 遥测">
        {(
          [
            ['recent_steps', 'Steps'],
            ['network_logs', 'Network'],
            ['console_logs', 'Console'],
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
        <p className="rt-muted">尚未记录此类浏览器事件</p>
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
    </div>
  );
}
