import { useEffect, useState } from 'react';
import { ClipboardCopy, Code2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../../api/client';
import type { RuntimeSnapshot, RuntimeSourceOpener } from '../../types/runtime';
import { durationLabel, inspectorContext, runtimeStatusKey } from './runtimeModel';
import { RuntimeArtifactActions } from './RuntimeArtifactActions';
import { decisionFacts } from './jevModel';
import { AIExecutionTimeline } from '../../components/AIExecutionTimeline';
import { traceAdapter } from './traceModel';

function Fields({ value }: { value: Record<string, unknown> }) {
  const { t } = useTranslation('runtime');
  const copy = async (item: unknown) => {
    try { await navigator.clipboard.writeText(typeof item === 'string' ? item : JSON.stringify(item, null, 2)); } catch { /* Clipboard may be unavailable in insecure contexts. */ }
  };
  const display = (key: string, item: unknown) => item == null ? '—' : typeof item === 'object' ? JSON.stringify(item, null, 2) : key === 'status' && typeof item === 'string' ? t(runtimeStatusKey(item), { defaultValue: item }) : String(item);
  return Object.keys(value).length ? (
    <dl className="rt-inspector-fields">
      {Object.entries(value).map(([key, item]) => (
        <div key={key}>
          <dt>{t(`fieldLabels.${key}`, { defaultValue: key.replaceAll('_', ' ') })}</dt>
          <dd><span>{display(key, item)}</span><button className="rt-copy-button" aria-label={`${t('copy')} ${t(`fieldLabels.${key}`, { defaultValue: key.replaceAll('_', ' ') })}`} title={t('copy')} onClick={() => void copy(item)}><ClipboardCopy size={12} aria-hidden="true" /></button></dd>
        </div>
      ))}
    </dl>
  ) : (
    <p className="rt-muted">{t('dataUnavailable')}</p>
  );
}

export function RuntimeInspector({
  snapshot,
  selectedStepId,
  onClose,
  onOpenSource,
}: {
  snapshot: RuntimeSnapshot;
  selectedStepId: string | null;
  onClose: () => void;
  onOpenSource?: RuntimeSourceOpener;
}) {
  const { t } = useTranslation('runtime');
  const { step, decisions, evidence, artifacts, events, runs } =
    inspectorContext(snapshot, selectedStepId);
  const decisionDetails = decisionFacts(events);
  const [detail, setDetail] = useState<{
    id: string;
    inputs: Record<string, unknown>;
    outputs: Record<string, unknown>;
  } | null>(null);
  const [error, setError] = useState('');
  const taskId = snapshot.task?.id;
  useEffect(() => {
    if (!step || !taskId) return;
    let disposed = false;
    setError('');
    api
      .getRuntimeStep(taskId, step.id)
      .then((value) => {
        if (!disposed) setDetail(value);
      })
      .catch((reason) => {
        if (!disposed) setError(String(reason));
      });
    return () => {
      disposed = true;
    };
  }, [taskId, step?.id, step?.status, step?.finished_at]);
  if (!step) return null;
  const inputs = detail?.id === step.id ? detail.inputs : {};
  const outputs = detail?.id === step.id ? detail.outputs : {};
  const sourcePath = [outputs.file_path, outputs.target_file, inputs.file_path, inputs.path]
    .find((value): value is string => typeof value === 'string' && value.trim().length > 0)
    ?.replaceAll('\\', '/').replace(/^\/+/, '');
  const rawLine = [outputs.line_number, outputs.line, inputs.line_number, inputs.line]
    .find((value) => typeof value === 'number' || (typeof value === 'string' && /^\d+$/.test(value)));
  const sourceLine = typeof rawLine === 'number' ? rawLine : typeof rawLine === 'string' ? Number(rawLine) : 1;
  const nodeId = [outputs.nodeid, outputs.test_nodeid, inputs.nodeid, inputs.test_nodeid]
    .find((value): value is string => typeof value === 'string' && value.length > 0);
  const testCaseId = [outputs.test_case_id, outputs.case_id, inputs.test_case_id, inputs.case_id]
    .find((value): value is string => typeof value === 'string' && value.length > 0);
  const failureId = [outputs.failure_id, inputs.failure_id]
    .find((value): value is string => typeof value === 'string' && value.length > 0);
  const runIds = new Set(runs.map((run) => run.id));
  const sessions = snapshot.browser_sessions.filter((session) => session.step_id === step.id || (session.test_run_id !== null && runIds.has(session.test_run_id)));
  const failures = snapshot.failures.filter((failure) => runIds.has(failure.test_run_id));
  const aiCalls = snapshot.ai_invocations.filter((invocation) => invocation.step_id === step.id);
  return (
    <aside className="rt-inspector" aria-label={t('inspector')}>
      <div className="rt-toolbar">
        <span className="rt-eyebrow">{t('inspector')}</span>
        <button
          className="btn btn-icon btn-sm"
          aria-label={t('closeInspector')}
          title={t('closeInspector')}
          onClick={onClose}
        >
          <X size={14} />
        </button>
      </div>
      <h3>{step.title}</h3>
      <code>{step.key}</code>
      <span className={`rt-status status-${step.status.toLowerCase()}`}>
        {step.status === 'PENDING' ? t('pending') : step.status === 'WAITING_FOR_APPROVAL' ? t('waitingApproval') : t(step.status.toLowerCase())}
      </span>
      {snapshot.status === 'BLOCKED' && snapshot.blocking?.step_id === step.id && <div className="rt-inspector-blocker"><strong>{t('blockedHere')}</strong><code>{snapshot.blocking.failure_type}</code><p>{snapshot.blocking.reason}</p></div>}
      <Fields
        value={{
          tool: step.tool,
          started: step.started_at,
          finished: step.finished_at,
          duration: durationLabel(step.duration_ms),
          retry: step.retry_count,
        }}
      />
      {error && (
        <p className="rt-notice" role="alert">
          {error}
        </p>
      )}
      {sourcePath && onOpenSource && <button
        type="button"
        className="btn btn-secondary btn-sm rt-inspector-open-studio"
        onClick={() => onOpenSource(sourcePath, sourceLine > 0 ? sourceLine : 1, {
          nodeId,
          testCaseId,
          failureId,
          taskId: snapshot.task?.id,
          runId: step.test_run_id ?? snapshot.runs.at(-1)?.id,
        })}
      ><Code2 size={13} aria-hidden="true" />{t('openInStudio')}</button>}
      <section>
        <h4>{t('inputs')}</h4>
        <Fields value={inputs} />
      </section>
      <section>
        <h4>{t('outputs')}</h4>
        <Fields value={outputs} />
      </section>
      {step.failure_type === 'AI_OUTPUT_INVALID' && <section><h4>{t('aiOutputValidation')}</h4><Fields value={Object.fromEntries(Object.entries({ failure_type: step.failure_type, provider: step.ai_provider ?? outputs.provider, model: step.ai_model ?? outputs.model, response_fields: outputs.response_fields, validation_error: step.validation_error ?? outputs.validation_error }).filter(([, value]) => value !== undefined && value !== null))} />{outputs.response_fields == null && outputs.validation_error == null && !step.validation_error && <p className="rt-muted">{t('aiResponseNotPersisted')}</p>}</section>}
      {!!decisions.length && (
        <section>
          <h4>{t('decision')} / JEV</h4>
          {decisions.map((item) => (
            <Fields
              key={item.id}
              value={{
                decision: item.name,
                provider: item.provider,
                selected: item.selected,
                confidence: item.confidence,
              }}
            />
          ))}
        </section>
      )}
      {!!events.some((event) => event.category === 'decision') && (
        <section>
          <h4>{t('decisionValidation')}</h4>
          <h5>{t('candidateGeneration')}</h5>
          <Fields value={decisionDetails.candidateGeneration} />
          {Object.keys(decisionDetails.jevDecision).length > 0 && <>
            <h5>{t('jevDecision')}</h5>
            <p className="rt-muted">{t('jevConfidenceNote')}</p>
            <Fields value={decisionDetails.jevDecision} />
          </>}
          <AIExecutionTimeline
            events={events
              .filter(
                (event) =>
                  event.category === 'decision' ||
                  event.metadata.engine ||
                  event.metadata.verified !== undefined,
              )
              .map(traceAdapter)}
            running={step.status === 'RUNNING'}
            runtime
          />
        </section>
      )}
      {!!events.filter((item) => item.category === 'ai').length && (
        <section>
          <h4>{t('ai')}</h4>
          {events
            .filter((item) => item.category === 'ai')
            .map((item) => (
              <div key={item.id}>
                <strong>{item.title}</strong>
                <Fields value={item.metadata} />
              </div>
            ))}
        </section>
      )}
      {!!aiCalls.length && <section><h4>{t('ai')}</h4>{aiCalls.map((call) => <Fields key={call.id} value={{ provider_and_model: call.title, status: call.status, duration: durationLabel(call.duration_ms), started_at: call.started_at }} />)}</section>}
      {!!evidence.length && (
        <section>
          <h4>{t('evidence')}</h4>
          {evidence.map((item) => (
            <p key={item.id}>
              <strong>{item.type}</strong>
              <small>{item.summary}</small>
            </p>
          ))}
        </section>
      )}
      {!!artifacts.length && (
        <section>
          <h4>{t('artifacts')}</h4>
          {artifacts.map((item) => (
            <div key={item.id}>
              {item.name}
              <RuntimeArtifactActions artifact={item} />
              <small>
                {item.type} ·{' '}
                {item.size_bytes == null ? '—' : `${item.size_bytes} bytes`}
              </small>
            </div>
          ))}
        </section>
      )}
      {!!runs.length && (
        <section>
          <h4>{t('testRun')}</h4>
          {runs.map((item) => (
            <Fields
              key={item.id}
              value={{
                run: item.id,
                status: item.status,
                tests: item.total,
                passed: item.passed,
                failed: item.failed,
                duration: durationLabel(item.duration_ms),
              }}
            />
          ))}
        </section>
      )}
      {!!sessions.length && <section>
        <h4>{t('browser')}</h4>
        {sessions.map((session) => <Fields key={session.id} value={{ session: session.browser_session_id, status: session.status, url: session.current_url, duration: durationLabel(session.duration_ms) }} />)}
      </section>}
      {!!failures.length && <section>
        <h4>{t('failureEvidence')}</h4>
        {failures.map((failure) => <p key={failure.id}>{failure.title} · {failure.classification}<small>{failure.message}</small></p>)}
      </section>}
      {step.error && (
        <section>
          <h4>{t('failure')}</h4>
          <p role="alert">{step.error}</p>
        </section>
      )}
      <section>
        <h4>{t('events')}</h4>
        {events.length ? (
          events.slice(-20).map((item) => (
            <p key={item.id}>
              <time>
                {item.timestamp
                  ? new Date(item.timestamp).toLocaleTimeString()
                  : '—'}
              </time>{' '}
              · {item.title}
              <small>{item.summary}</small>
            </p>
          ))
        ) : (
          <p className="rt-muted">{t('noData')}</p>
        )}
      </section>
      <details>
        <summary>{t('advancedJson')}</summary>
        <pre>{JSON.stringify({ step, inputs, outputs }, null, 2)}</pre>
      </details>
    </aside>
  );
}
