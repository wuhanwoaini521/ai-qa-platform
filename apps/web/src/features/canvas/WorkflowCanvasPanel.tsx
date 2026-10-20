import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '../../api/client';
import type { DiscoveryMetrics, WorkflowCanvas, WorkflowNode } from '../../types/workflowCanvas';
import { canvasIsLive, flowEdges, flowNodes, statusTone, type CanvasNodeData, type CanvasStageData } from './canvasModel';
import './canvas.css';

const POLL_MS = 3000;

function WorkflowNodeCard({ data, selected }: NodeProps<Node<CanvasNodeData>>) {
  return (
    <div className={`lw-node is-${data.tone}${selected ? ' is-selected' : ''}`} data-entity-id={data.entityId} title={data.entityId}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <span className="lw-node-kind">{data.kind}</span>
      <strong className="lw-node-title">{data.label}</strong>
      {data.subtitle && <span className="lw-node-subtitle">{data.subtitle}</span>}
      <span className={`lw-node-status is-${data.tone}`}>{data.status}</span>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}

function StageHeader({ data }: NodeProps<Node<CanvasStageData>>) {
  return (
    <div className="lw-stage">
      <span className="lw-stage-title">{data.title}</span>
      <span className="lw-stage-count">{data.count}</span>
    </div>
  );
}

const nodeTypes = { workflow: WorkflowNodeCard, stage: StageHeader };

function MetricGrid({ metrics }: { metrics: DiscoveryMetrics }) {
  const { t } = useTranslation('workspace');
  const entries: [string, number][] = [
    ['states', metrics.states],
    ['actions', metrics.actions],
    ['features', metrics.features],
    ['requirements', metrics.requirements],
    ['testCases', metrics.test_cases],
    ['gaps', metrics.gaps],
    ['covered', metrics.covered],
    ['notCovered', metrics.not_covered],
  ];
  return (
    <dl className="lw-metrics">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{t(`canvas.metrics.${key}`)}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function NodeDetail({ node, onClose }: { node: WorkflowNode; onClose: () => void }) {
  const { t } = useTranslation('workspace');
  const outputs = Object.entries(node.outputs).filter(([, value]) => value !== null && value !== '');
  const inputs = Object.entries(node.inputs).filter(([, value]) => value !== null && value !== '');
  const navigation = Object.entries(node.links).filter(([key]) => key !== 'api');
  return (
    <aside className="lw-detail" aria-label={t('canvas.detail.title')}>
      <header>
        <div>
          <span className="lw-node-kind">{t(`canvas.kinds.${node.kind}`)}</span>
          <h3>{node.title}</h3>
          {node.subtitle && <p className="lw-detail-subtitle">{node.subtitle}</p>}
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
          {t('canvas.detail.close')}
        </button>
      </header>
      <dl className="lw-detail-grid">
        <div><dt>{t('canvas.detail.status')}</dt><dd className={`is-${statusTone(node.status)}`}>{node.status}</dd></div>
        <div><dt>{t('canvas.detail.entity')}</dt><dd>{node.entity_type} · <code>{node.entity_id}</code></dd></div>
        {node.task_id && <div><dt>{t('canvas.detail.task')}</dt><dd><code>{node.task_id}</code></dd></div>}
        {node.started_at && <div><dt>{t('canvas.detail.startedAt')}</dt><dd>{new Date(node.started_at).toLocaleString()}</dd></div>}
        {node.finished_at && <div><dt>{t('canvas.detail.finishedAt')}</dt><dd>{new Date(node.finished_at).toLocaleString()}</dd></div>}
        {node.duration_ms !== null && <div><dt>{t('canvas.detail.duration')}</dt><dd>{Math.round(node.duration_ms / 1000)}s</dd></div>}
      </dl>
      {node.metrics && <section>
        <h4>{t('canvas.detail.metrics')}</h4>
        <MetricGrid metrics={node.metrics} />
      </section>}
      {inputs.length > 0 && <section>
        <h4>{t('canvas.detail.inputs')}</h4>
        <dl className="lw-kv">{inputs.map(([key, value]) => (
          <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>
        ))}</dl>
      </section>}
      {outputs.length > 0 && <section>
        <h4>{t('canvas.detail.outputs')}</h4>
        <dl className="lw-kv">{outputs.map(([key, value]) => (
          <div key={key}><dt>{key}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>
        ))}</dl>
      </section>}
      {node.evidence_index.length > 0 && <section>
        <h4>{t('canvas.detail.evidenceIndex')}</h4>
        <ul className="lw-evidence">
          {node.evidence_index.map((entry) => (
            <li key={entry.id}>
              <span>{t(`canvas.collections.${entry.collection}`)}</span>
              <small>{entry.summary.page_type ? String(entry.summary.page_type) : entry.collection_method}</small>
              {entry.artifact_ref && <code>{entry.artifact_ref.slice(0, 8)}</code>}
            </li>
          ))}
        </ul>
      </section>}
      {node.evidence.length > 0 && <section>
        <h4>{t('canvas.detail.evidence')}</h4>
        <ul className="lw-evidence">
          {node.evidence.map((entry) => (
            <li key={`${entry.kind}-${entry.label}`}>
              <span>{entry.label}</span>
              <small>{entry.kind}</small>
              {entry.ref && <code>{entry.ref}</code>}
            </li>
          ))}
        </ul>
      </section>}
      {navigation.length > 0 && <section>
        <h4>{t('canvas.detail.open')}</h4>
        <div className="lw-detail-actions">
          {navigation.map(([key, href]) => (
            <Link key={key} className="btn btn-secondary btn-sm" to={href}>{t(`canvas.links.${key}`)}</Link>
          ))}
        </div>
      </section>}
    </aside>
  );
}

function CanvasSurface({ projectId, requirementId }: { projectId: string; requirementId?: string }) {
  const { t } = useTranslation('workspace');
  const [canvas, setCanvas] = useState<WorkflowCanvas | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const flowHostRef = useRef<HTMLDivElement>(null);
  const { fitView, setViewport } = useReactFlow();

  const load = useCallback(async () => {
    try {
      const next = await api.getWorkflowCanvas(projectId, requirementId);
      setCanvas(next);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, [projectId, requirementId]);

  useEffect(() => {
    void load();
    setSelectedId(null);
  }, [load]);

  useEffect(() => {
    if (!canvasIsLive(canvas)) return;
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [canvas, load]);

  const nodes = useMemo(() => (canvas ? flowNodes(canvas) : []), [canvas]);
  const edges = useMemo(() => (canvas ? flowEdges(canvas) : []), [canvas]);

  useEffect(() => {
    if (nodes.length === 0) return;
    const width = flowHostRef.current?.clientWidth ?? 0;
    const timer = window.setTimeout(() => {
      // A narrow screen fits the pipeline only as an unreadable smear: start at its first stage instead.
      if (width > 0 && width < 700) void setViewport({ x: 12, y: 12, zoom: 0.6 });
      else void fitView({ padding: 0.08 });
    }, 60);
    return () => window.clearTimeout(timer);
  }, [fitView, nodes.length, setViewport]);

  const selected = canvas?.nodes.find((node) => node.id === selectedId) ?? null;

  if (error) {
    return (
      <section className="lw-canvas lw-canvas-state" role="alert">
        <h2>{t('canvas.errorTitle')}</h2>
        <p>{error}</p>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()}>{t('canvas.retry')}</button>
      </section>
    );
  }

  if (!canvas) {
    return <section className="lw-canvas lw-canvas-state" role="status">{t('canvas.loading')}</section>;
  }

  if (canvas.nodes.length === 0) {
    return (
      <section className="lw-canvas lw-canvas-state">
        <h2>{t('canvas.emptyTitle')}</h2>
        <p>{t('canvas.emptyHint')}</p>
        <div className="lw-empty-stages">
          {canvas.stages.map((stage) => (
            <span key={stage.key} className="lw-empty-stage">
              <strong>{t(`canvas.stages.${stage.key}`)}</strong>
              <small>{t(`canvas.stageHints.${stage.key}`)}</small>
            </span>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="lw-canvas" aria-label={t('canvas.title')}>
      <div className="lw-canvas-flow" ref={flowHostRef}>
        <ReactFlow
          nodes={nodes}
          edges={edges as Edge[]}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => setSelectedId(node.type === 'stage' ? null : node.id)}
          onPaneClick={() => setSelectedId(null)}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesFocusable={false}
          minZoom={0.2}
        >
          <Background gap={24} />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable />
        </ReactFlow>
      </div>
      {canvas.truncated && <p className="lw-canvas-note">{t('canvas.truncated')}</p>}
      {selected && <NodeDetail node={selected} onClose={() => setSelectedId(null)} />}
    </section>
  );
}

/** Read-only projection of the project's real pipeline records. It never starts anything. */
export function WorkflowCanvasPanel({ projectId, requirementId }: { projectId: string; requirementId?: string }) {
  return (
    <ReactFlowProvider>
      <CanvasSurface projectId={projectId} requirementId={requirementId} />
    </ReactFlowProvider>
  );
}
