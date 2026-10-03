import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../../api/client';
import type { RuntimeSnapshot } from '../../types/runtime';
import { durationLabel, inspectorContext } from './runtimeModel';
import { RuntimeArtifactActions } from './RuntimeArtifactActions';
import { decisionFacts } from './jevModel';
import { AIExecutionTimeline } from '../../components/AIExecutionTimeline';
import { traceAdapter } from './traceModel';

function Fields({ value }: { value: Record<string, unknown> }) {
  return Object.keys(value).length ? (
    <dl className="rt-inspector-fields">
      {Object.entries(value).map(([key, item]) => (
        <div key={key}>
          <dt>{key.replaceAll('_', ' ')}</dt>
          <dd>
            {item == null
              ? '—'
              : typeof item === 'object'
                ? Array.isArray(item)
                  ? item.join(' · ')
                  : Object.entries(item)
                      .map(([field, data]) => `${field}: ${data}`)
                      .join(' · ')
                : String(item)}
          </dd>
        </div>
      ))}
    </dl>
  ) : (
    <p className="rt-muted">数据暂未记录</p>
  );
}

export function RuntimeInspector({
  snapshot,
  selectedStepId,
  onClose,
}: {
  snapshot: RuntimeSnapshot;
  selectedStepId: string | null;
  onClose: () => void;
}) {
  const { step, decisions, evidence, artifacts, events, runs } =
    inspectorContext(snapshot, selectedStepId);
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
  const runIds = new Set(runs.map((run) => run.id));
  const sessions = snapshot.browser_sessions.filter((session) => session.step_id === step.id || (session.test_run_id !== null && runIds.has(session.test_run_id)));
  const failures = snapshot.failures.filter((failure) => runIds.has(failure.test_run_id));
  return (
    <aside className="rt-inspector" aria-label="Runtime Inspector">
      <div className="rt-toolbar">
        <span className="rt-eyebrow">STEP INSPECTOR</span>
        <button
          className="btn btn-icon btn-sm"
          aria-label="收起 Inspector"
          onClick={onClose}
        >
          <X size={14} />
        </button>
      </div>
      <h3>{step.title}</h3>
      <code>{step.key}</code>
      <span className={`rt-status status-${step.status.toLowerCase()}`}>
        {step.status}
      </span>
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
      <section>
        <h4>Inputs</h4>
        <Fields value={inputs} />
      </section>
      <section>
        <h4>Outputs</h4>
        <Fields value={outputs} />
      </section>
      {!!decisions.length && (
        <section>
          <h4>Decision / JEV</h4>
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
          <h4>决策验证链</h4>
          <Fields value={decisionFacts(events)} />
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
          <h4>AI</h4>
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
      {!!evidence.length && (
        <section>
          <h4>Evidence</h4>
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
          <h4>Artifacts</h4>
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
          <h4>Test</h4>
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
        <h4>Browser</h4>
        {sessions.map((session) => <Fields key={session.id} value={{ session: session.browser_session_id, status: session.status, url: session.current_url, duration: durationLabel(session.duration_ms) }} />)}
      </section>}
      {!!failures.length && <section>
        <h4>失败证据</h4>
        {failures.map((failure) => <p key={failure.id}>{failure.title} · {failure.classification}<small>{failure.message}</small></p>)}
      </section>}
      {step.error && (
        <section>
          <h4>Failure</h4>
          <p role="alert">{step.error}</p>
        </section>
      )}
      <section>
        <h4>Events</h4>
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
          <p className="rt-muted">尚未记录步骤关联事件</p>
        )}
      </section>
      <details>
        <summary>Advanced · 安全 JSON</summary>
        <pre>{JSON.stringify({ step, inputs, outputs }, null, 2)}</pre>
      </details>
    </aside>
  );
}
