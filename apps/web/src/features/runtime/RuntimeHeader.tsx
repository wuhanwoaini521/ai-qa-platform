import { useEffect, useState } from 'react';
import { Activity, Clock3 } from 'lucide-react';
import type { RuntimeSnapshot } from '../../types/runtime';
import {
  currentSteps,
  durationLabel,
  runtimeActive,
  spanDuration,
} from './runtimeModel';

export function RuntimeHeader({
  snapshot,
  connection,
}: {
  snapshot: RuntimeSnapshot;
  connection: string;
}) {
  const [now, setNow] = useState(Date.now);
  const active = runtimeActive(snapshot.status);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  const current = currentSteps(snapshot)
    .map((step) => step.key)
    .join(' · ');
  const metrics = [
    [
      '当前步骤',
      current || (snapshot.kind === 'run' && active ? snapshot.status : '—'),
    ],
    [
      '步骤',
      `${snapshot.summary.completed_steps} / ${snapshot.summary.total_steps}`,
    ],
    ['耗时', durationLabel(spanDuration(snapshot, now))],
    ['失败位置', snapshot.summary.failures],
    ['重试', snapshot.summary.retries],
    ['AI Calls', snapshot.summary.ai_calls ?? '—'],
    ['制品', snapshot.summary.artifacts],
  ];
  return (
    <header className="rt-header">
      <div className="rt-heading">
        <div>
          <span className="rt-eyebrow">
            <Activity size={13} aria-hidden="true" /> EXECUTION OBSERVATORY
          </span>
          <h2 title={snapshot.title}>{snapshot.title}</h2>
          <code>{snapshot.id}</code>
        </div>
        <div className="rt-status-stack">
          <span
            role="status"
            className={`rt-status status-${snapshot.status.toLowerCase()}`}
          >
            {active && <span className="rt-pulse" />}
            {snapshot.status}
          </span>
          <small>
            {snapshot.task?.type ?? 'TestRun'} · {connection}
          </small>
        </div>
      </div>
      <dl className="rt-metrics">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <dt>
              {label === '耗时' && <Clock3 size={11} aria-hidden="true" />}{' '}
              {label}
            </dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </header>
  );
}
