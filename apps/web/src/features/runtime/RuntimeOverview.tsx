import { Check, Circle, Play, ShieldAlert, Timer } from 'lucide-react';
import type { RuntimeSnapshot } from '../../types/runtime';
import { durationLabel, overviewFacts, runtimeActive } from './runtimeModel';
import { Link } from 'react-router-dom';
import { RuntimeRunResults } from './RuntimeRunResults';

export function RuntimeOverview({
  snapshot,
  onOpenFlow,
}: {
  snapshot: RuntimeSnapshot;
  onOpenFlow?: () => void;
}) {
  const facts = overviewFacts(snapshot);
  const active = runtimeActive(snapshot.status);
  return (
    <div className="rt-overview">
      {snapshot.kind === 'run' && snapshot.task && (
        <Link to={`/runs/tasks?taskId=${encodeURIComponent(snapshot.task.id)}`}>返回工作流 · {snapshot.task.title}</Link>
      )}
      {!!snapshot.run_ancestors?.length && (
        <section className="rt-block">
          <h3>Retry · 父运行链</h3>
          <div className="rt-retry-chain">
            {snapshot.run_ancestors.map((run) => (
              <Link key={run.id} to={`/runs/${run.id}`}>
                {run.id} · {run.status} →
              </Link>
            ))}
            <code>{snapshot.id}</code>
          </div>
        </section>
      )}
      <section className="rt-now">
        <span className="rt-eyebrow">当前执行</span>
        <h3>
          {facts.active.length
            ? facts.active.map((step) => step.title).join(' · ')
            : snapshot.summary.approval
              ? '等待你审批本次变更'
              : active
                ? snapshot.kind === 'run'
                  ? '测试执行正在进行'
                  : '等待调度或依赖完成'
                : snapshot.status === 'COMPLETED' ||
                    snapshot.status === 'PASSED'
                  ? '本次执行已完成'
                  : `本次执行 ${snapshot.status}`}
        </h3>
        <p>
          {facts.active.map((step) => step.tool).join(' · ') || snapshot.id}
        </p>
        <div className="rt-progress">
          <span
            style={{
              width: `${snapshot.summary.total_steps ? (snapshot.summary.completed_steps / snapshot.summary.total_steps) * 100 : 0}%`,
            }}
          />
        </div>
        <small>
          {snapshot.summary.completed_steps} / {snapshot.summary.total_steps}{' '}
          步骤完成{snapshot.summary.approval ? ' · 需要审批' : ''}
        </small>
      </section>
      <div className="rt-overview-grid">
        <section className="rt-block">
          <h3>下一可执行步骤</h3>
          {facts.next.length ? (
            facts.next.map((step) => (
              <p key={step.id}>
                <code>{step.key}</code> · {step.title}
              </p>
            ))
          ) : (
            <p className="rt-muted">
              {active ? '等待依赖完成；没有可执行的后续步骤' : '执行已结束'}
            </p>
          )}
        </section>
        <section className="rt-block">
          <h3>测试执行</h3>
          {snapshot.runs.length ? (
            <>
              <strong className="rt-large-number">
                {facts.tests.passed} <small>/ {facts.tests.total} passed</small>
              </strong>
              <p>
                {facts.tests.failed} failed · {snapshot.runs.length} Run
              </p>
              {snapshot.runs.map((run) => (
                <div className="rt-inline-meta" key={run.id}>
                  <Link to={`/runs/${run.id}`}><code>{run.id}</code></Link>
                  <span>{run.status}</span>
                </div>
              ))}
            </>
          ) : (
            <p className="rt-muted">尚未记录 TestRun</p>
          )}
        </section>
      </div>
      {!!(facts.failed.length || snapshot.failures.length) && (
        <section className="rt-block rt-failure">
          <h3>
            <ShieldAlert size={14} aria-hidden="true" /> 失败位置
          </h3>
          {facts.failed.map((step) => (
            <p key={step.id}>
              <code>{step.key}</code> · {step.error || step.status}
            </p>
          ))}
          {snapshot.failures.map((failure) => (
            <p key={failure.id}>
              <Link to={`/failures/${encodeURIComponent(failure.id)}`}><strong>{failure.title}</strong></Link> · {failure.classification}
              <small>{failure.message}</small>
            </p>
          ))}
        </section>
      )}
      <RuntimeRunResults snapshot={snapshot} />
      <section className="rt-block">
        <div className="rt-toolbar">
          <h3>TaskStep 执行路径</h3>
          {onOpenFlow && !!snapshot.steps.length && (
            <button className="btn btn-secondary btn-sm" onClick={onOpenFlow}>
              Open Flow
            </button>
          )}
        </div>
        {snapshot.steps.length ? (
          <ol className="rt-mini-flow">
            {snapshot.steps.map((step) => {
              const Icon =
                step.status === 'COMPLETED'
                  ? Check
                  : step.status === 'RUNNING'
                    ? Play
                    : step.status === 'FAILED'
                      ? ShieldAlert
                      : Circle;
              return (
                <li
                  key={step.id}
                  className={`status-${step.status.toLowerCase()}`}
                >
                  <Icon size={14} aria-hidden="true" />
                  <div>
                    <code>{step.key}</code>
                    <span>{step.title}</span>
                  </div>
                  <small>{step.status}</small>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="rt-muted">
            独立 TestRun 没有 TaskStep DAG；可查看测试结果与真实执行记录。
          </p>
        )}
      </section>
      <div className="rt-overview-grid">
        <section className="rt-block">
          <h3>
            <Timer size={14} aria-hidden="true" /> 最慢的已完成步骤
          </h3>
          <p>
            {facts.slowest
              ? `${facts.slowest.key} · ${durationLabel(facts.slowest.duration_ms)}`
              : '数据暂未记录'}
          </p>
        </section>
        <section className="rt-block">
          <h3>决策与制品</h3>
          <p>
            {snapshot.decisions.length} 个决策 · {snapshot.artifacts.length}{' '}
            个制品
          </p>
          <p>
            {snapshot.browser_sessions.length} 个测试浏览器会话 ·{' '}
            {snapshot.summary.retries} 次步骤重试
          </p>
          {snapshot.artifacts.slice(0, 4).map((artifact) => (
            <div key={artifact.id} className="rt-inline-meta">
              <span>{artifact.name}</span>
              <code>{artifact.type}</code>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
