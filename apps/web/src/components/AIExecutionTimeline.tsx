import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Check,
  ChevronDown,
  Circle,
  LoaderCircle,
  ShieldAlert,
  StopCircle,
} from 'lucide-react';
import { AITraceEvent } from '../types';
import { traceState } from '../features/runtime/traceState';

interface AIExecutionTimelineProps {
  events: AITraceEvent[];
  running: boolean;
  onCancel?: () => void;
  debugMode?: boolean;
  runtime?: boolean;
  workflowMode?: boolean;
  selectedStepId?: string | null;
  onSelectStep?: (id: string) => void;
}

interface TimelineEntry {
  event: AITraceEvent;
  children: AITraceEvent[];
}

function buildWorkflowTimeline(events: AITraceEvent[]): TimelineEntry[] {
  const hasWorkflowSteps = events.some(
    (event) => event.type === 'workflow.step',
  );
  if (!hasWorkflowSteps) {
    return events
      .filter((event) => event.type !== 'workflow.plan')
      .map((event) => ({ event, children: [] }));
  }

  const entries: TimelineEntry[] = [];
  const byStage = new Map<string, TimelineEntry>();
  let activeEntry: TimelineEntry | null = null;

  for (const event of events) {
    if (event.type === 'workflow.plan') continue;
    if (event.type === 'workflow.step') {
      let entry = byStage.get(event.stage);
      if (!entry) {
        entry = { event, children: [] };
        entries.push(entry);
        byStage.set(event.stage, entry);
      } else {
        entry.event = event;
      }
      if ((event.status ?? '').toUpperCase() === 'RUNNING') activeEntry = entry;
      else if (activeEntry === entry) activeEntry = null;
      continue;
    }
    if (event.type === 'model.progress') {
      const owner = activeEntry ?? byStage.get(event.stage);
      if (owner) {
        owner.event = {
          ...owner.event,
          timestamp: event.timestamp,
          message: event.message,
          metadata: { ...owner.event.metadata, ...event.metadata },
        };
      } else {
        entries.push({ event, children: [] });
      }
      continue;
    }
    if (event.type.startsWith('run.')) {
      entries.push({ event, children: [] });
      activeEntry = null;
      continue;
    }
    const owner = activeEntry ?? byStage.get(event.stage);
    if (owner) owner.children.push(event);
    else entries.push({ event, children: [] });
  }

  return entries;
}

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
  analysis_started: 'traceAnalysisStarted',
  evidence_collected: 'traceEvidenceCollected',
  candidates_generated: 'traceCandidatesGenerated',
  decision_started: 'traceDecisionStarted',
  decision_completed: 'traceDecisionCompleted',
  verification_started: 'traceVerificationStarted',
  verification_completed: 'traceVerificationCompleted',
  diagnosis_completed: 'traceDiagnosisCompleted',
  repair_suggested: 'traceRepairSuggested',
  failed: 'traceFailed',
};

export const AIExecutionTimeline: React.FC<AIExecutionTimelineProps> = ({
  events,
  running,
  onCancel,
  debugMode = false,
  runtime = false,
  workflowMode = false,
  selectedStepId,
  onSelectStep,
}) => {
  const { t } = useTranslation('studioPanels');
  const [expanded, setExpanded] = useState(true);
  const sourceEvents = useMemo(
    () => events.filter(
      (event) => event.type !== 'model.delta' && (workflowMode || event.type !== 'model.progress'),
    ),
    [events, workflowMode],
  );
  const timelineEntries = useMemo(
    () => workflowMode
      ? buildWorkflowTimeline(sourceEvents)
      : sourceEvents.map((event) => ({ event, children: [] })),
    [sourceEvents, workflowMode],
  );
  const visibleEvents = timelineEntries.map((entry) => entry.event);
  if (!visibleEvents.length && !running) return null;

  const latestModelEvent = [...events]
    .reverse()
    .find(
      (event) =>
        typeof event.metadata?.provider === 'string' ||
        typeof event.metadata?.model === 'string',
    );
  const modelMetadata = latestModelEvent?.metadata ?? {};
  const provider =
    typeof modelMetadata.provider === 'string' ? modelMetadata.provider : '';
  const model =
    typeof modelMetadata.model === 'string' ? modelMetadata.model : '';
  const simulation = provider === 'fake';
  const fallback =
    !simulation &&
    (modelMetadata.fallback_used === true ||
      ['local-policy', 'local-strategy', 'fallback'].includes(provider));
  const failure = [...events]
    .reverse()
    .find((event) => event.type === 'run.failed');
  const providerUnavailable = Boolean(failure) && Boolean(provider || model) && !fallback;
  const runtimeLabels: Record<string, string> = { 'run.started': '运行开始', 'run.completed': '运行完成', 'run.failed': '运行失败', 'run.cancelled': '运行取消' };
  const heading = runtime ? '执行 Trace' : t('assistant.aiExecution');
  const cancelled = [...events]
    .reverse()
    .find((event) => event.type === 'run.cancelled');

  return (
    <section className="ai-execution" aria-label={heading}>
      <div className="ai-execution-heading">
        <div className="ai-execution-heading-main">
          <span className="ai-execution-title">
            {runtime ? heading : running ? t('assistant.aiAnalyzing') : heading}
          </span>
          {(provider || model) && (
            <span
              className={`ai-provider-badge${providerUnavailable ? ' is-unavailable' : fallback ? ' is-fallback' : ' is-real'}`}
            >
              {providerUnavailable
                ? t('assistant.providerUnavailable')
                : simulation
                  ? t('assistant.simulationMode')
                  : fallback
                    ? t('assistant.fallbackMode')
                    : t('assistant.realProvider')}
              {[provider, model].filter(Boolean).join(' · ') &&
                ` · ${[provider, model].filter(Boolean).join(' · ')}`}
            </span>
          )}
        </div>
        {running && onCancel && (
          <button
            type="button"
            className="btn btn-secondary btn-sm ai-cancel"
            onClick={onCancel}
          >
            <StopCircle size={13} aria-hidden="true" /> {t('assistant.cancel')}
          </button>
        )}
      </div>

      <details
        open={expanded}
        onToggle={(event) => setExpanded(event.currentTarget.open)}
        className="ai-execution-details"
      >
        <summary>
          <ChevronDown size={13} aria-hidden="true" />{' '}
          {expanded ? t('assistant.hideTimeline') : t('assistant.showTimeline')}
        </summary>
        <ol className="ai-execution-list">
          {!visibleEvents.length && running && (
            <li className="ai-execution-step is-active">
              <LoaderCircle size={14} aria-hidden="true" />
              <div>
                <strong>{t('assistant.waitingProgress')}</strong>
              </div>
            </li>
          )}
          {timelineEntries.map((entry, index) => {
            const event = entry.event;
            const state = traceState(visibleEvents, index, running);
            const detail =
              event.message &&
              !event.message.includes('evidence source') &&
              event.type !== 'run.failed'
                ? event.message
                : '';
            const Icon =
              state === 'done'
                ? Check
                : state === 'active'
                  ? LoaderCircle
                  : state === 'error'
                    ? ShieldAlert
                    : Circle;
            return (
              <li
                key={event.event_id}
                className={`ai-execution-step is-${state}${selectedStepId && event.step_id === selectedStepId ? ' is-selected' : ''}`}
              >
                <Icon size={14} aria-hidden="true" />
                <div>
                  {runtime && (
                    <div className="rt-trace-meta">
                      <time>
                        {event.timestamp
                          ? new Date(event.timestamp).toLocaleTimeString()
                          : '—'}
                      </time>
                      <code>
                        {String(event.metadata.category ?? event.stage)}
                      </code>
                      <code>
                        {event.duration_ms == null
                          ? '—'
                          : `${(event.duration_ms / 1000).toFixed(2)}s`}
                      </code>
                    </div>
                  )}
                  {runtime && event.step_id && onSelectStep ? (
                    <button
                      className="rt-trace-select"
                      onClick={() => onSelectStep(event.step_id!)}
                    >
                      {event.title}
                    </button>
                  ) : (
                    <strong>
                      {workflowMode && event.type === 'workflow.step' ? (
                        t(`assistant.workflowStages.${event.stage}`, {
                          defaultValue: event.title,
                        })
                      ) : runtime && runtimeLabels[event.type] ? (
                        runtimeLabels[event.type]
                      ) : EVENT_LABELS[event.type] ? (
                        t(`assistant.${EVENT_LABELS[event.type]}`)
                      ) : (
                        event.title
                      )}
                    </strong>
                  )}
                  {detail && <small>{detail}</small>}
                  {entry.children.length > 0 && (
                    <details className="ai-workflow-substeps">
                      <summary>{t('assistant.workflowDetails', { count: entry.children.length })}</summary>
                      <ol className="ai-execution-list">
                        {entry.children.map((child, childIndex) => {
                          const childState = traceState(
                            entry.children,
                            childIndex,
                            running && state === 'active',
                          );
                          const ChildIcon =
                            childState === 'done'
                              ? Check
                              : childState === 'active'
                                ? LoaderCircle
                                : childState === 'error'
                                  ? ShieldAlert
                                  : Circle;
                          return (
                            <li
                              key={child.event_id}
                              className={`ai-execution-step is-${childState}`}
                            >
                              <ChildIcon size={14} aria-hidden="true" />
                              <div>
                                <strong>
                                  {EVENT_LABELS[child.type]
                                    ? t(`assistant.${EVENT_LABELS[child.type]}`)
                                    : child.title}
                                </strong>
                                {child.message && <small>{child.message}</small>}
                              </div>
                            </li>
                          );
                        })}
                      </ol>
                    </details>
                  )}
                  {runtime && (
                    <div className="rt-trace-meta">
                      {[
                        'provider',
                        'model',
                        'candidate_count',
                        'candidate_id',
                        'selected_locator',
                        'selected',
                        'confidence',
                        'latency_ms',
                        'verified',
                        'engine',
                        'fallback_used',
                        'fallback_reason',
                        'test_run_id',
                        'nodeid',
                        'url',
                        'action',
                        'locator',
                        'method',
                        'status',
                        'status_code',
                        'level',
                      ]
                        .filter((key) => event.metadata[key] != null)
                        .map((key) => (
                          <span key={key}>
                            {key}: {String(event.metadata[key])}
                          </span>
                        ))}
                    </div>
                  )}
                  {event.type === 'run.failed' && event.message && (
                    <code>{event.message}</code>
                  )}
                  {debugMode &&
                    Object.keys(event.metadata ?? {}).length > 0 && (
                      <details className="ai-trace-debug">
                        <summary>{t('assistant.eventMetadata')}</summary>
                        <pre>{JSON.stringify(event.metadata, null, 2)}</pre>
                      </details>
                    )}
                </div>
              </li>
            );
          })}
        </ol>
      </details>

      {simulation && (
        <p className="ai-fallback-notice" role="status">
          {t('assistant.simulationModeMessage', {
            model: model || provider || 'fake-qa-model',
          })}
        </p>
      )}
      {fallback && (
        <p className="ai-fallback-notice" role="status">
          {t(
            ['local-policy', 'local-strategy', 'fallback'].includes(provider)
              ? 'assistant.localFallbackMessage'
              : 'assistant.fakeFallbackMessage',
            { model: model || provider || 'local-strategy' },
          )}
        </p>
      )}
      {failure && (
        <p className="ai-execution-error" role="alert">
          {t('assistant.traceRunFailed')}:{' '}
          {failure.message || t('assistant.providerUnavailable')}
        </p>
      )}
      {cancelled && (
        <p className="ai-execution-muted" role="status">
          {t('assistant.cancelled')}
        </p>
      )}
      {!running &&
        !failure &&
        events.some((event) => event.type === 'model.delta') &&
        !events.some((event) => event.type === 'run.completed') && (
          <p className="ai-execution-muted" role="status">
            {t('assistant.interruptedPartial')}
          </p>
        )}
    </section>
  );
};
