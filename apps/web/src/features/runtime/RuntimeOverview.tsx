import { Check, Circle, Play, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import type { RuntimeSnapshot, RuntimeStep } from '../../types/runtime';
import { durationLabel, nextAction, overviewFacts, retryActionLabel, runtimeActive, runtimeStatusKey } from './runtimeModel';

function StepMark({ status }: { status: string }) {
  const Icon = status === 'COMPLETED' ? Check : status === 'FAILED' ? ShieldAlert : status === 'RUNNING' ? Play : Circle;
  return <Icon size={13} aria-hidden="true" />;
}

export function RuntimeOverview({
  snapshot,
  onOpenFlow,
  onSelectStep,
}: {
  snapshot: RuntimeSnapshot;
  onOpenFlow?: () => void;
  onSelectStep: (stepId: string) => void;
}) {
  const { t } = useTranslation('runtime');
  const facts = overviewFacts(snapshot);
  const active = runtimeActive(snapshot.status);
  const next = nextAction(snapshot);
  const blocker = snapshot.blocking;
  const retryLabel = retryActionLabel(snapshot.task?.type);
  const blockerStep = snapshot.steps.find((step) => step.id === blocker?.step_id);
  const failed = facts.failed[0];
  const relatedAi = snapshot.ai_invocations.filter((call) => call.step_id === blocker?.step_id);
  const testState = snapshot.runs.length ? 'started' : snapshot.status === 'BLOCKED' ? 'notReached' : 'notStarted';
  const agentProgress = [...snapshot.events].reverse().find((event) => event.type === 'browser.agent_progress');
  const actionLifecycle = snapshot.events.filter((event) => ['browser.action_started', 'browser.action_completed', 'browser.action_blocked'].includes(event.type));
  const lastActionEvent = actionLifecycle[actionLifecycle.length - 1];
  const agentAction = lastActionEvent?.type === 'browser.action_started' ? lastActionEvent : undefined;
  const agentResult = [...snapshot.events].reverse().find((event) => ['browser.action_completed', 'browser.action_blocked'].includes(event.type));
  const summaryLines = [
    facts.counts.completed > 0 && facts.counts.failed > 0,
    snapshot.status === 'BLOCKED' && blocker?.failure_type === 'AI_OUTPUT_INVALID',
    snapshot.status === 'BLOCKED' && !snapshot.steps.some((step) => ['source.write_generated', 'source.apply_repair'].includes(step.tool) && step.status === 'COMPLETED'),
  ];

  return (
    <div className="rt-overview">
      <section className="rt-overview-state">
        <div className="rt-overview-state-copy">
          <span className="rt-eyebrow">{t('currentState')}</span>
          <div className="rt-overview-status"><span className={`rt-status status-${snapshot.status.toLowerCase()}`}>{t(runtimeStatusKey(snapshot.status))}</span>
            {blockerStep && <button className="rt-inline-step" onClick={() => onSelectStep(blockerStep.id)}><code>{t('blockedAt')} · {blockerStep.key}</code></button>}
          </div>
          {snapshot.status === 'BLOCKED' && blocker?.reason && <p className="rt-blocker-reason">{blocker.reason}</p>}
          {snapshot.status === 'BLOCKED' && snapshot.task?.type === 'FIX_FAILURE' && snapshot.runs.length === 0 && <p className="rt-not-reached">{t('testNotStarted')}</p>}
          {snapshot.status !== 'BLOCKED' && (blocker?.reason || blockerStep?.error) && <p>{blocker?.reason ?? blockerStep?.error}</p>}
          {snapshot.status !== 'BLOCKED' && !blockerStep && <p>{facts.active.map((step) => step.title).join(' · ') || (active ? t('running') : t('completed'))}</p>}
        </div>
        <div className="rt-next-action">
          <span className="rt-eyebrow">{t('nextAction')}</span>
          <strong>{next === 'retry' ? t(retryLabel) : next === 'replan' ? t('replan') : next === 'approval' ? t('approvalRequired') : next === 'run_next' ? t('running') : next === 'running' ? t('running') : next === 'none' ? t('noNextAction') : t('unknown')}</strong>
          {blockerStep && <button className="btn btn-secondary btn-sm" onClick={() => onSelectStep(blockerStep.id)}>{t('inspectOutput')}</button>}
        </div>
      </section>

      <section className="rt-overview-progress rt-block">
        <div className="rt-section-heading"><h3>{t('progress')}</h3><span className="rt-count-summary">{facts.counts.completed} {t('completedCount')} · {facts.counts.failed} {t('failedCount')} · {facts.counts.remaining} {t('pendingCount')}{facts.counts.blocked ? ` (${facts.counts.blocked} ${t('blockedCount')})` : ''}</span></div>
        <div className="rt-progress-segments" role="img" aria-label={t('progressAria', { completed: facts.counts.completed, failed: facts.counts.failed, pending: facts.counts.remaining })}>
          {snapshot.steps.map((step) => <span key={step.id} className={`rt-progress-segment status-${step.status.toLowerCase()}`} title={`${step.key} · ${step.status}`} />)}
        </div>
        <ol className="rt-step-list">
          {snapshot.steps.map((step: RuntimeStep) => {
            const downstream = facts.counts.blockedStepIds.includes(step.id);
            return <li key={step.id} className={`status-${step.status.toLowerCase()}${downstream ? ' is-blocked-downstream' : ''}`}>
              <button onClick={() => onSelectStep(step.id)} title={`${step.title} · ${t(runtimeStatusKey(step.status))}`} aria-label={`${step.key}, ${t(runtimeStatusKey(step.status))}`}>
                <StepMark status={step.status} /><code>{step.key}</code><span>{step.title}</span>
                {step.status === 'FAILED' && snapshot.status === 'BLOCKED' && <small>{t('blockedHere')}</small>}
                {downstream && <small>{t('blockedBy', { step: snapshot.blocking?.step_key })}</small>}
              </button>
            </li>;
          })}
        </ol>
        {onOpenFlow && snapshot.steps.length > 0 && <button className="btn btn-secondary btn-sm" onClick={onOpenFlow}>{t('openFlow')}</button>}
      </section>

      {snapshot.task?.type === 'EXPLORE_PAGE' && (agentProgress || agentAction || agentResult) && <section className="rt-block">
        <h3>QA Agent</h3>
        <div className="rt-inline-meta"><span>{t('currentGoal')}</span><span>{snapshot.title}</span></div>
        {agentAction && <div className="rt-inline-meta"><span>{t('currentAction')}</span><span>{agentAction.title}</span></div>}
        {agentResult && <div className="rt-inline-meta"><span>{t('recentResult')}</span><span>{agentResult.summary || agentResult.title}</span></div>}
        {!agentResult && agentProgress?.summary && <p>{agentProgress.summary}</p>}
      </section>}

      <div className="rt-overview-grid">
        <section className="rt-block rt-summary-block">
          <h3>{t('executionSummary')}</h3>
          {summaryLines[0] && <p>{t('stepsBeforeFailure', { count: facts.counts.completed, step: failed?.key ?? '—' })}</p>}
          {summaryLines[1] && !blocker?.reason && <p>{t('repairFailed')}</p>}
          {summaryLines[2] && <p>{t('sourceUnchanged')}</p>}
          {!summaryLines.some(Boolean) && <p className="rt-muted">{facts.active.map((step) => step.title).join(' · ') || snapshot.title}</p>}
          <div className="rt-inline-meta"><span>{t('browser')}</span><span>{snapshot.browser_sessions.length ? t('sessionCount', { count: snapshot.browser_sessions.length }) : t('browserUnused')}</span></div>
          <div className="rt-inline-meta"><span>{t('testRun')}</span><span>{testState === 'started' ? t('runCount', { count: snapshot.runs.length }) : t(testState)}</span></div>
          {snapshot.runs.map((run) => <div className="rt-inline-meta" key={run.id}><Link to={`/runs/${run.id}`}>{t('testRun')} #{run.id}</Link><span>{t(runtimeStatusKey(run.status), { defaultValue: run.status })}</span></div>)}
        </section>
        <section className="rt-block">
          <h3>{t('runtimeSummary')}</h3>
          <dl className="rt-summary-grid">
            <div><dt>{t('aiTime')}</dt><dd>{facts.aiTimeMs ? durationLabel(facts.aiTimeMs) : '—'}</dd></div>
            <div><dt>{t('evidence')}</dt><dd>{snapshot.evidence.length}</dd></div>
            <div><dt>{t('childRuns')}</dt><dd>{snapshot.runs.length}</dd></div>
            <div><dt>{t('longestStep')}</dt><dd>{facts.slowest ? `${facts.slowest.key} · ${durationLabel(facts.slowest.duration_ms)}` : '—'}</dd></div>
          </dl>
          {snapshot.artifacts.length === 0 ? <p className="rt-empty-note">{t('noArtifacts')} {snapshot.status === 'BLOCKED' && t('noArtifactsReason')}</p> : snapshot.artifacts.slice(0, 4).map((artifact) => <div key={artifact.id} className="rt-inline-meta"><span>{artifact.name}</span><code>{artifact.type}</code></div>)}
        </section>
      </div>

      {!!failed && <section className="rt-block rt-failure-card">
        <div className="rt-section-heading"><h3>{t('failure')}</h3><span className="rt-status status-failed">{blocker?.failure_type ?? 'STEP_FAILED'}</span></div>
        <dl className="rt-failure-facts">
          <div><dt>{t('step')}</dt><dd><code>{failed.key}</code></dd></div>
          <div><dt>{t('tool')}</dt><dd><code>{failed.tool}</code></dd></div>
          <div><dt>{t('attempt')}</dt><dd>{failed.retry_count + 1}</dd></div>
          <div><dt>{t('providerModel')}</dt><dd>{relatedAi.map((call) => call.title).join(' · ') || [failed.ai_provider, failed.ai_model].filter(Boolean).join(' · ') || '—'}</dd></div>
        </dl>
        {failed.validation_error && failed.validation_error !== blocker?.reason && <p><strong>{t('fieldLabels.validation_error')}:</strong> {failed.validation_error}</p>}
        {failed.error && failed.error !== blocker?.reason && !failed.validation_error && <p>{failed.error}</p>}
      </section>}
    </div>
  );
}
