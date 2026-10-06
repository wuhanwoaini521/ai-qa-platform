import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AIExecutionTimeline } from '../../components/AIExecutionTimeline';
import type { RuntimeSnapshot } from '../../types/runtime';
import { durationLabel, runtimeActive } from './runtimeModel';
import { TRACE_FILTERS, filterTrace, traceAdapter, type TraceFilter } from './traceModel';
import { eventLabelKey, summarizeTrace } from './traceSummaryModel';

export function RuntimeTrace({ snapshot, selectedStepId, onSelect }: {
  snapshot: RuntimeSnapshot;
  selectedStepId: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation('runtime');
  const [filter, setFilter] = useState<TraceFilter>('All');
  const [errors, setErrors] = useState(false);
  const [mode, setMode] = useState<'Summary' | 'Raw'>('Summary');
  const filtered = useMemo(() => filterTrace(snapshot.events, filter, errors, selectedStepId), [snapshot.events, filter, errors, selectedStepId]);
  const groups = useMemo(() => summarizeTrace(filtered, snapshot), [filtered, snapshot.steps]);
  const invocations = snapshot.ai_invocations.filter((call) =>
    (filter === 'All' || filter === 'AI') && (!selectedStepId || call.step_id === selectedStepId) &&
    (!errors || ['FAILED', 'ERROR', 'BLOCKED'].includes(call.status.toUpperCase())),
  );

  return (
    <section className="rt-trace" aria-label={t('traceLabel')}>
      <div className="rt-trace-toolbar">
        <div className="rt-segmented" role="group" aria-label={t('traceMode')}>
          <button aria-pressed={mode === 'Summary'} onClick={() => setMode('Summary')}>{t('summary')}</button>
          <button aria-pressed={mode === 'Raw'} onClick={() => setMode('Raw')}>{t('raw')}</button>
        </div>
        <div className="rt-segmented" role="group" aria-label={t('traceFilter')}>
          {TRACE_FILTERS.map((key) => <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>{key === 'All' ? t('all') : t(`category_${key.toLowerCase()}`)}</button>)}
        </div>
        <label className="rt-errors-filter"><input type="checkbox" checked={errors} onChange={(event) => setErrors(event.target.checked)} />{t('onlyErrors')}</label>
      </div>
      {mode === 'Raw' ? (
        filtered.length ? <AIExecutionTimeline events={filtered.map(traceAdapter)} running={runtimeActive(snapshot.status)} runtime selectedStepId={selectedStepId} onSelectStep={onSelect} /> : <p className="rt-empty">{t('noData')}</p>
      ) : groups.length || invocations.length ? (
        <ol className="rt-trace-list">
          {groups.map((group) => {
            const step = snapshot.steps.find((item) => item.id === group.stepId);
            const timestamp = group.timestamp ? new Date(group.timestamp).toLocaleTimeString() : '—';
            const provider = [...new Set(group.events.map((event) => [event.metadata.provider, event.metadata.model].filter((part): part is string => typeof part === 'string' && Boolean(part)).join(' · ')).filter(Boolean))];
            const title = group.id === 'lifecycle:task' ? t('taskStarted') : group.title;
            const status = group.status ?? (step?.status ?? '');
            return <li key={group.id} className={`rt-trace-group status-${status.toLowerCase()}${group.stepId === selectedStepId ? ' is-selected' : ''}`}>
              <div className="rt-trace-group-main">
                <time>{timestamp}</time>
                {step ? <button className="rt-trace-select" onClick={() => onSelect(step.id)}><span>{status === 'FAILED' ? '✕' : status === 'COMPLETED' ? '✓' : '•'}</span><strong>{step.key}</strong><span>{title}</span></button> : <div className="rt-trace-select"><strong>{title}</strong></div>}
                <span className={`rt-trace-status status-${status.toLowerCase()}`}>{status ? t(status === 'WAITING_FOR_APPROVAL' ? 'waitingApproval' : status.toLowerCase(), { defaultValue: status }) : '—'}</span>
                <code>{group.durationMs == null ? '—' : durationLabel(group.durationMs)}</code>
              </div>
              {group.id === 'lifecycle:task' && <p className="rt-trace-summary-line">{snapshot.task?.type ?? snapshot.kind} · {snapshot.steps.length} {t('plannedSteps')}</p>}
              {group.evidenceCount > 0 && <p className="rt-trace-summary-line">{t('evidence')}: {group.evidenceCount} {t('itemsCount')}</p>}
              {step?.error && <p className="rt-trace-error">{step.error}</p>}
              {step?.validation_error && <p className="rt-trace-error">{step.validation_error}</p>}
              {provider.length > 0 && <p className="rt-trace-summary-line">{provider.join(' → ')}</p>}
              <details className="rt-trace-raw-events"><summary>{group.events.length} {t('events')}</summary><ul>{group.events.map((event) => { const labelKey = eventLabelKey(event.type); return <li key={event.id}><time>{event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : '—'}</time><span>{labelKey ? t(labelKey) : event.title || event.type}</span><code>{event.type}</code>{event.summary && <small>{event.summary}</small>}</li>; })}</ul></details>
            </li>;
          })}
          {invocations.map((call) => <li key={`ai:${call.id}`} className={`rt-trace-group status-${call.status.toLowerCase()}${call.step_id === selectedStepId ? ' is-selected' : ''}`}>
            <div className="rt-trace-group-main"><time>{call.started_at ? new Date(call.started_at).toLocaleTimeString() : '—'}</time>{call.step_id ? <button className="rt-trace-select" onClick={() => onSelect(call.step_id!)}><strong>AI</strong><span>{call.title}</span></button> : <div className="rt-trace-select"><strong>AI</strong><span>{call.title}</span></div>}<span className={`rt-trace-status status-${call.status.toLowerCase()}`}>{t(call.status === 'WAITING_FOR_APPROVAL' ? 'waitingApproval' : call.status.toLowerCase(), { defaultValue: call.status })}</span><code>{durationLabel(call.duration_ms)}</code></div>
          </li>)}
        </ol>
      ) : <p className="rt-empty">{t('noData')}</p>}
    </section>
  );
}
