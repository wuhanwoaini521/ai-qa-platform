import { memo, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Circle,
  Maximize2,
  Minus,
  Plus,
  Scan,
  ShieldAlert,
  X,
} from 'lucide-react';
import type { RuntimeSnapshot, RuntimeStep } from '../../types/runtime';
import {
  FLOW_NODE_HEIGHT,
  FLOW_NODE_WIDTH,
  graphStructure,
  layoutDAG,
} from './dagLayout';
import type { FlowDirection } from './dagLayout';
import { useFlowViewport } from './useFlowViewport';
import { durationLabel, spanDuration } from './runtimeModel';

const StepNode = memo(function StepNode({
  step,
  selected,
  onSelect,
  decisions,
  jev,
  artifacts,
  runs,
  blocked,
  downstreamBlocked,
}: {
  step: RuntimeStep;
  selected: boolean;
  onSelect: (id: string) => void;
  decisions: number;
  jev: boolean;
  artifacts: number;
  runs: number;
  blocked: boolean;
  downstreamBlocked: boolean;
}) {
  const { t } = useTranslation('runtime');
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (step.status !== 'RUNNING') return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [step.status]);
  const Icon =
    step.status === 'COMPLETED'
      ? Check
      : step.status === 'FAILED'
        ? ShieldAlert
        : Circle;
  const status = step.status === 'PENDING' ? t('pending') : step.status === 'WAITING_FOR_APPROVAL' ? t('waitingApproval') : t(step.status.toLowerCase());
  return (
    <button
      className={`rt-node status-${step.status.toLowerCase()}${selected ? ' is-selected' : ''}${blocked ? ' is-blocker' : ''}${downstreamBlocked ? ' is-downstream-blocked' : ''}`}
      aria-pressed={selected}
      aria-label={`${step.key}: ${step.title}, ${t(step.status === 'WAITING_FOR_APPROVAL' ? 'waitingApproval' : step.status.toLowerCase())}${blocked ? `, ${t('blockedHere')}` : ''}`}
      title={`${step.key} · ${step.title} · ${step.tool}`}
      onClick={() => onSelect(step.id)}
    >
      <div className="rt-node-key">
        <Icon size={13} aria-hidden="true" />
        <code title={step.key}>{step.key}</code>
        {step.status === 'RUNNING' && <span className="rt-pulse" />}
      </div>
      {blocked && <small className="rt-blocker-marker">{t('blockedHere')}</small>}
      <strong title={step.title}>{step.title}</strong>
      <div className="rt-node-meta">
        <span title={step.tool}>{step.tool}</span>
        <time>{durationLabel(spanDuration(step, now))}</time>
      </div>
      <div className="rt-node-footer">
        <span>{status}</span>
        <div>
          {decisions > 0 && <small>{t('decision')} {decisions}</small>}
          {jev && <small>JEV</small>}
          {step.retry_count > 0 && <small>{t('retry')} {step.retry_count}</small>}
          {artifacts > 0 && <small>{t('artifacts')} {artifacts}</small>}
          {runs > 0 && <small>{t('testRun')} {runs}</small>}
        </div>
      </div>
    </button>
  );
});

export function RuntimeFlow({
  snapshot,
  selectedStepId,
  onSelect,
  onClearSelection,
  focus,
  onFocus,
}: {
  snapshot: RuntimeSnapshot;
  selectedStepId: string | null;
  onSelect: (id: string) => void;
  onClearSelection: () => void;
  focus: boolean;
  onFocus: () => void;
}) {
  const { t } = useTranslation('runtime');
  const structure = graphStructure(snapshot.steps);
  const [direction, setDirection] = useState<FlowDirection>('vertical');
  const layout = useMemo(
    () => layoutDAG(snapshot.steps, direction),
    [structure, direction],
  );
  const hasSteps = snapshot.steps.length > 0;
  const view = useFlowViewport(layout.width, layout.height, hasSteps);
  const [follow, setFollow] = useState(!selectedStepId);
  const activeId = snapshot.summary.active_step_ids[0] ?? null;
  const blockedStepIds = new Set(snapshot.blocking?.step_id ? [snapshot.blocking.step_id] : []);
  const downstreamBlocked = new Set<string>();
  if (snapshot.status === 'BLOCKED' && snapshot.blocking?.step_key) {
    const keys = new Set([snapshot.blocking.step_key]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const step of snapshot.steps) {
        if (step.status === 'PENDING' && !keys.has(step.key) && step.dependencies.some((key) => keys.has(key))) {
          keys.add(step.key);
          changed = true;
        }
      }
    }
    for (const step of snapshot.steps) if (step.status === 'PENDING' && keys.has(step.key)) downstreamBlocked.add(step.id);
  }
  const steps = new Map(snapshot.steps.map((step) => [step.id, step]));
  const currentId = selectedStepId ?? activeId;
  const currentIndex = currentId ? layout.order.indexOf(currentId) : -1;
  const select = (id: string) => {
    setFollow(false);
    onSelect(id);
    const position = layout.positions.get(id);
    if (position) view.center(position, true);
  };
  const centerActive = () => {
    const position = activeId ? layout.positions.get(activeId) : null;
    if (position) view.center(position, true);
  };
  // Selection and layout changes reveal the step without shrinking the whole run.
  useLayoutEffect(() => {
    const id = follow && activeId ? activeId : selectedStepId;
    const position = id ? layout.positions.get(id) : null;
    if (position) view.center(position, true);
    else view.viewport.current?.scrollTo(0, 0);
  }, [selectedStepId, layout]);
  useLayoutEffect(() => {
    if (follow && activeId) centerActive();
  }, [activeId, follow]);
  useLayoutEffect(() => {
    const id = follow && activeId ? activeId : selectedStepId;
    const position = id ? layout.positions.get(id) : null;
    if (position) view.center(position);
  }, [view.size.width, view.size.height]);
  useEffect(() => {
    const element = view.viewport.current;
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      setFollow(false);
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      view.zoom(view.scale * Math.exp(-event.deltaY * 0.005), {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      });
    };
    element.addEventListener('wheel', onWheel, { passive: false });
    return () => element.removeEventListener('wheel', onWheel);
  }, [view.scale, view.inset, layout.width, hasSteps]);
  if (!snapshot.steps.length)
    return (
      <p className="rt-empty">{t('noTaskDag')}</p>
    );
  return (
    <section
      className="rt-flow"
      aria-label={t('observatory')}
      style={
        {
          '--rt-node-width': `${FLOW_NODE_WIDTH}px`,
          '--rt-node-height': `${FLOW_NODE_HEIGHT}px`,
        } as CSSProperties
      }
    >
      <div className="rt-toolbar rt-flow-controls">
        <div className="rt-control-group">
          <label className="rt-direction-control">{t('direction')}
            <select aria-label={t('direction')} value={direction} onChange={(event) => setDirection(event.target.value as FlowDirection)}>
              <option value="vertical">{t('vertical')}</option><option value="horizontal">{t('horizontal')}</option>
            </select>
          </label>
          <button
            onClick={() => {
              setFollow(false);
              view.fit();
            }}
          >
            <Scan size={14} aria-hidden="true" />
            {t('fit')}
          </button>
          <button
            aria-label={t('zoomOut')}
            disabled={view.scale <= 0.15}
            onClick={() => {
              setFollow(false);
              view.zoom(view.scale - 0.15);
            }}
          >
            <Minus size={14} aria-hidden="true" />
          </button>
          <code>{Math.round(view.scale * 100)}%</code>
          <button
            aria-label={t('zoomIn')}
            disabled={view.scale >= 2}
            onClick={() => {
              setFollow(false);
              view.zoom(view.scale + 0.15);
            }}
          >
            <Plus size={14} aria-hidden="true" />
          </button>
        </div>
        <div className="rt-control-group">
          <button
            aria-pressed={follow && !!activeId}
            disabled={!activeId}
            onClick={() => setFollow((value) => !value)}
          >
            {t('followActive')}
          </button>
          <button className="rt-flow-focus" aria-label={t(focus ? 'exitFocus' : 'focusMode')} title={t(focus ? 'exitFocus' : 'focusMode')} aria-pressed={focus} onClick={onFocus}>
            <Maximize2 size={14} aria-hidden="true" />
            <span>{focus ? t('exitFocus') : t('focusMode')}</span>
          </button>
        </div>
      </div>
      <div className="rt-flow-navigation">
        <div className="rt-control-group">
          <button
            aria-label={t('previousStep')}
            disabled={currentIndex <= 0}
            onClick={() => select(layout.order[currentIndex - 1])}
          >
            <ChevronLeft size={14} aria-hidden="true" />
          </button>
          <select
            aria-label={t('jumpToStep')}
            value={currentId ?? ''}
            onChange={(event) => select(event.target.value)}
          >
            <option value="" disabled>
              {t('jumpToStep')} · {layout.order.length} {t('step')}
            </option>
            {layout.order.map((id, index) => (
              <option key={id} value={id}>
                {index + 1}. {steps.get(id)?.title}
              </option>
            ))}
          </select>
          <button
            aria-label={t('nextStep')}
            disabled={currentIndex >= layout.order.length - 1}
            onClick={() => select(layout.order[currentIndex + 1])}
          >
            <ChevronRight size={14} aria-hidden="true" />
          </button>
          <code>
            {currentIndex >= 0 ? currentIndex + 1 : '—'} / {layout.order.length}
          </code>
          {selectedStepId && <button className="rt-flow-clear-selection" aria-label={t('clearStepFilter')} title={t('clearStepFilter')} onClick={() => { setFollow(false); onClearSelection(); }}><X size={14} aria-hidden="true" /></button>}
        </div>
        <span id="rt-flow-help">
          {t('flowHelp')}
        </span>
      </div>
      {!!(layout.cycle.length || layout.unknown.length) && (
        <p className="rt-notice">{t('invalidDag')}</p>
      )}
      <div
        className="rt-viewport rt-flow-viewport"
        ref={view.viewport}
        tabIndex={0}
        aria-label={t('flowCanvas')}
        aria-describedby="rt-flow-help"
        onPointerDown={(event) => {
          if (!(event.target as HTMLElement).closest('button,a'))
            setFollow(false);
        }}
        onKeyDown={(event) => {
          if (
            event.target === event.currentTarget &&
            [
              'ArrowLeft',
              'ArrowRight',
              'ArrowUp',
              'ArrowDown',
              'PageUp',
              'PageDown',
              'Home',
              'End',
              ' ',
            ].includes(event.key)
          )
            setFollow(false);
        }}
      >
        <div
          className="rt-flow-space"
          style={{
            width: Math.max(view.size.width, layout.width * view.scale),
            height: Math.max(view.size.height, layout.height * view.scale),
          }}
        >
          <div
            className="rt-canvas"
            style={{
              width: layout.width,
              height: layout.height,
              left: view.inset,
              transform: `scale(${view.scale})`,
            }}
          >
            <svg width={layout.width} height={layout.height} aria-hidden="true">
              <defs><marker id="rt-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" className="rt-edge-arrow" /></marker></defs>
              {layout.edges.map((edge) => {
                const source = layout.positions.get(edge.source)!;
                const target = layout.positions.get(edge.target)!;
                const sourceStep = steps.get(edge.source);
                const targetStep = steps.get(edge.target);
                const status = targetStep?.status;
                const blockedEdge = sourceStep?.status === 'FAILED' && targetStep?.status === 'PENDING';
                const activeEdge = sourceStep?.status === 'COMPLETED' && ['RUNNING', 'FAILED'].includes(targetStep?.status ?? '');
                const edgeState = blockedEdge ? 'is-blocked' : status === 'FAILED' ? 'is-failed' : activeEdge ? 'is-active' : status === 'COMPLETED' ? 'is-completed' : '';
                return (
                  <path
                    key={`${edge.source}:${edge.target}`}
                    d={
                      direction === 'horizontal'
                        ? `M${source.x + FLOW_NODE_WIDTH},${source.y + FLOW_NODE_HEIGHT / 2} C${source.x + FLOW_NODE_WIDTH + 32},${source.y + FLOW_NODE_HEIGHT / 2} ${target.x - 32},${target.y + FLOW_NODE_HEIGHT / 2} ${target.x},${target.y + FLOW_NODE_HEIGHT / 2}`
                        : `M${source.x + FLOW_NODE_WIDTH / 2},${source.y + FLOW_NODE_HEIGHT} C${source.x + FLOW_NODE_WIDTH / 2},${source.y + FLOW_NODE_HEIGHT + 28} ${target.x + FLOW_NODE_WIDTH / 2},${target.y - 28} ${target.x + FLOW_NODE_WIDTH / 2},${target.y}`
                    }
                    markerEnd="url(#rt-arrow)"
                    className={edgeState}
                  />
                );
              })}
            </svg>
            {snapshot.steps.map((step) => {
              const position = layout.positions.get(step.id)!;
              return (
                <div
                  className="rt-node-position"
                  key={step.id}
                  style={{ left: position.x, top: position.y }}
                >
                  <StepNode
                    step={step}
                    selected={step.id === selectedStepId}
                    onSelect={select}
                    decisions={
                      snapshot.decisions.filter(
                        (item) => item.step_id === step.id,
                      ).length
                    }
                    jev={
                      snapshot.decisions.some(
                        (item) =>
                          item.step_id === step.id && item.provider === 'jev',
                      ) ||
                      snapshot.events.some(
                        (item) =>
                          item.step_id === step.id &&
                          item.metadata.provider === 'jev',
                      )
                    }
                    artifacts={
                      snapshot.artifacts.filter(
                        (item) => item.step_id === step.id,
                      ).length
                    }
                    runs={
                      snapshot.runs.filter((item) => item.step_id === step.id)
                        .length
                    }
                    blocked={blockedStepIds.has(step.id)}
                    downstreamBlocked={downstreamBlocked.has(step.id)}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="rt-flow-legend">
        <span>○ {t('pending')}</span>
        <span className="status-running">● {t('running')}</span>
        <span className="status-completed">✓ {t('completed')}</span>
        <span className="status-failed">! {t('failed')} · {t('blocker')}</span>
        <span>
          {snapshot.steps.length} {t('step')} · {layout.edges.length} {t('dependencies')}
        </span>
      </div>
    </section>
  );
}
