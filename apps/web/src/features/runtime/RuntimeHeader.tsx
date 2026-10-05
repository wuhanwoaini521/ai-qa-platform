import { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import type { RuntimeSnapshot } from '../../types/runtime';
import { currentSteps, durationLabel, runtimeActive, spanDuration, stepCounts } from './runtimeModel';

function statusLabel(status: string, t: (key: string) => string) {
  const labels: Record<string, string> = {
    BLOCKED: 'blocked', RUNNING: 'running', WAITING: 'waitingApproval', WAITING_FOR_APPROVAL: 'waitingApproval',
    COMPLETED: 'completed', PASSED: 'completed', FAILED: 'failed', CANCELLED: 'cancelled',
  };
  return t(labels[status] ?? status);
}

export function RuntimeHeader({ snapshot, connection }: { snapshot: RuntimeSnapshot; connection: string }) {
  const { t } = useTranslation('runtime');
  const [now, setNow] = useState(Date.now);
  const active = runtimeActive(snapshot.status);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);

  const counts = stepCounts(snapshot);
  const blocking = snapshot.blocking;
  const blockedStep = blocking?.step_key ?? currentSteps(snapshot)[0]?.key;
  const duration = durationLabel(spanDuration(snapshot, now));
  const taskType = snapshot.task?.type === 'FIX_FAILURE' ? t('fixFailure') : snapshot.task?.type;
  const metrics = [
    [t('completedCount'), counts.completed],
    [t('failedCount'), counts.failed],
    [t('pendingCount'), counts.remaining],
    ...(counts.skipped ? [[t('skipped'), counts.skipped]] : []),
    [t('duration'), duration],
    [t('aiCalls'), snapshot.summary.ai_calls ?? '—'],
    [t('retries'), snapshot.summary.retries],
    [t('artifacts'), snapshot.summary.artifacts],
  ];

  return (
    <header className="rt-header">
      <div className="rt-header-main">
        <div className="rt-header-title">
          <span className="rt-eyebrow"><Activity size={13} aria-hidden="true" /> {t('observatory')}</span>
          <h2 title={snapshot.title}>{snapshot.title}</h2>
          <div className="rt-header-context">
            {taskType && <span>{taskType}</span>}
            {snapshot.status === 'BLOCKED' && blockedStep && <span>{t('blockedAt')}: <code>{blockedStep}</code></span>}
            {snapshot.runs.map((run) => <Link key={run.id} to={`/runs/${run.id}`} title={`${t('testRun')} #${run.id}`}>{t('testRun')} #{run.id}</Link>)}
            <code title={snapshot.id}>{snapshot.id}</code>
          </div>
        </div>
        <div className="rt-header-status">
          <span role="status" className={`rt-status status-${snapshot.status.toLowerCase()}`}>
            {active && <span className="rt-pulse" />}
            {statusLabel(snapshot.status, t)}
          </span>
          <small>{t(connection)}</small>
        </div>
      </div>
      <dl className="rt-metrics">
        {metrics.map(([label, value]) => (
          <div key={String(label)}><dt>{label}</dt><dd>{value}</dd></div>
        ))}
      </dl>
    </header>
  );
}
