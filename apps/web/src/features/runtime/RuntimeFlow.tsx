import { memo, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Circle,
  Crosshair,
  Maximize2,
  Minus,
  Plus,
  Scan,
  ShieldAlert,
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
}: {
  step: RuntimeStep;
  selected: boolean;
  onSelect: (id: string) => void;
  decisions: number;
  jev: boolean;
  artifacts: number;
  runs: number;
}) {
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
  return (
    <button
      className={`rt-node status-${step.status.toLowerCase()}${selected ? ' is-selected' : ''}`}
      aria-pressed={selected}
      onClick={() => onSelect(step.id)}
    >
      <div className="rt-node-key">
        <Icon size={13} aria-hidden="true" />
        <code title={step.key}>{step.key}</code>
        {step.status === 'RUNNING' && <span className="rt-pulse" />}
      </div>
      <strong title={step.title}>{step.title}</strong>
      <div className="rt-node-meta">
        <span title={step.tool}>{step.tool}</span>
        <time>{durationLabel(spanDuration(step, now))}</time>
      </div>
      <div className="rt-node-footer">
        <span>{step.status}</span>
        <div>
          {decisions > 0 && <small>Decision {decisions}</small>}
          {jev && <small>JEV</small>}
          {step.retry_count > 0 && <small>Retry {step.retry_count}</small>}
          {artifacts > 0 && <small>Artifact {artifacts}</small>}
          {runs > 0 && <small>Run {runs}</small>}
        </div>
      </div>
    </button>
  );
});

export function RuntimeFlow({
  snapshot,
  selectedStepId,
  onSelect,
  focus,
  onFocus,
}: {
  snapshot: RuntimeSnapshot;
  selectedStepId: string | null;
  onSelect: (id: string) => void;
  focus: boolean;
  onFocus: () => void;
}) {
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
      <p className="rt-empty">
        此独立 TestRun 没有 TaskStep DAG。数据暂未记录。
      </p>
    );
  return (
    <section
      className="rt-flow"
      aria-label="Live Runtime Canvas"
      style={
        {
          '--rt-node-width': `${FLOW_NODE_WIDTH}px`,
          '--rt-node-height': `${FLOW_NODE_HEIGHT}px`,
        } as CSSProperties
      }
    >
      <div className="rt-toolbar rt-flow-controls">
        <div className="rt-control-group">
          <button
            aria-pressed={direction === 'vertical'}
            onClick={() => setDirection('vertical')}
          >
            纵向
          </button>
          <button
            aria-pressed={direction === 'horizontal'}
            onClick={() => setDirection('horizontal')}
          >
            横向
          </button>
          <button
            onClick={() => {
              setFollow(false);
              view.fit();
            }}
          >
            <Scan size={14} aria-hidden="true" />
            查看全图
          </button>
          <button
            aria-label="缩小画布"
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
            aria-label="放大画布"
            disabled={view.scale >= 2}
            onClick={() => {
              setFollow(false);
              view.zoom(view.scale + 0.15);
            }}
          >
            <Plus size={14} aria-hidden="true" />
          </button>
          <button
            onClick={() => {
              setFollow(false);
              view.zoom(1);
            }}
          >
            实际大小
          </button>
        </div>
        <div className="rt-control-group">
          <button disabled={!activeId} onClick={centerActive}>
            <Crosshair size={14} aria-hidden="true" />
            定位执行中
          </button>
          <button
            aria-pressed={follow && !!activeId}
            disabled={!activeId}
            onClick={() => setFollow((value) => !value)}
          >
            跟随执行
          </button>
          <button aria-pressed={focus} onClick={onFocus}>
            <Maximize2 size={14} aria-hidden="true" />
            {focus ? '退出专注' : '专注模式'}
          </button>
        </div>
      </div>
      <div className="rt-flow-navigation">
        <div className="rt-control-group">
          <button
            aria-label="上一步"
            disabled={currentIndex <= 0}
            onClick={() => select(layout.order[currentIndex - 1])}
          >
            <ChevronLeft size={14} aria-hidden="true" />
          </button>
          <select
            aria-label="定位步骤"
            value={currentId ?? ''}
            onChange={(event) => select(event.target.value)}
          >
            <option value="" disabled>
              选择步骤 · {layout.order.length} 个步骤
            </option>
            {layout.order.map((id, index) => (
              <option key={id} value={id}>
                {index + 1}. {steps.get(id)?.title}
              </option>
            ))}
          </select>
          <button
            aria-label="下一步"
            disabled={currentIndex >= layout.order.length - 1}
            onClick={() => select(layout.order[currentIndex + 1])}
          >
            <ChevronRight size={14} aria-hidden="true" />
          </button>
          <code>
            {currentIndex >= 0 ? currentIndex + 1 : '—'} / {layout.order.length}
          </code>
        </div>
        <span id="rt-flow-help">
          滚动浏览 · Ctrl / ⌘ + 滚轮缩放 · 点击步骤查看详情
        </span>
      </div>
      {!!(layout.cycle.length || layout.unknown.length) && (
        <p className="rt-notice">
          历史 DAG 存在循环或缺失依赖；仅展示已记录的关系。
        </p>
      )}
      <div
        className="rt-viewport rt-flow-viewport"
        ref={view.viewport}
        tabIndex={0}
        aria-label="执行流程画布"
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
              {layout.edges.map((edge) => {
                const source = layout.positions.get(edge.source)!;
                const target = layout.positions.get(edge.target)!;
                const status = steps.get(edge.target)?.status;
                return (
                  <path
                    key={`${edge.source}:${edge.target}`}
                    d={
                      direction === 'horizontal'
                        ? `M${source.x + FLOW_NODE_WIDTH},${source.y + FLOW_NODE_HEIGHT / 2} C${source.x + FLOW_NODE_WIDTH + 32},${source.y + FLOW_NODE_HEIGHT / 2} ${target.x - 32},${target.y + FLOW_NODE_HEIGHT / 2} ${target.x},${target.y + FLOW_NODE_HEIGHT / 2}`
                        : `M${source.x + FLOW_NODE_WIDTH / 2},${source.y + FLOW_NODE_HEIGHT} C${source.x + FLOW_NODE_WIDTH / 2},${source.y + FLOW_NODE_HEIGHT + 28} ${target.x + FLOW_NODE_WIDTH / 2},${target.y - 28} ${target.x + FLOW_NODE_WIDTH / 2},${target.y}`
                    }
                    className={
                      status === 'RUNNING'
                        ? 'is-active'
                        : status === 'FAILED'
                          ? 'is-failed'
                          : status === 'COMPLETED'
                            ? 'is-completed'
                            : ''
                    }
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
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="rt-flow-legend">
        <span>○ Pending</span>
        <span className="status-running">● Running</span>
        <span className="status-completed">✓ Completed</span>
        <span className="status-failed">! Failed</span>
        <span>
          {snapshot.steps.length} steps · {layout.edges.length} dependencies
        </span>
      </div>
    </section>
  );
}
