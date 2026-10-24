import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { api } from '../../api/client';
import type { AgentTask } from '../../types';
import type { ExecutionTrace, TraceNode } from '../../types/executionTrace';
import {
  formatDuration,
  traceExtent,
  traceIsLive,
  treeEdges,
  treeNodes,
  treeTone,
  type TreeCardData,
} from './executionTreeModel';
import './execution-tree.css';

/** Below this zoom the card text stops being readable, so the tree anchors instead of shrinking. */
const READABLE_ZOOM = 0.7;
/** Below this the tree becomes a vertical list instead of four columns. */
const NARROW_HOST = 720;
const FITS_LEGIBLY = 0.5;
const POLL_MS = 3000;

function TraceNodeCard({ data, selected }: NodeProps<Node<TreeCardData>>) {
  const { t } = useTranslation('workspace');
  const node = data.node;
  const duration = formatDuration(node.duration_ms);
  return (
    <div className={`let-node is-${data.tone}${selected ? ' is-selected' : ''}`} data-trace-node={node.id} data-trace-kind={node.type}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="let-node-head">
        <span className="let-node-kind">{node.type}</span>
        <span className={`let-node-state is-${data.state}`}>{data.state}</span>
      </div>
      <strong className="let-node-title">{node.label}</strong>
      <div className="let-node-meta">
        {node.provider && <span>{node.provider}</span>}
        {node.model && <span className="let-node-model">{node.model}</span>}
        {duration && <span>{duration}</span>}
        {node.fallback_used && <span className="let-node-fallback">{t('executionTree.fallback')}</span>}
        {node.status && <span className="let-node-status">{node.status}</span>}
      </div>
      {data.hasChildren && (
        <button
          type="button"
          className="let-node-fold"
          aria-label={data.collapsed ? '展开子树' : '收起子树'}
          onClick={(event) => {
            event.stopPropagation();
            data.onToggle();
          }}
        >
          {data.collapsed ? '+' : '−'}
        </button>
      )}
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}

const nodeTypes = { traceNode: TraceNodeCard };

function formatCost(node: TraceNode, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (node.cost === null) return node.pricing === 'unpriced' ? t('executionTree.detail.unpriced') : t('executionTree.detail.noCost');
  return `${node.cost}`;
}

function NodeDetail({ node, onClose }: { node: TraceNode; onClose: () => void }) {
  const { t } = useTranslation('workspace');
  const kv = (record: Record<string, unknown>) => Object.entries(record).filter(([, value]) => value !== null && value !== '');
  const inputs = kv(node.inputs);
  const outputs = kv(node.outputs);
  const navigation = Object.entries(node.links ?? {});
  return (
    <aside className="let-detail" aria-label={t('executionTree.detail.title')}>
      <header>
        <div>
          <span className="let-node-kind">{t(`executionTree.kinds.${node.type}`)}</span>
          <h3>{node.label}</h3>
          {node.subtitle && <p className="let-detail-subtitle">{node.subtitle}</p>}
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
          {t('executionTree.detail.close')}
        </button>
      </header>
      <dl className="let-detail-grid">
        <div>
          <dt>{t('executionTree.detail.status')}</dt>
          <dd className={`is-${treeTone(node.status)}`}>{node.status ?? t('executionTree.unknownValue')}</dd>
        </div>
        <div>
          <dt>{t('executionTree.detail.duration')}</dt>
          <dd>{formatDuration(node.duration_ms) ?? t('executionTree.unknownValue')}</dd>
        </div>
        {node.started_at && (
          <div>
            <dt>{t('executionTree.detail.startedAt')}</dt>
            <dd>{new Date(node.started_at).toLocaleString()}</dd>
          </div>
        )}
        {node.finished_at && (
          <div>
            <dt>{t('executionTree.detail.finishedAt')}</dt>
            <dd>{new Date(node.finished_at).toLocaleString()}</dd>
          </div>
        )}
        <div>
          <dt>{t('executionTree.detail.provider')}</dt>
          <dd>{node.provider ? `${node.provider}${node.model ? ` · ${node.model}` : ''}` : t('executionTree.detail.noProvider')}</dd>
        </div>
        <div>
          <dt>{t('executionTree.detail.tokens')}</dt>
          <dd>
            {node.token_usage
              ? `${t('executionTree.detail.inputTokens', { value: node.token_usage.input_tokens ?? 0 })} · ${t('executionTree.detail.outputTokens', { value: node.token_usage.output_tokens ?? 0 })} · ${node.token_usage.source}`
              : t('executionTree.detail.noTokens')}
          </dd>
        </div>
        <div>
          <dt>{t('executionTree.detail.cost')}</dt>
          <dd>{formatCost(node, t)}</dd>
        </div>
        {node.task_id && (
          <div>
            <dt>{t('executionTree.detail.task')}</dt>
            <dd><code>{node.task_id}</code></dd>
          </div>
        )}
        {node.invocation_id && (
          <div>
            <dt>{t('executionTree.detail.invocation')}</dt>
            <dd><code>{node.invocation_id}</code></dd>
          </div>
        )}
      </dl>
      {node.error_code && (
        <section>
          <h4>{t('executionTree.detail.error')}</h4>
          <p className="let-error" role="alert">
            <code>{node.error_code}</code>
            {node.error_message && <span>{node.error_message}</span>}
          </p>
        </section>
      )}
      {inputs.length > 0 && (
        <section>
          <h4>{t('executionTree.detail.inputs')}</h4>
          <dl className="let-kv">
            {inputs.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      {outputs.length > 0 && (
        <section>
          <h4>{t('executionTree.detail.outputs')}</h4>
          <dl className="let-kv">
            {outputs.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      {node.evidence_ids.length > 0 && (
        <section>
          <h4>{t('executionTree.detail.evidence')}</h4>
          <ul className="let-evidence">
            {node.evidence_ids.map((id) => (
              <li key={id}><code>{id}</code></li>
            ))}
          </ul>
        </section>
      )}
      {node.unknown.length > 0 && (
        <section>
          <h4>{t('executionTree.detail.unknown')}</h4>
          <p className="let-detail-note">
            {t('executionTree.detail.unknownHint', { fields: node.unknown.join(', ') })}
          </p>
        </section>
      )}
      {navigation.length > 0 && (
        <section>
          <h4>{t('executionTree.detail.open')}</h4>
          <div className="let-detail-actions">
            {navigation.map(([key, href]) => (
              <Link key={key} className="btn btn-secondary btn-sm" to={href}>
                {t(`executionTree.links.${key}`)}
              </Link>
            ))}
          </div>
        </section>
      )}
    </aside>
  );
}

function TreeSurface({ projectId, initialTaskId }: { projectId: string; initialTaskId?: string | null }) {
  const { t } = useTranslation('workspace');
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [taskId, setTaskId] = useState<string | null>(initialTaskId ?? null);
  const [trace, setTrace] = useState<ExecutionTrace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [focusId, setFocusId] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const hostRef = useRef<HTMLDivElement>(null);
  const nodesInitialized = useNodesInitialized();
  const { fitView, setViewport } = useReactFlow();

  const load = useCallback(async () => {
    try {
      const next = taskId ? await api.getTaskExecutionTrace(taskId) : await api.getProjectExecutionTrace(projectId, 6);
      setTrace(next);
      setError(null);
      return next;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      return null;
    }
  }, [projectId, taskId]);

  useEffect(() => {
    let alive = true;
    void api
      .getTasks(projectId)
      .then((rows) => {
        if (!alive) return;
        const ordered = [...rows].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
        setTasks(ordered);
        setTaskId((current) => current ?? initialTaskId ?? ordered[0]?.id ?? null);
      })
      .catch(() => {
        if (alive) setTasks([]);
      });
    return () => {
      alive = false;
    };
  }, [initialTaskId, projectId]);

  useEffect(() => {
    setSelectedId(null);
    setCollapsed(new Set());
    setFocusId(null);
    void load();
  }, [load]);

  // Live: follow the task's own event stream and re-read the server, which stays the only source.
  useEffect(() => {
    if (!taskId) return;
    let timer: number | null = null;
    const resync = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(() => void load(), 400);
    };
    const close = api.streamTaskEvents(
      taskId,
      (event) => {
        setLive(true);
        if (['task.completed', 'task.failed', 'task.blocked', 'task.cancelled'].includes(event.type)) setLive(false);
        resync();
      },
      () => setLive(false),
    );
    return () => {
      if (timer !== null) window.clearTimeout(timer);
      close();
    };
  }, [load, taskId]);

  useEffect(() => {
    if (traceIsLive(trace)) setLive(true);
  }, [trace]);

  useEffect(() => {
    if (!live) return;
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [live, load]);

  const toggle = useCallback((nodeId: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }, []);

  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    // The flow element only mounts once a trace exists, so this has to re-run with it.
    const host = hostRef.current;
    if (!host || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => setNarrow(entry.contentRect.width < NARROW_HOST));
    observer.observe(host);
    return () => observer.disconnect();
  }, [trace]);
  const cards = useMemo(
    () => (trace ? treeNodes(trace, { collapsed, focusId, stacked: narrow }, toggle) : []),
    [collapsed, focusId, narrow, toggle, trace],
  );
  const visibleIds = useMemo(() => new Set(cards.map((card) => card.id)), [cards]);
  const edges = useMemo(() => (trace ? treeEdges(trace, visibleIds) : []), [trace, visibleIds]);
  const extent = useMemo(() => traceExtent(cards), [cards]);

  useEffect(() => {
    // Fit once the cards exist; the host can still be unmounted or hidden on the first tick, and a
    // silently skipped fit left the tree at zoom 1 with its last column off-screen at 1024px.
    if (cards.length === 0) return;
    let cancelled = false;
    let tries = 0;
    let timer = 0;
    const attempt = () => {
      if (cancelled) return;
      const host = hostRef.current;
      if (!host || host.clientWidth === 0) {
        if (tries++ < 20) timer = window.setTimeout(attempt, 120);
        return;
      }
      // A stacked list is read top-to-bottom and panned, so only its width has to fit.
      if (narrow) {
        void setViewport({ x: 8, y: 8, zoom: Math.min(1, host.clientWidth / (extent.right + 16)) });
        return;
      }
      const zoom = Math.min(host.clientWidth / (extent.right + 28), host.clientHeight / (extent.bottom + 28));
      // A tree squeezed to unreadable text is worse than a tree you pan: anchor at the root instead.
      if (zoom < FITS_LEGIBLY) void setViewport({ x: 16, y: 16, zoom: READABLE_ZOOM });
      else void fitView({ padding: 0.1, maxZoom: 1 });
    };
    timer = window.setTimeout(attempt, nodesInitialized ? 60 : 160);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [cards.length, extent.bottom, extent.right, fitView, narrow, nodesInitialized, setViewport]);

  const selected = trace?.nodes.find((node) => node.id === selectedId) ?? null;
  const roots = trace?.nodes.filter((node) => node.type === 'task') ?? [];

  if (error) {
    return (
      <section className="let-panel let-state" role="alert">
        <h2>{t('executionTree.errorTitle')}</h2>
        <p>{error}</p>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()}>
          {t('executionTree.retry')}
        </button>
      </section>
    );
  }

  return (
    <section className="let-panel" aria-label={t('executionTree.title')}>
      <header className="let-toolbar">
        <label className="let-picker">
          <span>{t('executionTree.task')}</span>
          <select
            aria-label={t('executionTree.task')}
            value={taskId ?? ''}
            onChange={(event) => setTaskId(event.target.value || null)}
          >
            <option value="">{t('executionTree.allTasks')}</option>
            {tasks.map((task) => (
              <option key={task.id} value={task.id}>
                {t(`executionTree.taskTypes.${task.type}`, { defaultValue: task.type })} · {task.status} · {task.goal.slice(0, 40)}
              </option>
            ))}
          </select>
        </label>
        <div className="let-meta">
          {live && <span className="let-live" role="status">{t('executionTree.live')}</span>}
          {trace && (
            <span>
              {t('executionTree.summary', {
                nodes: trace.nodes.length,
                roots: trace.root_count,
                invocations: trace.counts.invocation ?? 0,
              })}
              {trace.workflow_execution_id && (
                <> · {t('executionTree.workflowProvenance', { version: trace.workflow_version, execution: trace.workflow_execution_id.slice(0, 8) })}</>
              )}
            </span>
          )}
          {focusId && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setFocusId(null)}>
              {t('executionTree.clearFocus')}
            </button>
          )}
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()}>
            {t('executionTree.refresh')}
          </button>
        </div>
      </header>

      {trace && trace.nodes.length === 0 && (
        <div className="let-state" role="status">
          <h2>{t('executionTree.emptyTitle')}</h2>
          <p>{t('executionTree.emptyHint')}</p>
        </div>
      )}

      {trace && trace.nodes.length > 0 && (
        <div className={`let-body${narrow ? ' is-narrow' : ''}`}>
          <div className="let-flow" ref={hostRef}>
            <ReactFlow
              nodes={cards as unknown as Node[]}
              edges={edges as unknown as Edge[]}
              nodeTypes={nodeTypes}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable
              onNodeClick={(_, node) => setSelectedId(node.id)}
              onNodeDoubleClick={(_, node) => setFocusId(node.id)}
              minZoom={0.2}
              maxZoom={1.6}
              proOptions={{ hideAttribution: false }}
            >
              <Background gap={22} size={1} color="#20262f" />
              <Controls showInteractive={false} />
              <MiniMap
                pannable
                zoomable
                position="bottom-left"
                maskColor="rgba(8, 11, 15, 0.75)"
                nodeColor={(node) => toneColor((node.data as TreeCardData)?.tone)}
              />
            </ReactFlow>
          </div>
          {selected && <NodeDetail node={selected} onClose={() => setSelectedId(null)} />}
        </div>
      )}

      {trace && trace.nodes.length > 0 && (
        <footer className="let-legend">
          {(['done', 'running', 'waiting', 'failed'] as const).map((state) => (
            <span key={state} className={`let-legend-item is-${state}`}>
              <i />
              {t(`executionTree.states.${state}`)}
            </span>
          ))}
          {trace.unknown.length > 0 && (
            <span className="let-legend-note">
              {t('executionTree.unknownHint', { fields: trace.unknown.join(', ') })}
            </span>
          )}
          {roots.length > 1 && <span className="let-legend-note">{t('executionTree.parallelHint')}</span>}
          <span className="let-legend-note is-quiet">{t('executionTree.hint')}</span>
        </footer>
      )}
    </section>
  );
}

function toneColor(tone: TreeCardData['tone'] | undefined): string {
  if (tone === 'ok') return '#2f7d4f';
  if (tone === 'active') return '#2563eb';
  if (tone === 'attention') return '#a16207';
  if (tone === 'bad') return '#9f1239';
  return '#374151';
}

export function ExecutionTreePanel({ projectId, taskId: initialTaskId }: { projectId: string; taskId?: string | null }) {
  return (
    <ReactFlowProvider>
      <TreeSurface projectId={projectId} initialTaskId={initialTaskId} />
    </ReactFlowProvider>
  );
}
