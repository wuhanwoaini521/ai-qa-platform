import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, ChevronDown, Circle, LoaderCircle, ShieldAlert, StopCircle } from 'lucide-react';
import { AITraceEvent } from '../types';

interface AIExecutionTimelineProps {
  events: AITraceEvent[];
  running: boolean;
  onCancel?: () => void;
  debugMode?: boolean;
}

const STARTED_TO_COMPLETED: Record<string, string> = {
  'run.started': 'run.completed',
  'model.started': 'model.completed',
  'decision.started': 'decision.completed',
  'validation.started': 'validation.completed',
};

const EVENT_LABELS: Record<string, string> = {
  'run.started': 'traceStarted',
  'context.loaded': 'traceContextLoaded',
  'evidence.collected': 'traceEvidenceCollected',
  'tool.started': 'traceToolStarted',
  'tool.completed': 'traceToolCompleted',
  'tool.failed': 'traceToolFailed',
  'decision.started': 'traceDecisionStarted',
  'decision.completed': 'traceDecisionCompleted',
  'model.started': 'traceModelStarted',
  'model.completed': 'traceModelCompleted',
  'validation.started': 'traceValidationStarted',
  'validation.completed': 'traceValidationCompleted',
  'validation.failed': 'traceValidationFailed',
  'run.completed': 'traceRunCompleted',
  'run.failed': 'traceRunFailed',
  'run.cancelled': 'traceRunCancelled',
};

export const AIExecutionTimeline: React.FC<AIExecutionTimelineProps> = ({
  events,
  running,
  onCancel,
  debugMode = false,
}) => {
  const { t } = useTranslation('studioPanels');
  const [expanded, setExpanded] = useState(true);
  const visibleEvents = useMemo(() => events.filter((event) => event.type !== 'model.delta'), [events]);
  if (!visibleEvents.length) return null;

  const latestModelEvent = [...events].reverse().find((event) => typeof event.metadata?.provider === 'string' || typeof event.metadata?.model === 'string');
  const modelMetadata = latestModelEvent?.metadata ?? {};
  const provider = typeof modelMetadata.provider === 'string' ? modelMetadata.provider : '';
  const model = typeof modelMetadata.model === 'string' ? modelMetadata.model : '';
  const fallback = modelMetadata.fallback_used === true || ['fake', 'local-policy', 'fallback'].includes(provider);
  const failure = [...events].reverse().find((event) => event.type === 'run.failed');
  const providerUnavailable = Boolean(failure) && !fallback;
  const cancelled = [...events].reverse().find((event) => event.type === 'run.cancelled');

  const getState = (event: AITraceEvent, index: number): 'done' | 'active' | 'error' | 'pending' => {
    if (event.type === 'run.failed') return 'error';
    if (event.type === 'run.cancelled') return 'pending';
    const completionType = STARTED_TO_COMPLETED[event.type];
    if (completionType) {
      const completeIndex = visibleEvents.findIndex((candidate, candidateIndex) => candidateIndex > index && candidate.type === completionType);
      if (completeIndex >= 0) return 'done';
      if (running) return 'active';
      return 'pending';
    }
    if (event.type.endsWith('.completed') || event.type.endsWith('.collected') || event.type.endsWith('.loaded')) return 'done';
    if (event.type.endsWith('.failed')) return 'error';
    return 'pending';
  };

  return (
    <section className="ai-execution" aria-label={t('assistant.aiExecution')}>
      <div className="ai-execution-heading">
        <div className="ai-execution-heading-main">
          <span className="ai-execution-title">{running ? t('assistant.aiAnalyzing') : t('assistant.aiExecution')}</span>
          {(provider || model) && (
            <span className={`ai-provider-badge${providerUnavailable ? ' is-unavailable' : fallback ? ' is-fallback' : ' is-real'}`}>
              {providerUnavailable ? t('assistant.providerUnavailable') : fallback ? t('assistant.fallbackMode') : t('assistant.realProvider')}
              {[provider, model].filter(Boolean).join(' · ') && ` · ${[provider, model].filter(Boolean).join(' · ')}`}
            </span>
          )}
        </div>
        {running && onCancel && (
          <button type="button" className="btn btn-secondary btn-sm ai-cancel" onClick={onCancel}>
            <StopCircle size={13} aria-hidden="true" /> {t('assistant.cancel')}
          </button>
        )}
      </div>

      <details open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)} className="ai-execution-details">
        <summary>
          <ChevronDown size={13} aria-hidden="true" /> {expanded ? t('assistant.hideTimeline') : t('assistant.showTimeline')}
        </summary>
        <ol className="ai-execution-list">
          {visibleEvents.map((event, index) => {
            const state = getState(event, index);
            const detail = event.message && !event.message.includes('evidence source') && event.type !== 'run.failed' ? event.message : '';
            const Icon = state === 'done' ? Check : state === 'active' ? LoaderCircle : state === 'error' ? ShieldAlert : Circle;
            return (
              <li key={event.event_id} className={`ai-execution-step is-${state}`}>
                <Icon size={14} aria-hidden="true" />
                <div>
                  <strong>{EVENT_LABELS[event.type] ? t(`assistant.${EVENT_LABELS[event.type]}`) : event.title}</strong>
                  {detail && <small>{detail}</small>}
                  {event.type === 'run.failed' && event.message && <code>{event.message}</code>}
                  {debugMode && Object.keys(event.metadata ?? {}).length > 0 && (
                    <details className="ai-trace-debug"><summary>{t('assistant.eventMetadata')}</summary><pre>{JSON.stringify(event.metadata, null, 2)}</pre></details>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </details>

      {fallback && (
        <p className="ai-fallback-notice" role="status">
          {t(provider === 'local-policy' || provider === 'fallback' ? 'assistant.localFallbackMessage' : 'assistant.fakeFallbackMessage', { model: model || provider || 'fake-qa-model' })}
        </p>
      )}
      {failure && (
        <p className="ai-execution-error" role="alert">
          {t('assistant.traceRunFailed')}: {failure.message || t('assistant.providerUnavailable')}
        </p>
      )}
      {cancelled && <p className="ai-execution-muted" role="status">{t('assistant.cancelled')}</p>}
      {!running && !failure && events.some((event) => event.type === 'model.delta') && !events.some((event) => event.type === 'run.completed') && (
        <p className="ai-execution-muted" role="status">{t('assistant.interruptedPartial')}</p>
      )}
    </section>
  );
};
